import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../sales/sale_models.dart';
import '../sales/shared_authorization_dialog.dart';
import '../sales/shared_customer_dialog.dart';
import '../sales/shared_discount_dialog.dart';
import '../sales/shared_pos_widgets.dart';

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
  List<QuickSalePaymentMethod> get _cards => _methods
      .where((method) => method.visualGroup == 'card')
      .toList(growable: false);
  List<QuickSalePaymentMethod> get _cash => _methods
      .where((method) => method.kind == 'cash' || method.visualGroup == 'cash')
      .toList(growable: false);
  List<QuickSalePaymentMethod> get _pix => _methods
      .where((method) => method.kind == 'pix' || method.visualGroup == 'pix')
      .toList(growable: false);
  List<QuickSalePaymentMethod> get _others => _methods
      .where((method) =>
          !_cash.contains(method) &&
          !_cards.contains(method) &&
          !_pix.contains(method))
      .toList(growable: false);
  List<_EqualSplitPart>? _equalSplitParts;
  QuickSalePaymentAttempt? _pendingPayment;
  int? _pendingEqualSplitIndex;
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
                subtitle: Text('Quantidade: ${item.quantity} ${item.unit}'),
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
    final payment = await Navigator.of(context).push<_PaymentIntent>(
      MaterialPageRoute(
        builder: (_) => _PaymentEntryPage(
          method: method,
          remaining: _checkout.remainingAmount,
          controller: widget.controller,
          checkout: _checkout,
          allocations: allocations,
          initialAmount: initialAmount,
          amountLocked: allocations.isNotEmpty || amountLocked,
          amountContext: fromEqualSplit
              ? _PaymentAmountContext.equalSplit
              : allocations.isNotEmpty
                  ? _PaymentAmountContext.items
                  : _PaymentAmountContext.value,
        ),
      ),
    );
    if (payment == null || !mounted || !_checkout.canRecordPayment) {
      return false;
    }
    final attempt = QuickSalePaymentAttempt(
      intentId: payment.intentId,
      paymentMethodId: method.id,
      mode: payment.allocations.isEmpty ? 'value' : 'items',
      amount: payment.amount,
      receivedAmount: payment.receivedAmount,
      allocations: payment.allocations,
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
    final selection = await Navigator.of(context).push<_ItemPaymentSelection>(
      MaterialPageRoute(
          builder: (_) => _ItemAllocationPage(
              checkout: _checkout, controller: widget.controller)),
    );
    if (selection == null || !mounted) return;
    final method = await _pickMethod('Forma para os itens');
    if (method != null && mounted) {
      await _choose(method,
          allocations: selection.allocations, initialAmount: selection.total);
    }
  }

  Future<QuickSalePaymentMethod?> _pickMethod(String title,
          {List<QuickSalePaymentMethod>? methods}) =>
      showModalBottomSheet<QuickSalePaymentMethod>(
        context: context,
        builder: (context) => SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(title,
                      style: Theme.of(context)
                          .textTheme
                          .titleLarge
                          ?.copyWith(fontWeight: FontWeight.w900)),
                  const SizedBox(height: 12),
                  for (final method in methods ?? _methods)
                    ListTile(
                      leading: Icon(_icon(method)),
                      title: Text(method.name),
                      onTap: () => Navigator.pop(context, method),
                    ),
                ]),
          ),
        ),
      );

  Future<void> _reverse(QuickSaleCheckoutPayment payment) async {
    setState(() => _working = true);
    final updated = await widget.controller.reverseQuickSalePayment(
        checkoutId: _checkout.id, paymentId: payment.id);
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
      if (mounted) Navigator.of(context).pop();
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
            title: const Text('Pagamento'),
            actions: [
              TextButton(
                onPressed: _working ? null : _cancel,
                child: const Text('CANCELAR'),
              ),
              if (_checkout.canEditFinancials)
                PopupMenuButton<_FinancialEdit>(
                  enabled: !_working,
                  tooltip: 'Editar financeiro',
                  icon: const Icon(Icons.more_vert),
                  onSelected: _editFinancials,
                  itemBuilder: (_) => [
                    const PopupMenuItem(
                      value: _FinancialEdit.customer,
                      child: Text('ALTERAR CLIENTE'),
                    ),
                    if (_checkout.customer != null)
                      const PopupMenuItem(
                        value: _FinancialEdit.removeCustomer,
                        child: Text('REMOVER CLIENTE'),
                      ),
                    const PopupMenuItem(
                      value: _FinancialEdit.discount,
                      child: Text('ALTERAR DESCONTO'),
                    ),
                    const PopupMenuItem(
                      value: _FinancialEdit.itemDiscount,
                      child: Text('DESCONTO POR ITEM'),
                    ),
                    if (!_checkout.discountIntent.isZero)
                      const PopupMenuItem(
                        value: _FinancialEdit.removeDiscount,
                        child: Text('REMOVER DESCONTO'),
                      ),
                    PopupMenuItem(
                      value: _FinancialEdit.serviceFee,
                      child: Text(_checkout.serviceFeeWaived
                          ? 'RESTAURAR TAXA DE SERVIÇO'
                          : 'RETIRAR TAXA DE SERVIÇO'),
                    ),
                  ],
                ),
            ],
          ),
          body: SafeArea(
            child: LayoutBuilder(builder: (context, constraints) {
              final content = _content(context);
              return constraints.maxWidth >= 960
                  ? Row(children: [
                      Expanded(child: content),
                      SizedBox(width: 350, child: _summary(context))
                    ])
                  : Column(
                      children: [Expanded(child: content), _summary(context)]);
            }),
          ),
        ),
      );

  Widget _content(BuildContext context) => ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text('FALTA', style: Theme.of(context).textTheme.labelLarge),
          Text(formatMoney(_checkout.remainingAmount),
              style: Theme.of(context).textTheme.displaySmall?.copyWith(
                  fontWeight: FontWeight.w900, color: const Color(0xff3454d1))),
          if (!_checkout.canEditFinancials) ...[
            const SizedBox(height: 8),
            const Text(
                'Edição financeira bloqueada após o primeiro pagamento.'),
          ],
          const SizedBox(height: 20),
          const Text('FORMAS DE PAGAMENTO',
              style: TextStyle(fontWeight: FontWeight.w900)),
          const SizedBox(height: 10),
          _methodGrid(),
          if (_pendingPayment != null) ...[
            const SizedBox(height: 12),
            const Text('Há um pagamento aguardando confirmação.'),
            OutlinedButton.icon(
              onPressed: _working || !_checkout.canRecordPayment
                  ? null
                  : () => _recordPayment(_pendingPayment!),
              icon: const Icon(Icons.refresh),
              label: const Text('TENTAR NOVAMENTE'),
            ),
          ],
          const SizedBox(height: 12),
          Wrap(spacing: 8, children: [
            OutlinedButton.icon(
                onPressed: _working ||
                        _pendingPayment != null ||
                        !_checkout.canRecordPayment
                    ? null
                    : _selectItems,
                icon: const Icon(Icons.format_list_bulleted),
                label: const Text('PAGAR POR ITENS')),
            OutlinedButton.icon(
                onPressed: _working ||
                        _pendingPayment != null ||
                        !_checkout.canRecordPayment
                    ? null
                    : _selectEqualPart,
                icon: const Icon(Icons.call_split),
                label: const Text('DIVIDIR IGUAL')),
          ]),
          const SizedBox(height: 24),
          const Text('PAGAMENTOS REALIZADOS',
              style: TextStyle(fontWeight: FontWeight.w900)),
          const SizedBox(height: 8),
          if (_checkout.payments.isEmpty)
            const Text('Nenhum pagamento registrado.'),
          for (final payment in _checkout.payments) _history(payment),
        ],
      );

  Widget _methodGrid() {
    final directStandardMethods = _methods.length == 4 &&
        _cash.length == 1 &&
        _pix.length == 1 &&
        _cards.length == 2 &&
        _cards.any((method) => method.kind == 'credit') &&
        _cards.any((method) => method.kind == 'debit');
    final top = <_MethodTile>[
      if (directStandardMethods)
        for (final method in [
          _cash.single,
          _cards.firstWhere((method) => method.kind == 'credit'),
          _cards.firstWhere((method) => method.kind == 'debit'),
          _pix.single,
        ])
          _MethodTile(method.name, _icon(method), () => _choose(method))
      else ...[
        if (_cash.isNotEmpty)
          _groupTile('Dinheiro', Icons.payments_outlined, _cash),
        if (_cards.isNotEmpty) _groupTile('Cartão', Icons.credit_card, _cards),
        if (_pix.isNotEmpty) _groupTile('PIX', Icons.qr_code_2, _pix),
        if (_others.isNotEmpty) _groupTile('Outros', Icons.more_horiz, _others),
      ],
    ];
    return GridView.count(
      crossAxisCount: MediaQuery.sizeOf(context).width < 520 ? 2 : 4,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      childAspectRatio: 1.7,
      children: top
          .map((tile) => Card(
              child: InkWell(
                  onTap: _working ||
                          _pendingPayment != null ||
                          !_checkout.canRecordPayment
                      ? null
                      : tile.onTap,
                  child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(tile.icon),
                        const SizedBox(height: 5),
                        Text(tile.label,
                            style: const TextStyle(fontWeight: FontWeight.w800))
                      ]))))
          .toList(),
    );
  }

  _MethodTile _groupTile(
          String label, IconData icon, List<QuickSalePaymentMethod> methods) =>
      _MethodTile(label, icon, () async {
        final method = methods.length == 1
            ? methods.single
            : await _pickMethod('Formas de pagamento', methods: methods);
        if (method != null && mounted) await _choose(method);
      });

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

  Widget _history(QuickSaleCheckoutPayment payment) {
    final reversed = payment.isReversal || _checkout.hasReversalFor(payment.id);
    final subtitle = payment.isReversal
        ? 'Estorno'
        : reversed
            ? 'Estornado'
            : payment.receivedAmount == null
                ? 'Confirmado'
                : 'Recebido ${formatMoney(payment.receivedAmount!)}  Troco ${formatMoney(payment.changeAmount ?? '0.00')}';
    return Card(
      child: ListTile(
        leading: Icon(reversed ? Icons.undo : Icons.check_circle_outline,
            color: reversed ? Colors.red : const Color(0xff16803c)),
        title: Text(payment.methodName),
        subtitle: Text(subtitle),
        trailing: reversed || !_checkout.canReversePayment
            ? Text(formatMoney(payment.amount))
            : Row(mainAxisSize: MainAxisSize.min, children: [
                Text(formatMoney(payment.amount)),
                IconButton(
                    onPressed: _working ? null : () => _reverse(payment),
                    tooltip: 'Estornar',
                    icon: const Icon(Icons.undo))
              ]),
      ),
    );
  }

  Widget _summary(BuildContext context) => Material(
        color: Colors.white,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text('RESUMO',
                    style: TextStyle(fontWeight: FontWeight.w900)),
                const SizedBox(height: 12),
                SharedTotalsPanel(lines: [
                  SharedTotalsLine(
                      label: 'Subtotal', value: _checkout.preview.subtotal),
                  SharedTotalsLine(
                      label: 'Promoções',
                      value: _checkout.preview.promotionDiscountTotal,
                      negative: true),
                  SharedTotalsLine(
                      label: 'Descontos por item',
                      value: _checkout.preview.itemDiscountTotal,
                      negative: true),
                  SharedTotalsLine(
                      label: 'Desconto da venda',
                      value: _checkout.preview.discount,
                      negative: true),
                  SharedTotalsLine(
                      label: 'Taxa de serviço',
                      value: _checkout.preview.serviceFeeAmount),
                  SharedTotalsLine(
                      label: 'Total',
                      value: _checkout.preview.total,
                      strong: true),
                  SharedTotalsLine(label: 'Pago', value: _checkout.paidAmount),
                  SharedTotalsLine(
                      label: 'Falta',
                      value: _checkout.remainingAmount,
                      strong: true),
                ]),
                const SizedBox(height: 16),
                if (_checkout.canFinalize)
                  FilledButton(
                      onPressed: _working ? null : _finish,
                      child: _working
                          ? const CircularProgressIndicator()
                          : const Text('FINALIZAR VENDA')),
              ]),
        ),
      );

  IconData _icon(QuickSalePaymentMethod method) => switch (method.kind) {
        'cash' => Icons.payments_outlined,
        'pix' => Icons.qr_code_2,
        'card' || 'credit' || 'debit' || 'benefit' => Icons.credit_card,
        _ => Icons.account_balance_wallet_outlined
      };
}

