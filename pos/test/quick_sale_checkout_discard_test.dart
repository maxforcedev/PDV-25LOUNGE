import 'dart:convert';

import 'package:core_pos/auth/auth_models.dart';
import 'package:core_pos/core/app_controller.dart';
import 'package:core_pos/network/pos_api.dart';
import 'package:core_pos/network/pos_api_error.dart';
import 'package:core_pos/pairing/pairing_models.dart';
import 'package:core_pos/sales/sale_models.dart';
import 'package:core_pos/storage/secret_store.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const operator =
      PosOperator(id: 'operator-1', displayName: 'Operador', initials: 'OP');
  const device = DeviceDescriptor(
    name: 'Terminal',
    type: 'POS',
    appVersion: '1.0.0',
    osVersion: 'test',
    model: 'test',
  );

  AppController controller(_CheckoutApi api, _MemorySecretStore storage) {
    final controller =
        AppController(api: api, secrets: storage, device: device);
    controller.selectedOperator = operator;
    return controller;
  }

  test('discards a payment-free checkout only after backend cancellation',
      () async {
    final storage = _MemorySecretStore.forCheckout('checkout-a');
    final api = _CheckoutApi(_checkout());

    expect(await controller(api, storage).discardQuickSaleCheckout(), isTrue);
    expect(api.cancelledCheckoutId, 'checkout-a');
    expect(jsonDecode(storage.quickSaleCheckoutState!), isEmpty);
  });

  test('keeps checkout and storage when a payment remains applied', () async {
    final storage = _MemorySecretStore.forCheckout('checkout-a');
    final api = _CheckoutApi(_checkout(payments: [_payment()]));

    expect(await controller(api, storage).discardQuickSaleCheckout(), isFalse);
    expect(api.cancelledCheckoutId, isNull);
    expect(
        jsonDecode(storage.quickSaleCheckoutState!)['operators']['operator-1']
            ['checkout_id'],
        'checkout-a');
  });

  test('allows discard after every payment has a reversal', () async {
    final storage = _MemorySecretStore.forCheckout('checkout-a');
    final api = _CheckoutApi(_checkout(payments: [
      _payment(),
      _payment(id: 'reversal-a', status: 'reversed', reversalOf: 'payment-a'),
    ]));

    expect(await controller(api, storage).discardQuickSaleCheckout(), isTrue);
    expect(api.cancelledCheckoutId, 'checkout-a');
  });

  test('preserves an uncertain payment operation instead of cancelling',
      () async {
    final storage = _MemorySecretStore.forCheckout('checkout-a', pending: {
      'reverse:payment-a:': 'reverse-key',
    });
    final api = _CheckoutApi(_checkout(payments: [_payment()]));

    expect(await controller(api, storage).discardQuickSaleCheckout(), isFalse);
    expect(api.cancelledCheckoutId, isNull);
    final state =
        jsonDecode(storage.quickSaleCheckoutState!) as Map<String, dynamic>;
    expect(state['operators']['operator-1']['pending']['reverse:payment-a:'],
        'reverse-key');
  });

  test('keeps storage when cancellation is not confirmed as cancelled',
      () async {
    final storage = _MemorySecretStore.forCheckout('checkout-a');
    final api = _CheckoutApi(_checkout(), cancelResponse: _checkout());

    expect(await controller(api, storage).discardQuickSaleCheckout(), isFalse);
    expect(
        jsonDecode(storage.quickSaleCheckoutState!)['operators']['operator-1']
            ['checkout_id'],
        'checkout-a');
  });

  for (final statusCode in [401, 403, 409, 422, 429, 500]) {
    test('keeps recovery state on HTTP $statusCode', () async {
      final storage = _MemorySecretStore.forCheckout('checkout-a');
      final api = _CheckoutApi(
        _checkout(),
        recoveryError: PosApiException(
            statusCode: statusCode, code: 'failure', message: 'Falha'),
      );

      expect(await controller(api, storage).recoverQuickSaleCheckout(), isNull);
      expect(
          jsonDecode(storage.quickSaleCheckoutState!)['operators']['operator-1']
              ['checkout_id'],
          'checkout-a');
    });
  }

  test('clears recovery state for authoritative 404 or terminal checkout',
      () async {
    final missingStorage = _MemorySecretStore.forCheckout('checkout-a');
    final missingApi = _CheckoutApi(
      _checkout(),
      recoveryError: const PosApiException(
          statusCode: 404, code: 'not_found', message: 'Ausente'),
    );
    expect(
        await controller(missingApi, missingStorage).recoverQuickSaleCheckout(),
        isNull);
    expect(jsonDecode(missingStorage.quickSaleCheckoutState!), isEmpty);

    final terminalStorage = _MemorySecretStore.forCheckout('checkout-a');
    expect(
        await controller(
                _CheckoutApi(_checkout(status: 'cancelled')), terminalStorage)
            .recoverQuickSaleCheckout(),
        isNull);
    expect(jsonDecode(terminalStorage.quickSaleCheckoutState!), isEmpty);
  });
}

