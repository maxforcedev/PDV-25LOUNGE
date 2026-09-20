import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../sales/sale_models.dart';
import '../sales/sale_presentation.dart';
import '../sales/shared_authorization_dialog.dart';
import '../sales/shared_customer_dialog.dart';
import '../sales/shared_discount_dialog.dart';
import 'payment_contract.dart';
import 'payment_flow_components.dart';
import 'quick_sale_payment_adapter.dart';
import 'shared_payment_widgets.dart';

/// Reusable persistent-checkout UI. Hosts provide a checkout snapshot and POS API controller.
class SharedPaymentPage extends StatefulWidget {
  const SharedPaymentPage({
    required this.controller,
    required this.options,
    required this.checkout,
    required this.onCompleted,
    required this.onCancelled,
    super.key,
  });

  final AppController controller;
  final QuickSaleCheckout checkout;
  final QuickSaleCheckoutOptions options;
  final Future<void> Function(QuickSaleResult result) onCompleted;
  final Future<void> Function() onCancelled;

  @override
  State<SharedPaymentPage> createState() => _SharedPaymentPageState();
}

class _SharedPaymentPageState extends State<SharedPaymentPage> {
  late QuickSaleCheckout _checkout = widget.checkout;
  bool _working = false;

  List<QuickSalePaymentMethod> get _methods => widget.options.paymentMethods;
  List<_EqualSplitPart>? _equalSplitParts;
  QuickSalePaymentAttempt? _pendingPayment;
  int? _pendingEqualSplitIndex;
  bool _showSummaryDetails = false;
  bool get _canDiscount =>
      widget.controller.bootstrapSnapshot?.permissions
          .contains('sales.apply_discount') ??
      false;
  bool get _canItemDiscount =>
      widget.controller.bootstrapSnapshot?.permissions
          .contains('sales.apply_item_discount') ??
      false;
  bool get _hasAppliedPayment => _checkout.payments.any((payment) =>
      !payment.isReversal && !_checkout.hasReversalFor(payment.id));

  @override
  void initState() {
    super.initState();
    _restorePendingPayment();
  }

  Future<void> _restorePendingPayment() async {
    final pending =
        await widget.controller.pendingQuickSalePayment(_checkout.id);
    if (mounted) setState(() => _pendingPayment = pending);
  }

  void _replaceCheckout(QuickSaleCheckout checkout,
      {bool preserveEqualSplit = false}) {
    setState(() {
      if (!preserveEqualSplit &&
          checkout.remainingAmount != _checkout.remainingAmount) {
        _equalSplitParts = null;
      }
      _checkout = checkout;
    });
  }

  bool get _canWaiveFee =>
      widget.controller.bootstrapSnapshot?.permissions
          .contains('sales.waive_service_fee') ??
      false;
  bool get _canAddCustomers =>
      widget.controller.bootstrapSnapshot?.permissions
          .contains('customers.add') ??
      false;

  Future<void> _updateFinancials({
    List<Map<String, dynamic>>? items,
    QuickSaleCustomer? customer,
    bool clearCustomer = false,
    QuickSaleDiscountIntent? discount,
    bool? serviceFeeWaived,
    QuickSaleAuthorization? discountAuthorization,
    QuickSaleAuthorization? itemDiscountAuthorization,
    QuickSaleAuthorization? serviceFeeAuthorization,
  }) async {
    if (!_checkout.canEditFinancials || _working) return;
    setState(() => _working = true);
    final updated = await widget.controller.updateQuickSaleCheckout(
      checkoutId: _checkout.id,
      items: items ??
          _checkout.items.map((item) => item.input).toList(growable: false),
      cashSessionId: _checkout.cashSessionId,
      customerId: clearCustomer ? null : (customer ?? _checkout.customer)?.id,
      discount: (discount ?? _checkout.discountIntent).toJson(),
      serviceFeeWaived: serviceFeeWaived ?? _checkout.serviceFeeWaived,
      discountAuthorization: discountAuthorization,
      itemDiscountAuthorization: itemDiscountAuthorization,
      serviceFeeAuthorization: serviceFeeAuthorization,
    );
    if (mounted) setState(() => _working = false);
    if (updated != null && mounted) _replaceCheckout(updated);
  }

