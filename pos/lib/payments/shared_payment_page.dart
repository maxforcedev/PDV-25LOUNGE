import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../cash/cash_models.dart' show createIdempotencyKey;
import '../core/app_controller.dart';
import '../network/pos_api_error.dart';
import '../sales/sale_models.dart';
import '../sales/sale_presentation.dart';
import '../sales/shared_authorization_dialog.dart';
import '../sales/shared_customer_dialog.dart';
import '../sales/shared_discount_dialog.dart';
import 'payment_contract.dart';
import 'cielo_payment_bridge.dart';
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
  final CieloPaymentBridge _cieloBridge = CieloPaymentBridge();
  StreamSubscription<CieloPaymentCallback>? _cieloCallbacks;
  String? _activeProviderAttemptId;
  String? _activeProviderReversalOperationId;
  CieloPaymentCallback? _pendingCieloCallback;
  bool _resolvingProviderCallback = false;
  bool _checkingNativeCallback = false;
  final Set<String> _shownProviderResultDialogs = {};
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
    _cieloCallbacks = _cieloBridge.callbacks.listen(_receiveCieloCallback);
    _schedulePendingProviderCallback();
  }

  @override
  void dispose() {
    _cieloCallbacks?.cancel();
    _cieloBridge.dispose();
    super.dispose();
  }

  QuickSalePaymentIntegration? get _providerPayment =>
      _checkout.paymentIntegration;
  bool get _hasBlockingProviderPayment =>
      (_providerPayment != null &&
          _providerPayment!.intentStatus != 'cancelled') ||
      _checkout.payments
          .any((payment) => payment.providerReversal?.isBlocking == true);

  String? get _expectedProviderAttemptId =>
      _providerPayment?.attemptId ?? _activeProviderAttemptId;

  bool _isExpectedCieloCallback(CieloPaymentCallback callback) {
    if (callback.isPayment) {
      return callback.operationId == _expectedProviderAttemptId;
    }
    if (!callback.isReversal) return false;
    return callback.operationId == _activeProviderReversalOperationId ||
        _checkout.payments.any(
            (payment) => payment.providerReversal?.id == callback.operationId);
  }

  void _receiveCieloCallback(CieloPaymentCallback callback) {
    debugPrint(
        'CIELO_CALLBACK received operation=${callback.operation} operation_id=${callback.operationId} response_present=${callback.response.isNotEmpty} response_length=${callback.response.length} expected_match=${_isExpectedCieloCallback(callback)}');
    if (!_isExpectedCieloCallback(callback)) return;
    _pendingCieloCallback = callback;
    debugPrint(
        'CIELO_CALLBACK stored operation=${callback.operation} operation_id=${callback.operationId}');
    if (mounted) setState(() {});
    _schedulePendingProviderCallback();
  }

  void _schedulePendingProviderCallback() {
    if (_working || _resolvingProviderCallback || _checkingNativeCallback) {
      return;
    }
    unawaited(_drainPendingProviderCallback());
  }

  Future<void> _drainPendingProviderCallback() async {
    if (_working || _resolvingProviderCallback) return;
    if (_pendingCieloCallback == null && !_checkingNativeCallback) {
      _checkingNativeCallback = true;
      try {
        final callback = await _cieloBridge.getPendingCallback();
        if (callback != null && _isExpectedCieloCallback(callback)) {
          _pendingCieloCallback = callback;
          debugPrint(
              'CIELO_CALLBACK pending_native operation=${callback.operation} operation_id=${callback.operationId}');
          if (mounted) setState(() {});
        }
      } on PlatformException catch (error) {
        debugPrint('CIELO_CALLBACK pending_native_failed code=${error.code}');
        // The bridge is unavailable outside Android Cielo devices.
      } finally {
        _checkingNativeCallback = false;
      }
    }
    final callback = _pendingCieloCallback;
    if (callback == null || !_isExpectedCieloCallback(callback) || _working) {
      return;
    }
    _resolvingProviderCallback = true;
    if (mounted) setState(() => _working = true);
    try {
      debugPrint(
          'CIELO_CALLBACK resolve_started operation=${callback.operation} operation_id=${callback.operationId}');
      QuickSaleCheckout? updated;
      if (callback.isPayment) {
        updated = await widget.controller.resolveQuickSaleProviderPayment(
          checkoutId: _checkout.id,
          attemptId: callback.operationId,
          response: callback.response,
          responseCode: callback.responseCode,
        );
      } else if (callback.isReversal) {
        updated = await widget.controller.resolveQuickSaleProviderReversal(
          checkoutId: _checkout.id,
          operationId: callback.operationId,
          response: callback.response,
          responseCode: callback.responseCode,
        );
      }
      if (updated != null) {
        debugPrint(
            'CIELO_CALLBACK resolve_returned operation=${callback.operation} operation_id=${callback.operationId} resolved_status=${callback.isPayment ? updated.paymentIntegration?.intentStatus ?? "applied" : "reversal"}');
        final acknowledged = await _cieloBridge.acknowledgeCallback(callback);
        if (!acknowledged) {
          debugPrint(
              'CIELO_CALLBACK ack_failed operation=${callback.operation} operation_id=${callback.operationId}');
          return;
        }
        debugPrint(
            'CIELO_CALLBACK ack_sent operation=${callback.operation} operation_id=${callback.operationId}');
        _pendingCieloCallback = null;
        if (callback.isPayment) {
          _activeProviderAttemptId = null;
        } else {
          _activeProviderReversalOperationId = null;
        }
        if (mounted) {
          _replaceCheckout(updated);
          if (callback.isPayment) {
            await _showProviderResultDialog(
                callback.operationId, updated.paymentIntegration);
          } else {
            await _showProviderReversalResultDialog(
                callback.operationId, updated);
          }
        }
      }
    } on PosApiException catch (error) {
      if (error.code == 'provider_transaction_conflict') {
        debugPrint(
            'CIELO_CALLBACK deterministic_conflict operation=${callback.operation} operation_id=${callback.operationId}');
        await _cieloBridge.acknowledgeCallback(callback);
        _pendingCieloCallback = null;
        if (callback.isPayment) {
          _activeProviderAttemptId = null;
        } else {
          _activeProviderReversalOperationId = null;
        }
        final checkout =
            await widget.controller.quickSaleCheckoutDetail(_checkout.id);
        if (checkout != null && mounted) _replaceCheckout(checkout);
        widget.controller.showTransientMessage(error.message);
      } else {
        debugPrint('CIELO_CALLBACK resolve_failed type=${error.runtimeType}');
      }
    } catch (error) {
      debugPrint('CIELO_CALLBACK resolve_failed type=${error.runtimeType}');
      // Keep the callback for the explicit confirmation retry after a network failure.
    } finally {
      _resolvingProviderCallback = false;
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _showProviderResultDialog(
      String attemptId, QuickSalePaymentIntegration? integration) async {
    if (!mounted || integration?.attemptId != attemptId) return;
    final status = integration!.attemptStatus ?? integration.intentStatus;
    if (status != 'cancelled' && status != 'error') return;
    if (!_shownProviderResultDialogs.add('$attemptId:$status')) return;
    debugPrint(
        'CIELO_CALLBACK modal_opened operation=payment attempt_id=$attemptId status=$status');

    // A retry from the dialog must not be blocked by the callback resolution.
    setState(() => _working = false);
    final message = integration.providerMessage?.trim();
    final retry = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(status == 'cancelled'
            ? 'Pagamento cancelado'
            : 'Erro no pagamento'),
        content: Text(message?.isNotEmpty == true
            ? message!
            : status == 'cancelled'
                ? 'Pagamento cancelado pelo usuário.'
                : 'Não foi possível concluir o pagamento na Cielo.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(status == 'cancelled' ? 'OK' : 'FECHAR'),
          ),
          if (status == 'error' && integration.canRetry)
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('TENTAR NOVAMENTE'),
            ),
        ],
      ),
    );
    if (retry == true && mounted) await _retryProviderPayment();
  }

  Future<void> _showProviderReversalResultDialog(
      String operationId, QuickSaleCheckout checkout) async {
    if (!mounted) return;
    QuickSaleProviderReversal? reversal;
    for (final payment in checkout.payments) {
      if (payment.providerReversal?.id == operationId) {
        reversal = payment.providerReversal;
        break;
      }
    }
    final status = reversal?.status;
    if (status != 'cancelled' && status != 'error') return;
    if (!_shownProviderResultDialogs.add('reversal:$operationId:$status')) {
      return;
    }
    debugPrint(
        'CIELO_CALLBACK modal_opened operation=reversal operation_id=$operationId status=$status');
    final message = reversal?.providerMessage?.trim();
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(
            status == 'cancelled' ? 'Estorno cancelado' : 'Erro no estorno'),
        content: Text(message?.isNotEmpty == true
            ? message!
            : status == 'cancelled'
                ? 'Estorno cancelado pelo usuário.'
                : 'Não foi possível concluir o estorno na Cielo.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  void _finishedWorking() {
    if (!mounted) return;
    setState(() => _working = false);
    _schedulePendingProviderCallback();
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
      customerId: clearCustomer ? null : (customer ?? _checkout.customer)?.id,
      discount: (discount ?? _checkout.discountIntent).toJson(),
      serviceFeeWaived: serviceFeeWaived ?? _checkout.serviceFeeWaived,
      discountAuthorization: discountAuthorization,
      itemDiscountAuthorization: itemDiscountAuthorization,
      serviceFeeAuthorization: serviceFeeAuthorization,
    );
    if (updated != null && mounted) {
      _replaceCheckout(updated);
    } else {
      final recovered =
          widget.controller.takeRecoveredQuickSaleResult(_checkout.id);
      if (recovered != null && mounted) {
        await widget.onCompleted(recovered);
        if (mounted) Navigator.of(context).pop(recovered);
      }
    }
    _finishedWorking();
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
    if (method.usesProviderCapture) {
      return _startProviderPayment(attempt, method);
    }
    return _recordPayment(
      attempt,
      preserveEqualSplit: fromEqualSplit,
      equalSplitIndex: equalSplitIndex,
    );
  }

  Future<bool> _startProviderPayment(
      QuickSalePaymentAttempt attempt, QuickSalePaymentMethod method) async {
    final provider = method.capture?.provider;
    if (provider == null) return false;
    setState(() => _working = true);
    final launch = await widget.controller.startQuickSaleProviderPayment(
      checkoutId: _checkout.id,
      paymentMethodId: attempt.paymentMethodId,
      provider: provider,
      mode: attempt.mode,
      idempotencyKey: attempt.intentId,
      amount: attempt.amount,
      allocations: attempt.allocations,
    );
    if (launch == null) {
      // A timeout can still have created a PROCESSING attempt. Reload the
      // authoritative checkout rather than offering another charge.
      final current =
          await widget.controller.quickSaleCheckoutDetail(_checkout.id);
      if (current != null && mounted) _replaceCheckout(current);
      _finishedWorking();
      return false;
    }
    _activeProviderAttemptId = launch.attemptId;
    if (launch.launchUri == null) {
      final current =
          await widget.controller.quickSaleCheckoutDetail(_checkout.id);
      if (current != null && mounted) _replaceCheckout(current);
      _finishedWorking();
      return false;
    }
    try {
      // launchUri is intentionally scoped to this call and never written to POS storage.
      await _cieloBridge.launch(
        operation: 'payment',
        operationId: launch.attemptId,
        launchUri: launch.launchUri!,
      );
    } on PlatformException catch (error) {
      await _handleCieloLaunchFailure(launch.attemptId, error);
      _finishedWorking();
      return false;
    }
    if (mounted) {
      final current =
          await widget.controller.quickSaleCheckoutDetail(_checkout.id);
      if (current != null) _replaceCheckout(current);
      _finishedWorking();
    }
    return true;
  }

  Future<void> _retryProviderPayment() async {
    final integration = _providerPayment;
    if (integration == null || _working) return;
    setState(() => _working = true);
    final launch = await widget.controller.retryQuickSaleProviderPayment(
      checkoutId: _checkout.id,
      intentId: integration.intentId,
    );
    if (launch != null) {
      _activeProviderAttemptId = launch.attemptId;
      if (launch.launchUri != null) {
        try {
          await _cieloBridge.launch(
              operation: 'payment',
              operationId: launch.attemptId,
              launchUri: launch.launchUri!);
        } on PlatformException catch (error) {
          await _handleCieloLaunchFailure(launch.attemptId, error);
        }
      }
    }
    if (mounted) {
      final current =
          await widget.controller.quickSaleCheckoutDetail(_checkout.id);
      if (current != null) _replaceCheckout(current);
      _finishedWorking();
    }
  }

  String _cieloLaunchDetail(PlatformException error) {
    final bridgeMessage = error.message?.trim();
    switch (error.code) {
      case 'cielo_app_unavailable':
        return bridgeMessage?.isNotEmpty == true
            ? bridgeMessage!
            : 'O aplicativo Cielo não está instalado neste dispositivo.';
      case 'cielo_launch_unresolved':
        return bridgeMessage?.isNotEmpty == true
            ? bridgeMessage!
            : 'A Cielo instalada não aceita este tipo de pagamento. Verifique a versão e a configuração.';
      case 'cielo_launch_invalid':
        return bridgeMessage?.isNotEmpty == true
            ? bridgeMessage!
            : 'O pedido de pagamento recebido é inválido.';
      case 'cielo_launch_failed':
        return bridgeMessage?.isNotEmpty == true
            ? bridgeMessage!
            : 'O Android não conseguiu iniciar a Cielo. Tente novamente ou acione o suporte.';
      default:
        return 'Não foi possível iniciar o aplicativo Cielo.';
    }
  }

  Future<void> _handleCieloLaunchFailure(
      String attemptId, PlatformException error) async {
    widget.controller.showTransientMessage(
      'Não foi possível abrir a Cielo.\n'
      'Código: ${error.code}\n'
      'Detalhe: ${_cieloLaunchDetail(error)}',
    );
    final updated = await widget.controller.reportProviderLaunchFailed(
      checkoutId: _checkout.id,
      attemptId: attemptId,
    );
    if (updated != null && mounted) _replaceCheckout(updated);
    final current =
        await widget.controller.quickSaleCheckoutDetail(_checkout.id);
    if (current != null && mounted) _replaceCheckout(current);
  }

  Future<void> _applyProviderPayment() async {
    final integration = _providerPayment;
    if (integration == null || _working) return;
    setState(() => _working = true);
    final updated = await widget.controller.applyQuickSaleProviderPayment(
      checkoutId: _checkout.id,
      intentId: integration.intentId,
    );
    if (updated != null && mounted) _replaceCheckout(updated);
    _finishedWorking();
  }

  Future<void> _cancelProviderPayment() async {
    final integration = _providerPayment;
    if (integration == null || _working) return;
    setState(() => _working = true);
    final updated = await widget.controller.cancelQuickSaleProviderPayment(
      checkoutId: _checkout.id,
      intentId: integration.intentId,
    );
    if (updated != null && mounted) _replaceCheckout(updated);
    _finishedWorking();
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
    _finishedWorking();
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
        content: Text(
            'A venda já foi concluída. Use o cancelamento da venda, não o estorno do checkout.'),
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
    if (payment.requiresProviderReversal) {
      await _startProviderReversal(payment, reason, authorization);
      return;
    }
    setState(() => _working = true);
    final updated = await widget.controller.reverseQuickSalePayment(
      checkoutId: _checkout.id,
      paymentId: payment.id,
      reason: reason,
      authorization: authorization,
    );
    if (updated != null && mounted) _replaceCheckout(updated);
    _finishedWorking();
  }

  Future<void> _startProviderReversal(QuickSaleCheckoutPayment payment,
      String reason, QuickSaleAuthorization? authorization) async {
    setState(() => _working = true);
    final launch = await widget.controller.startQuickSaleProviderReversal(
      checkoutId: _checkout.id,
      paymentId: payment.id,
      idempotencyKey: createIdempotencyKey(),
      reason: reason,
      authorization: authorization,
    );
    if (launch == null) {
      final current =
          await widget.controller.quickSaleCheckoutDetail(_checkout.id);
      if (current != null && mounted) _replaceCheckout(current);
      _finishedWorking();
      return;
    }
    _activeProviderReversalOperationId = launch.operationId;
    if (launch.launchUri == null) {
      final current =
          await widget.controller.quickSaleCheckoutDetail(_checkout.id);
      if (current != null && mounted) _replaceCheckout(current);
      _finishedWorking();
      return;
    }
    try {
      await _cieloBridge.launch(
        operation: 'reversal',
        operationId: launch.operationId,
        launchUri: launch.launchUri!,
      );
    } on PlatformException catch (error) {
      widget.controller.showTransientMessage(
        'Não foi possível abrir a Cielo para o estorno.\n'
        'Código: ${error.code}\n'
        'Detalhe: ${_cieloLaunchDetail(error)}',
      );
      final updated =
          await widget.controller.reportProviderReversalLaunchFailed(
        checkoutId: _checkout.id,
        operationId: launch.operationId,
      );
      if (updated != null && mounted) _replaceCheckout(updated);
    }
    final current =
        await widget.controller.quickSaleCheckoutDetail(_checkout.id);
    if (current != null && mounted) _replaceCheckout(current);
    _finishedWorking();
  }

  Future<void> _finish() async {
    setState(() => _working = true);
    final result =
        await widget.controller.finalizeQuickSaleCheckout(_checkout.id);
    if (result != null && mounted) {
      await widget.onCompleted(result);
      if (mounted) Navigator.of(context).pop(result);
    }
    _finishedWorking();
  }

  Future<void> _cancel() async {
    if (_working) return;
    if (_hasBlockingProviderPayment) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Resolva a cobrança Cielo antes de cancelar a venda.'),
      ));
      return;
    }
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
    _finishedWorking();
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
    if (_checkoutCancelled ||
        _hasAppliedPayment ||
        _hasBlockingProviderPayment) {
      return;
    }
    setState(() => _working = true);
    final cancelled =
        await widget.controller.cancelQuickSaleCheckout(_checkout.id);
    if (!mounted) return;
    _finishedWorking();
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
            pendingAction: _providerAction() ??
                (_pendingPayment == null
                    ? null
                    : OutlinedButton.icon(
                        onPressed: _working || !_checkout.canRecordPayment
                            ? null
                            : () => _recordPayment(_pendingPayment!),
                        icon: const Icon(Icons.refresh),
                        label: const Text('TENTAR NOVAMENTE'),
                      )),
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

  Widget? _providerAction() {
    final integration = _providerPayment;
    if (integration == null) return null;
    if (_pendingCieloCallback != null) {
      return Container(
        padding: const EdgeInsets.all(12),
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('RETORNO DA CIELO RECEBIDO'),
            const Text('AGUARDANDO CONFIRMAÇÃO NO CORE'),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: _working ? null : _schedulePendingProviderCallback,
              icon: const Icon(Icons.sync),
              label: const Text('TENTAR CONFIRMAR PAGAMENTO'),
            ),
          ],
        ),
      );
    }
    if (integration.canApply) {
      return Container(
        padding: const EdgeInsets.all(12),
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('PAGAMENTO APROVADO NA CIELO'),
            const Text(
                'O pagamento foi aprovado, mas ainda precisa ser registrado no CORE.'),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: _working ? null : _applyProviderPayment,
              icon: const Icon(Icons.sync),
              label: const Text('TENTAR REGISTRAR NO CORE'),
            ),
          ],
        ),
      );
    }
    if (integration.intentStatus == 'cancelled' ||
        integration.attemptStatus == 'cancelled') {
      return null;
    }
    if (integration.canRetry || integration.canCancel) {
      final controls = Row(children: [
        if (integration.canRetry)
          Expanded(
              child: OutlinedButton.icon(
            onPressed: _working ? null : _retryProviderPayment,
            icon: const Icon(Icons.refresh),
            label: const Text('TENTAR NOVAMENTE'),
          )),
        if (integration.canRetry && integration.canCancel)
          const SizedBox(width: 8),
        if (integration.canCancel)
          Expanded(
              child: OutlinedButton(
            onPressed: _working ? null : _cancelProviderPayment,
            child: const Text('CANCELAR COBRANÇA'),
          )),
      ]);
      if (integration.intentStatus == 'error' ||
          integration.attemptStatus == 'error') {
        return controls;
      }
      return controls;
    }
    final isUnknown = integration.intentStatus == 'unknown' ||
        integration.attemptStatus == 'unknown';
    return Container(
      padding: const EdgeInsets.all(12),
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: isUnknown
          ? Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('PAGAMENTO AGUARDANDO VERIFICAÇÃO'),
                const SizedBox(height: 4),
                Text(
                  integration.providerMessage ??
                      'A transação exige verificação antes de uma nova cobrança.',
                ),
              ],
            )
          : Text(integration.requiresRecovery
              ? 'PAGAMENTO EM PROCESSAMENTO NA CIELO'
              : 'PAGAMENTO AGUARDANDO CONFIRMAÇÃO.'),
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
                onReverse: _checkout.canReversePayment
                    ? () => _reverse(payment)
                    : null,
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