QuickSaleCheckout _checkout({
  List<QuickSaleCheckoutPayment> payments = const [],
  String status = 'editing',
}) =>
    QuickSaleCheckout(
      id: 'checkout-a',
      status: status,
      preview: const QuickSalePreview(
        items: [],
        subtotal: '10.00',
        promotionDiscountTotal: '0.00',
        itemDiscountTotal: '0.00',
        discount: '0.00',
        serviceFeeRate: '0.00',
        serviceFeeAmount: '0.00',
        total: '10.00',
      ),
      paidAmount: '0.00',
      remainingAmount: '10.00',
      hasPaymentHistory: payments.isNotEmpty,
      discountIntent: const QuickSaleDiscountIntent(),
      serviceFeeWaived: false,
      items: const [],
      payments: payments,
      canEditFinancials: true,
      canRecordPayment: true,
      canPayByItems: false,
      canFinalize: false,
      canReversePayment: true,
    );

QuickSaleCheckoutPayment _payment({
  String id = 'payment-a',
  String status = 'applied',
  String? reversalOf,
}) =>
    QuickSaleCheckoutPayment(
      id: id,
      methodName: 'Dinheiro',
      amount: '10.00',
      status: status,
      reversalOf: reversalOf,
    );

class _MemorySecretStore implements SecretStore, QuickSaleCheckoutStateStore {
  _MemorySecretStore();

  _MemorySecretStore.forCheckout(String checkoutId,
      {Map<String, dynamic>? pending})
      : quickSaleCheckoutState = jsonEncode({
          'operators': {
            'operator-1': {
              'checkout_id': checkoutId,
              if (pending != null) 'pending': pending,
            },
          },
        });

  String? quickSaleCheckoutState;

  @override
  Future<void> clearDeviceCredential() async {}
  @override
  Future<void> clearOperatorSession() async {}
  @override
  Future<String?> readDeviceCredential() async => null;
  @override
  Future<String?> readOperatorSession() async => null;
  @override
  Future<String?> readPendingSaleIntents() async => null;
  @override
  Future<String?> readQuickSaleCheckoutState() async => quickSaleCheckoutState;
  @override
  Future<void> writeDeviceCredential(String credential) async {}
  @override
  Future<void> writeOperatorSession(String token) async {}
  @override
  Future<void> writePendingSaleIntents(String value) async {}
  @override
  Future<void> writeQuickSaleCheckoutState(String value) async =>
      quickSaleCheckoutState = value;
}

class _CheckoutApi implements PosApi {
  _CheckoutApi(this.checkout, {this.cancelResponse, this.recoveryError});

  final QuickSaleCheckout checkout;
  final QuickSaleCheckout? cancelResponse;
  final PosApiException? recoveryError;
  String? cancelledCheckoutId;

  @override
  Future<QuickSaleCheckout> cancelQuickSaleCheckout({
    required String checkoutId,
  }) async {
    cancelledCheckoutId = checkoutId;
    return cancelResponse ??
        _checkout(status: 'cancelled', payments: checkout.payments);
  }

  @override
  Future<QuickSaleCheckout> getQuickSaleCheckout(String checkoutId) async {
    if (recoveryError != null) throw recoveryError!;
    return checkout;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