  Future<QuickSaleAuthorization?> _requestAuthorization(String type) async {
    final authorizers = switch (type) {
      'item' => await widget.controller.quickSaleItemDiscountAuthorizers(),
      'service_fee' => await widget.controller.quickSaleServiceFeeAuthorizers(),
      _ => await widget.controller.quickSaleDiscountAuthorizers(),
    };
    if (!mounted || authorizers == null) return null;
    if (authorizers.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content:
            Text('Nenhum autorizador elegível está disponível nesta filial.'),
      ));
      return null;
    }
    return showDialog<QuickSaleAuthorization>(
      context: context,
      builder: (_) => SharedAuthorizationDialog(
        authorizers: authorizers,
        onAuthorize: (authorization) =>
            widget.controller.validateQuickSaleDiscountAuthorization(
          type: type,
          authorization: authorization,
        ),
      ),
    );
  }

  Future<void> _editFinancials(_FinancialEdit action) async {
    if (!_checkout.canEditFinancials || _working) return;
    switch (action) {
      case _FinancialEdit.customer:
        final customer = await showDialog<QuickSaleCustomer>(
          context: context,
          builder: (_) => SharedCustomerPickerDialog(
            controller: widget.controller,
            canCreate: _canAddCustomers,
          ),
        );
        if (customer != null && mounted) {
          await _updateFinancials(customer: customer);
        }
        return;
      case _FinancialEdit.removeCustomer:
        await _updateFinancials(clearCustomer: true);
        return;
      case _FinancialEdit.itemDiscount:
        await _editItemDiscount();
        return;
      case _FinancialEdit.discount:
        final maximumAmount = [
          double.tryParse(_checkout.preview.subtotal.replaceAll(',', '.')) ?? 0,
          -(double.tryParse(_checkout.preview.promotionDiscountTotal
                  .replaceAll(',', '.')) ??
              0),
          -(double.tryParse(
                  _checkout.preview.itemDiscountTotal.replaceAll(',', '.')) ??
              0),
        ].reduce((total, value) => total + value);
        final discount = await showDialog<QuickSaleDiscountIntent>(
          context: context,
          builder: (_) => SharedDiscountDialog(
            initial: _checkout.discountIntent,
            maximumAmount: maximumAmount < 0 ? 0 : maximumAmount,
            prefillInitialValue: true,
          ),
        );
        if (discount == null || !mounted) return;
        final authorization =
            _canDiscount ? null : await _requestAuthorization('sale');
        if (!_canDiscount && authorization == null) return;
        await _updateFinancials(
          discount: discount,
          discountAuthorization: authorization,
        );
        return;
      case _FinancialEdit.removeDiscount:
        await _updateFinancials(discount: const QuickSaleDiscountIntent());
        return;
      case _FinancialEdit.serviceFee:
        final waiving = !_checkout.serviceFeeWaived;
        final authorization = waiving && !_canWaiveFee
            ? await _requestAuthorization('service_fee')
            : null;
        if (waiving && !_canWaiveFee && authorization == null) return;
        await _updateFinancials(
          serviceFeeWaived: waiving,
          serviceFeeAuthorization: authorization,
        );
        return;
    }
  }

  Future<void> _editItemDiscount() async {
    final item = await showModalBottomSheet<QuickSaleCheckoutItem>(
      context: context,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            const ListTile(title: Text('DESCONTO POR ITEM')),
            for (final item in _checkout.items)
              ListTile(
                title: Text(item.name),
                subtitle: Text(
                    'Quantidade: ${formatQuantity(item.quantity)} ${item.unit}'),
                onTap: () => Navigator.pop(context, item),
              ),
          ],
        ),
      ),
    );
    if (item == null || !mounted) return;
    final initial = item.input['discount'] is Map
        ? QuickSaleDiscountIntent.fromJson(
            Map<String, dynamic>.from(item.input['discount'] as Map))
        : const QuickSaleDiscountIntent();
    final discount = await showDialog<QuickSaleDiscountIntent>(
      context: context,
      builder: (_) => SharedDiscountDialog(initial: initial),
    );
    if (discount == null || !mounted) return;
    final authorization =
        _canItemDiscount ? null : await _requestAuthorization('item');
    if (!_canItemDiscount && authorization == null) return;
    final items = _checkout.items.map((entry) {
      final input = Map<String, dynamic>.from(entry.input);
      if (entry.id == item.id) input['discount'] = discount.toJson();
      return input;
    }).toList(growable: false);
    await _updateFinancials(
      items: items,
      itemDiscountAuthorization: authorization,
    );
  }

  Future<bool> _choose(QuickSalePaymentMethod method,
      {List<Map<String, dynamic>> allocations = const [],
      String? initialAmount,
      bool amountLocked = false,
      bool fromEqualSplit = false,
      int? equalSplitIndex}) async {
    final payment = await Navigator.of(context).push<PaymentEntryResult>(
      MaterialPageRoute(
        builder: (_) => PaymentEntryPage(
          method: method,
          remaining: _checkout.remainingAmount,
          initialAmount: initialAmount,
          amountLocked: allocations.isNotEmpty || amountLocked,
          amountContext: fromEqualSplit
              ? PaymentAmountContext.equalSplit
              : allocations.isNotEmpty
                  ? PaymentAmountContext.items
                  : PaymentAmountContext.value,
        ),
      ),
    );
    if (payment == null || !mounted || !_checkout.canRecordPayment) {
      return false;
    }
    final attempt = QuickSalePaymentAttempt(
      intentId: payment.intentId,
      paymentMethodId: method.id,
      mode: allocations.isEmpty ? 'value' : 'items',
      amount: payment.amount,
      receivedAmount: payment.receivedAmount,
      allocations: allocations,
    );
    return _recordPayment(
      attempt,
      preserveEqualSplit: fromEqualSplit,
      equalSplitIndex: equalSplitIndex,
    );
  }

  Future<bool> _recordPayment(QuickSalePaymentAttempt attempt,
      {bool preserveEqualSplit = false, int? equalSplitIndex}) async {
    setState(() {
      _working = true;
      _pendingPayment = attempt;
      _pendingEqualSplitIndex ??= equalSplitIndex;
    });
    final updated = await widget.controller.recordQuickSalePayment(
      checkoutId: _checkout.id,
      paymentMethodId: attempt.paymentMethodId,
      mode: attempt.mode,
      paymentIntentId: attempt.intentId,
      amount: attempt.amount,
      receivedAmount: attempt.receivedAmount,
      allocations: attempt.allocations,
    );
    if (mounted) setState(() => _working = false);
    if (updated != null && mounted) {
      _replaceCheckout(updated,
          preserveEqualSplit:
              preserveEqualSplit || _pendingEqualSplitIndex != null);
      setState(() {
        final equalSplitIndex = _pendingEqualSplitIndex;
        if (equalSplitIndex != null && _equalSplitParts != null) {
          _equalSplitParts![equalSplitIndex].paid = true;
        }
        _pendingEqualSplitIndex = null;
        _pendingPayment = null;
      });
    } else {
      await _restorePendingPayment();
    }
    return updated != null;
  }

  Future<void> _selectItems() async {
    final selection =
        await Navigator.of(context).push<PaymentAllocationSelection>(
      MaterialPageRoute(
          builder: (_) => PaymentItemAllocationPage(
                remaining: _checkout.remainingAmount,
                items: _checkout.items
                    .map((item) => PaymentAllocationItem(
                          id: item.id,
                          name: item.name,
                          quantity: item.quantity,
                          availableQuantity: item.availableQuantity,
                          unit: item.unit,
                        ))
                    .toList(growable: false),
                preview: (allocations) async {
                  final preview =
                      await widget.controller.previewQuickSalePayment(
                    checkoutId: _checkout.id,
                    allocations: allocations,
                  );
                  return preview == null
                      ? null
                      : PaymentAllocationPreview(
                          total: preview.total,
                          availableQuantities: preview.availableQuantities,
                        );
                },
              )),
    );
    if (selection == null || !mounted) return;
    final method = await _pickMethod('Forma para os itens');
    if (method != null && mounted) {
      await _choose(method,
          allocations: selection.allocations, initialAmount: selection.total);
    }
  }

  Future<void> _showSplitSelector() => showModalBottomSheet<void>(
        context: context,
        builder: (context) => PaymentSplitSelector(
          canPayByItems: _checkout.canPayByItems,
          enabled: _checkout.canRecordPayment &&
              !_working &&
              _pendingPayment == null,
          onEqualSplit: () {
            Navigator.pop(context);
            _selectEqualPart();
          },
          onItems: () {
            Navigator.pop(context);
            _selectItems();
          },
        ),
      );

  Future<QuickSalePaymentMethod?> _pickMethod(String title,
          {List<QuickSalePaymentMethod>? methods}) =>
      showModalBottomSheet<QuickSalePaymentMethod>(
        context: context,
        isScrollControlled: true,
        builder: (context) => SafeArea(
          child: ConstrainedBox(
            constraints: BoxConstraints(
                maxHeight: MediaQuery.sizeOf(context).height * .7),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(title,
                        style: Theme.of(context)
                            .textTheme
                            .titleLarge
                            ?.copyWith(fontWeight: FontWeight.w900)),
                    const SizedBox(height: 12),
                    Expanded(
                      child: ListView(
                        children: [
                          for (final method in methods ?? _methods)
                            ListTile(
                              leading: Icon(_icon(method)),
                              title: Text(method.name),
                              onTap: () => Navigator.pop(context, method),
                            ),
                        ],
                      ),
                    ),
                  ]),
            ),
          ),
        ),
      );

  Future<void> _reverse(QuickSaleCheckoutPayment payment) async {
    final reason = await showDialog<String>(
      context: context,
      builder: (_) => PaymentReversalDialog(payment: _paymentDisplay(payment)),
    );
    if (reason == null || !mounted) return;
    QuickSaleAuthorization? authorization;
    final canReverseDirectly = widget.controller.bootstrapSnapshot?.permissions
            .contains('sales.payments.reverse') ??
        false;
    if (!canReverseDirectly) {
      final authorizers =
          await widget.controller.quickSalePaymentReverseAuthorizers();
      if (!mounted || authorizers == null) return;
      if (authorizers.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content:
              Text('Nenhum autorizador elegível está disponível nesta filial.'),
        ));
        return;
      }
      authorization = await showDialog<QuickSaleAuthorization>(
        context: context,
        builder: (_) => SharedAuthorizationDialog(
          authorizers: authorizers,
          onAuthorize: (value) =>
              widget.controller.validateQuickSaleDiscountAuthorization(
            type: 'payment_reverse',
            authorization: value,
          ),
        ),
      );
      if (authorization == null || !mounted) return;
    }
    setState(() => _working = true);
    final updated = await widget.controller.reverseQuickSalePayment(
      checkoutId: _checkout.id,
      paymentId: payment.id,
      reason: reason,
      authorization: authorization,
    );
    if (mounted) setState(() => _working = false);
    if (updated != null && mounted) _replaceCheckout(updated);
  }

  Future<void> _finish() async {
    setState(() => _working = true);
    final result =
        await widget.controller.finalizeQuickSaleCheckout(_checkout.id);
    if (mounted) setState(() => _working = false);
    if (result != null && mounted) {
      await widget.onCompleted(result);
      if (mounted) Navigator.of(context).pop(result);
    }
  }

  Future<void> _cancel() async {
    if (_working) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Cancelar checkout?'),
        content:
            const Text('Os itens voltarão a ficar disponíveis para venda.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('VOLTAR')),
          FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('CANCELAR CHECKOUT')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    if (_hasAppliedPayment) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Estorne todos os pagamentos antes de cancelar a venda.'),
      ));
      return;
    }
    setState(() => _working = true);
    final cancelled =
        await widget.controller.cancelQuickSaleCheckout(_checkout.id);
    if (!mounted) return;
    setState(() => _working = false);
    if (cancelled) {
      await widget.onCancelled();
      if (mounted) Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
        canPop: !_hasAppliedPayment,
        onPopInvokedWithResult: (didPop, _) {
          if (!didPop) {
            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
              content: Text(
                  'Conclua ou estorne os pagamentos para sair desta venda.'),
            ));
          }
        },
        child: Scaffold(
          appBar: AppBar(
            title: const Text('PAGAMENTO'),
            actions: [
              PaymentHeaderActions(
                customerLabel: _checkout.customer?.name ?? 'CLIENTE',
                canEditCustomer: !_working && _checkout.canEditFinancials,
                canSplit: !_working &&
                    _pendingPayment == null &&
                    _checkout.canRecordPayment,
                onCustomer: () => _editFinancials(_FinancialEdit.customer),
                onSplit: _showSplitSelector,
                menu: PopupMenuButton<_PaymentAction>(
                  enabled: !_working,
                  tooltip: 'Editar financeiro',
                  icon: const Icon(Icons.more_vert),
                  onSelected: (action) {
                    switch (action) {
                      case _PaymentAction.cancel:
                        _cancel();
                      case _PaymentAction.removeCustomer:
                        _editFinancials(_FinancialEdit.removeCustomer);
                      case _PaymentAction.discount:
                        _editFinancials(_FinancialEdit.discount);
                      case _PaymentAction.itemDiscount:
                        _editFinancials(_FinancialEdit.itemDiscount);
                      case _PaymentAction.removeDiscount:
                        _editFinancials(_FinancialEdit.removeDiscount);
                      case _PaymentAction.serviceFee:
                        _editFinancials(_FinancialEdit.serviceFee);
                    }
                  },
                  itemBuilder: (_) => [
                    if (_checkout.canEditFinancials &&
                        _checkout.customer != null)
                      const PopupMenuItem(
                        value: _PaymentAction.removeCustomer,
                        child: Text('REMOVER CLIENTE'),
                      ),
                    if (_checkout.canEditFinancials) ...[
                      const PopupMenuItem(
                        value: _PaymentAction.discount,
                        child: Text('ALTERAR DESCONTO'),
                      ),
                      const PopupMenuItem(
                        value: _PaymentAction.itemDiscount,
                        child: Text('DESCONTO POR ITEM'),
                      ),
                      if (!_checkout.discountIntent.isZero)
                        const PopupMenuItem(
                          value: _PaymentAction.removeDiscount,
                          child: Text('REMOVER DESCONTO'),
                        ),
                      PopupMenuItem(
                        value: _PaymentAction.serviceFee,
                        child: Text(_checkout.serviceFeeWaived
                            ? 'RESTAURAR TAXA DE SERVIÇO'
                            : 'RETIRAR TAXA DE SERVIÇO'),
                      ),
                    ],
                    const PopupMenuDivider(),
                    const PopupMenuItem(
                      value: _PaymentAction.cancel,
                      child: Text('CANCELAR VENDA'),
                    ),
                  ],
                ),
              ),
            ],
          ),
          body: PaymentPageLayout(
            summary: _summaryData,
            methodGrid: _methodGrid(),
            pendingAction: _pendingPayment == null
                ? null
                : OutlinedButton.icon(
                    onPressed: _working || !_checkout.canRecordPayment
                        ? null
                        : () => _recordPayment(_pendingPayment!),
                    icon: const Icon(Icons.refresh),
                    label: const Text('TENTAR NOVAMENTE'),
                  ),
            history: _paymentHistory(),
            summaryPanel: _summary(context),
          ),
        ),
      );

  Widget _methodGrid() {
    return PaymentMethodGrid(
      methods: _methods,
      enabled:
          !_working && _pendingPayment == null && _checkout.canRecordPayment,
      onSelect: (methods) async {
        final method = methods.length == 1
            ? methods.single
            : await _pickMethod('Formas de pagamento', methods: methods);
        if (method != null && mounted) await _choose(method);
      },
    );
  }

  Future<void> _selectEqualPart() async {
    final selection = await Navigator.of(context).push<_EqualSplitSelection>(
      MaterialPageRoute(
          builder: (_) => _EqualSplitPage(
                remaining: _checkout.remainingAmount,
                initialParts: _equalSplitParts,
              )),
    );
    if (selection == null || !mounted) return;
    setState(() => _equalSplitParts = selection.parts);
    final method = await _pickMethod('Forma para esta parte');
    if (method == null || !mounted) return;
    await _choose(method,
        initialAmount: selection.amount,
        amountLocked: true,
        fromEqualSplit: true,
        equalSplitIndex: selection.index);
  }

  Widget _paymentHistory() {
    final payments = _checkout.payments
        .where((payment) => !payment.isReversal)
        .toList(growable: false);
    if (payments.isEmpty) {
      return const Center(child: Text('Nenhum pagamento registrado.'));
    }
    return ListView.separated(
      padding: EdgeInsets.zero,
      itemCount: payments.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (_, index) {
        final payment = payments[index];
        return PaymentHistoryItem(
          payment: _paymentDisplay(payment),
          reversed: _checkout.hasReversalFor(payment.id),
          working: _working,
          onReverse: () => _reverse(payment),
          reversalReason: _checkout.reversalFor(payment.id)?.reversalReason,
        );
      },
    );
  }

  Widget _summary(BuildContext context) => PaymentFinancialSummary(
        summary: _summaryData,
        showDetails: _showSummaryDetails,
        onToggleDetails: () =>
            setState(() => _showSummaryDetails = !_showSummaryDetails),
        primaryAction: _checkout.canFinalize
            ? FilledButton(
                onPressed: _working ? null : _finish,
                child: _working
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator())
                    : const Text('FINALIZAR VENDA'),
              )
            : null,
      );

  IconData _icon(QuickSalePaymentMethod method) => switch (method.kind) {
        'cash' => Icons.payments_outlined,
        'pix' => Icons.qr_code_2,
        'card' || 'credit' || 'debit' || 'benefit' => Icons.credit_card,
        _ => Icons.account_balance_wallet_outlined
      };

  PaymentDisplayEntry _paymentDisplay(QuickSaleCheckoutPayment payment) =>
      _adapter.payment(payment);

  PaymentSummaryData get _summaryData => _adapter.summary;

  QuickSalePaymentAdapter get _adapter => QuickSalePaymentAdapter(_checkout);
}