class _MethodTile {
  const _MethodTile(this.label, this.icon, this.onTap);
  final String label;
  final IconData icon;
  final VoidCallback onTap;
}

enum _FinancialEdit {
  customer,
  removeCustomer,
  discount,
  itemDiscount,
  removeDiscount,
  serviceFee
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
    this.initialAmount,
  });
  final QuickSalePaymentMethod method;
  final String remaining;
  final AppController controller;
  final QuickSaleCheckout checkout;
  final List<Map<String, dynamic>> allocations;
  final String? initialAmount;
  final bool amountLocked;
  final _PaymentAmountContext amountContext;
  @override
  State<_PaymentEntryPage> createState() => _PaymentEntryPageState();
}

class _PaymentEntryPageState extends State<_PaymentEntryPage> {
  late final String _intentId = createIdempotencyKey();
  late final _MoneyEntry _amount = _MoneyEntry(widget.initialAmount ?? '0.00');
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
      _MoneyEntry.centsFor(_preview!.total) > 0 &&
      !_previewExceedsRemaining;

  Future<void> _update() async {
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
        input.text = _quantityValue(next);
      });
      _update();
    }

    return Card(
      child: ListTile(
        title: Text(item.name),
        subtitle:
            Text(error ?? 'Disponível: ${_quantityValue(max)} ${item.unit}'),
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
