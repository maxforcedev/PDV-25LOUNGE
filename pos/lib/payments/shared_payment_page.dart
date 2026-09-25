import 'dart:async';

import 'package:flutter/material.dart';

import '../cash/cash_models.dart' show createIdempotencyKey;
import '../core/app_controller.dart';
import '../printing/models.dart';
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
  bool _checkoutCancelled = false;
  bool _allowPop = false;

  List<QuickSalePaymentMethod> get _methods => widget.options.paymentMethods;
  List<PaymentEqualSplitPart>? _equalSplitParts;
  QuickSalePaymentAttempt? _pendingPayment;
  int? _pendingEqualSplitIndex;
  bool _showSummaryDetails = false;
  final Map<String, PrintDocumentResult> _paymentDocuments = {};
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
    for (final payment in _checkout.payments) {
      if (payment.printDocument != null) {
        _paymentDocuments[payment.id] = payment.printDocument!;
      }
    }
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
      for (final payment in checkout.payments) {
        if (payment.printDocument != null) {
          _paymentDocuments[payment.id] = payment.printDocument!;
        }
      }
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
      customerId: clearCustomer ? null : (customer ?? _checkout.customer)?.id,
      discount: (discount ?? _checkout.discountIntent).toJson(),
      serviceFeeWaived: serviceFeeWaived ?? _checkout.serviceFeeWaived,
      discountAuthorization: discountAuthorization,
      itemDiscountAuthorization: itemDiscountAuthorization,
      serviceFeeAuthorization: serviceFeeAuthorization,
    );
    if (mounted) setState(() => _working = false);
    if (updated != null && mounted) {
      _replaceCheckout(updated);
    } else {
      final recovered = widget.controller.takeRecoveredQuickSaleResult();
      if (recovered != null && mounted) {
        await widget.onCompleted(recovered);
        if (mounted) Navigator.of(context).pop(recovered);
      }
    }
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
                          name: item.name,
                          quantity: item.quantity,
                          unit: item.unit,
                          sources: [
                            PaymentAllocationSource(
                              itemId: item.id,
                              quantity: item.quantity,
                              availableQuantity: item.availableQuantity,
                            ),
                          ],
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
    final method = await PaymentMethodPicker.show(
      context,
      title: 'Forma para os itens',
      methods: _methods,
    );
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

  Future<void> _reverse(QuickSaleCheckoutPayment payment) async {
    if (_checkout.status != 'open') {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('A venda já foi concluída. Use o cancelamento da venda, não o estorno do checkout.'),
      ));
      return;
    }
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

  Future<void> _printPaymentReceipt(QuickSaleCheckoutPayment payment) async {
    if (_working || payment.isReversal) return;
    setState(() => _working = true);
    final document = _paymentDocuments[payment.id];
    if (document?.awaitingInitialPrint == true) {
      setState(() => _working = false);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('A impressão inicial ainda está pendente.')));
      return;
    }
    final result = document?.canReprint == true
        ? await widget.controller.reprintPrintDocument(
            PrintDocumentReprintRequest(
              documentId: document!.id!, idempotencyKey: createIdempotencyKey(),
              reason: 'Reimpressão de comprovante de pagamento',
            ),
          )
        : await widget.controller.requestPrintDocument(
            PrintDocumentRequest(
              type: PrintDocumentType.paymentReceipt,
              sourceType: 'quick_sale_payment', sourceId: payment.id,
              idempotencyKey: createIdempotencyKey(),
            ),
          );
    if (!mounted) return;
    setState(() {
      _working = false;
      if (result != null) _paymentDocuments[payment.id] = result;
    });
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
      _checkoutCancelled = true;
      await widget.onCancelled();
      if (mounted) {
        setState(() => _allowPop = true);
        Navigator.of(context).pop();
      }
    }
  }

  Future<void> _cancelAbandonedCheckout() async {
    if (_checkoutCancelled || _hasAppliedPayment) return;
    setState(() => _working = true);
    final cancelled = await widget.controller.cancelQuickSaleCheckout(_checkout.id);
    if (!mounted) return;
    setState(() => _working = false);
    if (!cancelled) return;
    _checkoutCancelled = true;
    await widget.onCancelled();
    if (mounted) {
      setState(() => _allowPop = true);
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) => PopScope(
        canPop: _allowPop,
        onPopInvokedWithResult: (didPop, _) async {
          if (didPop || _working) return;
          if (_hasAppliedPayment) {
            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
              content: Text(
                  'Conclua ou estorne os pagamentos para sair desta venda.'),
            ));
          } else {
            await _cancelAbandonedCheckout();
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
            : await PaymentMethodPicker.show(
                context,
                title: 'Formas de pagamento',
                methods: methods,
              );
        if (method != null && mounted) await _choose(method);
      },
    );
  }

  Future<void> _selectEqualPart() async {
    final selection =
        await Navigator.of(context).push<PaymentEqualSplitSelection>(
      MaterialPageRoute(
          builder: (_) => PaymentEqualSplitPage(
                remaining: _checkout.remainingAmount,
                initialParts: _equalSplitParts,
              )),
    );
    if (selection == null || !mounted) return;
    setState(() => _equalSplitParts = selection.parts!);
    final method = await PaymentMethodPicker.show(
      context,
      title: 'Forma para esta parte',
      methods: _methods,
    );
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
    return PaymentHistoryList(
      entries: payments
          .map((payment) => PaymentHistoryEntry(
                payment: _paymentDisplay(payment),
                reversed: _checkout.hasReversalFor(payment.id),
                reversalReason:
                    _checkout.reversalFor(payment.id)?.reversalReason,
                working: _working,
                onReverse: _checkout.status == 'open' ? () => _reverse(payment) : null,
                onPrint: _working ? null : () => _printPaymentReceipt(payment),
                printTooltip: _paymentDocuments[payment.id]?.printActionLabel ?? 'IMPRIMIR COMPROVANTE',
              ))
          .toList(growable: false),
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