enum _FinancialEdit {
  customer,
  removeCustomer,
  discount,
  itemDiscount,
  removeDiscount,
  serviceFee
}

enum _PaymentAction {
  cancel,
  removeCustomer,
  discount,
  itemDiscount,
  removeDiscount,
  serviceFee,
}

class _PaymentIntent {
  const _PaymentIntent(
      this.intentId, this.amount, this.receivedAmount, this.allocations);
  final String intentId;
  final String amount;
  final String? receivedAmount;
  final List<Map<String, dynamic>> allocations;
}

enum _PaymentAmountContext { value, items, equalSplit }

class _PaymentEntryPage extends StatefulWidget {
  const _PaymentEntryPage({
    required this.method,
    required this.remaining,
    required this.controller,
    required this.checkout,
    required this.allocations,
    required this.amountLocked,
    required this.amountContext,
  });
  final QuickSalePaymentMethod method;
  final String remaining;
  final AppController controller;
  final QuickSaleCheckout checkout;
  final List<Map<String, dynamic>> allocations;
  final bool amountLocked;
  final _PaymentAmountContext amountContext;
  @override
  State<_PaymentEntryPage> createState() => _PaymentEntryPageState();
}

class _PaymentEntryPageState extends State<_PaymentEntryPage> {
  late final String _intentId = createIdempotencyKey();
  late final _MoneyEntry _amount = _MoneyEntry('0.00');
  late final _MoneyEntry _received = _MoneyEntry('0.00');
  bool _receiving = false;
  bool get _editingAmount => !widget.amountLocked || _receiving;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(widget.method.name)),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('FALTA ${formatMoney(widget.remaining)}',
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 14),
                  Text(
                    _receiving
                        ? 'VALOR RECEBIDO'
                        : switch (widget.amountContext) {
                            _PaymentAmountContext.items =>
                              'VALOR OFICIAL DOS ITENS',
                            _PaymentAmountContext.equalSplit =>
                              'VALOR DA PARTE',
                            _PaymentAmountContext.value => 'VALOR APLICADO',
                          },
                    textAlign: TextAlign.center,
                  ),
                  Text(
                    formatMoney((_receiving ? _received : _amount).value),
                    textAlign: TextAlign.center,
                    style: Theme.of(context)
                        .textTheme
                        .displaySmall
                        ?.copyWith(fontWeight: FontWeight.w900),
                  ),
                  if (widget.method.isCash) ...[
                    SwitchListTile(
                      title: const Text('Informar valor recebido'),
                      value: _receiving,
                      onChanged: (value) => setState(() => _receiving = value),
                    ),
                    if (_receiving)
                      Text('Troco: ${formatMoney(_received.subtract(_amount))}',
                          textAlign: TextAlign.center),
                  ],
                  const SizedBox(height: 10),
                  Wrap(alignment: WrapAlignment.center, spacing: 8, children: [
                    for (final value in ['5.00', '10.00', '20.00', '50.00'])
                      OutlinedButton(
                        onPressed: !_editingAmount
                            ? null
                            : () => setState(() =>
                                (_receiving ? _received : _amount).set(value)),
                        child: Text('R\$ ${value.split('.').first}'),
                      ),
                    OutlinedButton(
                      onPressed: widget.amountLocked
                          ? null
                          : () => setState(() => _amount.set(widget.remaining)),
                      child: const Text('PAGAR SALDO'),
                    ),
                  ]),
                  const Spacer(),
                  if (_editingAmount) _keypad(),
                  const SizedBox(height: 14),
                  FilledButton(
                    onPressed: _valid
                        ? () => Navigator.pop(
                            context,
                            _PaymentIntent(
                              _intentId,
                              _amount.value,
                              widget.method.isCash
                                  ? (_receiving
                                      ? _received.value
                                      : _amount.value)
                                  : null,
                              widget.allocations,
                            ))
                        : null,
                    child: const Text('CONFIRMAR PAGAMENTO MANUAL'),
                  ),
                ]),
          ),
        ),
      );
  bool get _valid =>
      _amount.cents > 0 &&
      _amount.cents <= _MoneyEntry.centsFor(widget.remaining) &&
      (!widget.method.isCash ||
          !_receiving ||
          _received.cents >= _amount.cents);
  Widget _keypad() => GridView.count(
          crossAxisCount: 3,
          shrinkWrap: true,
          childAspectRatio: 1.6,
          children: [
            for (final digit in [
              '1',
              '2',
              '3',
              '4',
              '5',
              '6',
              '7',
              '8',
              '9',
              '00',
              '0'
            ])
              OutlinedButton(
                  onPressed: () => setState(
                      () => (_receiving ? _received : _amount).append(digit)),
                  child: Text(digit, style: const TextStyle(fontSize: 22))),
            OutlinedButton(
                onPressed: () => setState(
                    () => (_receiving ? _received : _amount).backspace()),
                child: const Icon(Icons.backspace_outlined)),
          ]);
}

class _MoneyEntry {
  _MoneyEntry(String value) : cents = centsFor(value);
  int cents;
  static int centsFor(String value) {
    final bits = value.replaceAll(',', '.').split('.');
    return (int.tryParse(bits.first) ?? 0) * 100 +
        int.parse((bits.length > 1 ? '${bits[1]}00' : '00').substring(0, 2));
  }

  String get value =>
      '${(cents ~/ 100)}.${(cents % 100).toString().padLeft(2, '0')}';
  void set(String value) => cents = centsFor(value);
  void append(String digits) => cents = int.parse('$cents$digits');
  void backspace() => cents ~/= 10;
  String subtract(_MoneyEntry other) => cents >= other.cents
      ? '${((cents - other.cents) ~/ 100)}.${((cents - other.cents) % 100).toString().padLeft(2, '0')}'
      : '0.00';
}

class _ItemAllocationPage extends StatefulWidget {
  const _ItemAllocationPage({required this.checkout, required this.controller});
  final QuickSaleCheckout checkout;
  final AppController controller;
  @override
  State<_ItemAllocationPage> createState() => _ItemAllocationPageState();
}

class _ItemAllocationPageState extends State<_ItemAllocationPage> {
  // Quantities use thousandths, matching the checkout allocation precision.
  final Map<int, int> _quantities = {};
  final Map<int, TextEditingController> _quantityInputs = {};
  final Map<int, String> _quantityErrors = {};
  QuickSalePaymentPreview? _preview;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    for (final item in widget.checkout.items) {
      _quantityInputs[item.id] = TextEditingController(text: '0');
    }
  }

  @override
  void dispose() {
    for (final controller in _quantityInputs.values) {
      controller.dispose();
    }
    super.dispose();
  }

  List<Map<String, dynamic>> get _allocations => _quantities.entries
      .where((entry) => entry.value > 0)
      .map((entry) => {
            'item': entry.key,
            'allocated_quantity': _quantityValue(entry.value)
          })
      .toList(growable: false);

  bool get _previewExceedsRemaining =>
      _preview != null &&
      _MoneyEntry.centsFor(_preview!.total) >
          _MoneyEntry.centsFor(widget.checkout.remainingAmount);

  bool get _canContinue =>
      _preview != null &&
      !_loading &&
      _quantityErrors.isEmpty &&
      _MoneyEntry.centsFor(_preview!.total) > 0 &&
      !_previewExceedsRemaining;

  Future<void> _update() async {
    if (_quantityErrors.isNotEmpty) return;
    final rows = _allocations;
    if (rows.isEmpty) {
      setState(() => _preview = null);
      return;
    }
    setState(() => _loading = true);
    final preview = await widget.controller.previewQuickSalePayment(
      checkoutId: widget.checkout.id,
      allocations: rows,
    );
    if (mounted) {
      setState(() {
        _loading = false;
        _preview = preview;
      });
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Pagar por itens')),
        body: ListView(padding: const EdgeInsets.all(20), children: [
          for (final item in widget.checkout.items) _item(item),
          if (_preview != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('TOTAL OFICIAL ${formatMoney(_preview!.total)}',
                      style: const TextStyle(fontWeight: FontWeight.w900)),
                  if (_previewExceedsRemaining) ...[
                    const SizedBox(height: 8),
                    Text(
                        'Os itens selecionados somam ${formatMoney(_preview!.total)}, mas faltam ${formatMoney(widget.checkout.remainingAmount)}.'),
                    const Text(
                        'Reduza os itens selecionados ou pague o saldo restante por valor.'),
                  ],
                ],
              ),
            ),
          FilledButton(
            onPressed: !_canContinue
                ? null
                : () => Navigator.pop(context,
                    _ItemPaymentSelection(_allocations, _preview!.total)),
            child: const Text('CONTINUAR'),
          ),
        ]),
      );

  Widget _item(QuickSaleCheckoutItem item) {
    final max = _quantityUnits(
        _preview?.availableQuantities[item.id] ?? item.availableQuantity);
    final step = item.unit.toLowerCase() == 'un' ? 1000 : 1;
    final value = _quantities[item.id] ?? 0;
    final input = _quantityInputs[item.id]!;
    final error = _quantityErrors[item.id];
    void setValue(int next) {
      setState(() {
        _quantities[item.id] = next;
        _quantityErrors.remove(item.id);
        input.text = formatQuantity(_quantityValue(next));
      });
      _update();
    }

    return Card(
      child: ListTile(
        title: Text(item.name),
        subtitle: Text(error ??
            'Disponível: ${formatQuantity(_quantityValue(max))} ${item.unit}'),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          IconButton(
            onPressed:
                _loading || value == 0 ? null : () => setValue(value - step),
            icon: const Icon(Icons.remove),
          ),
          SizedBox(
            width: 72,
            child: TextField(
              controller: input,
              enabled: !_loading,
              textAlign: TextAlign.center,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [
                TextInputFormatter.withFunction((oldValue, newValue) =>
                    RegExp(r'^\d*(?:[\.,]\d{0,3})?$').hasMatch(newValue.text)
                        ? newValue
                        : oldValue),
              ],
              onChanged: (text) {
                final validSyntax =
                    RegExp(r'^\d*(?:[\.,]\d{0,3})?$').hasMatch(text);
                final next = _quantityUnits(text);
                final validUnit =
                    item.unit.toLowerCase() != 'un' || next % 1000 == 0;
                if (validSyntax && validUnit && next <= max) {
                  setState(() {
                    _quantities[item.id] = next;
                    _quantityErrors.remove(item.id);
                    _preview = null;
                  });
                } else {
                  setState(() {
                    _preview = null;
                    _quantityErrors[item.id] = validUnit
                        ? 'Informe até ${_quantityValue(max)} ${item.unit}.'
                        : 'Produtos por unidade exigem quantidade inteira.';
                  });
                }
              },
              onEditingComplete: _update,
            ),
          ),
          IconButton(
            onPressed: _loading || value + step > max
                ? null
                : () => setValue(value + step),
            icon: const Icon(Icons.add),
          ),
        ]),
      ),
    );
  }
}

class _ItemPaymentSelection {
  const _ItemPaymentSelection(this.allocations, this.total);
  final List<Map<String, dynamic>> allocations;
  final String total;
}

int _quantityUnits(String value) {
  final bits = value.replaceAll(',', '.').split('.');
  final whole = int.tryParse(bits.first) ?? 0;
  final fraction = bits.length > 1 ? bits[1] : '';
  return whole * 1000 + (int.tryParse('${fraction}000'.substring(0, 3)) ?? 0);
}

String _quantityValue(int thousandths) {
  final whole = thousandths ~/ 1000;
  final fraction = (thousandths % 1000)
      .toString()
      .padLeft(3, '0')
      .replaceFirst(RegExp(r'0+$'), '');
  return fraction.isEmpty ? '$whole' : '$whole.$fraction';
}

class _EqualSplitPart {
  _EqualSplitPart(this.cents, {this.paid = false});
  final int cents;
  bool paid;

  _EqualSplitPart copy() => _EqualSplitPart(cents, paid: paid);
  String get amount =>
      '${cents ~/ 100}.${(cents % 100).toString().padLeft(2, '0')}';
}

class _EqualSplitSelection {
  const _EqualSplitSelection(this.parts, this.index);
  final List<_EqualSplitPart> parts;
  final int index;
  String get amount => parts[index].amount;
}

class _EqualSplitPage extends StatefulWidget {
  const _EqualSplitPage({required this.remaining, this.initialParts});
  final String remaining;
  final List<_EqualSplitPart>? initialParts;
  @override
  State<_EqualSplitPage> createState() => _EqualSplitPageState();
}

class _EqualSplitPageState extends State<_EqualSplitPage> {
  late List<_EqualSplitPart> _parts;
  late int _people;

  @override
  void initState() {
    super.initState();
    _parts = widget.initialParts?.map((part) => part.copy()).toList() ??
        _partsFor(_MoneyEntry.centsFor(widget.remaining), 2);
    _people = _parts.length;
  }

  List<_EqualSplitPart> _partsFor(int cents, int people) {
    final base = cents ~/ people;
    final remainder = cents % people;
    return List.generate(
        people, (index) => _EqualSplitPart(base + (index < remainder ? 1 : 0)));
  }

  @override
  Widget build(BuildContext context) {
    final hasPaidPart = _parts.any((part) => part.paid);
    final total = _parts.fold(0, (sum, part) => sum + part.cents);
    return Scaffold(
      appBar: AppBar(title: const Text('Dividir igual')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(children: [
          Text('DIVIDIR ENTRE: $_people'),
          Slider(
            value: _people.toDouble(),
            min: 2,
            max: 12,
            divisions: 10,
            label: '$_people',
            onChanged: hasPaidPart
                ? null
                : (value) => setState(() {
                      _people = value.round();
                      _parts = _partsFor(total, _people);
                    }),
          ),
          Text(
              'Total: ${formatMoney('${total ~/ 100}.${(total % 100).toString().padLeft(2, '0')}')}'),
          const SizedBox(height: 12),
          Expanded(
            child: ListView.builder(
              itemCount: _parts.length,
              itemBuilder: (context, index) {
                final part = _parts[index];
                return Card(
                  child: ListTile(
                    title: Text('Parte ${index + 1}'),
                    subtitle: Text(part.paid ? 'Paga' : 'Selecione esta parte'),
                    trailing: Text(formatMoney(part.amount),
                        style: const TextStyle(fontWeight: FontWeight.w900)),
                    onTap: part.paid || part.cents == 0
                        ? null
                        : () => Navigator.pop(
                            context, _EqualSplitSelection(_parts, index)),
                  ),
                );
              },
            ),
          ),
        ]),
      ),
    );
  }
}
