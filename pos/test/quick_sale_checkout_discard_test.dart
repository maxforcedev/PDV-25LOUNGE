import 'dart:convert';

import 'package:core_pos/auth/auth_models.dart';
import 'package:core_pos/core/app_controller.dart';
import 'package:core_pos/network/pos_api.dart';
import 'package:core_pos/pairing/pairing_models.dart';
import 'package:core_pos/sales/sale_models.dart';
import 'package:core_pos/storage/secret_store.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const operator = PosOperator(id: 'operator-1', displayName: 'Operador', initials: 'OP');
  const device = DeviceDescriptor(
    name: 'Terminal',
    type: 'POS',
    appVersion: '1.0.0',
    osVersion: 'test',
    model: 'test',
  );

  AppController controller(_CheckoutApi api, _MemorySecretStore storage) {
    final controller = AppController(api: api, secrets: storage, device: device);
    controller.selectedOperator = operator;
    return controller;
  }

  test('discards a payment-free checkout only after backend cancellation', () async {
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
    expect(jsonDecode(storage.quickSaleCheckoutState!)['operators']['operator-1']['checkout_id'], 'checkout-a');
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

  test('preserves an uncertain payment operation instead of cancelling', () async {
    final storage = _MemorySecretStore.forCheckout('checkout-a', pending: {
      'reverse:payment-a:': 'reverse-key',
    });
    final api = _CheckoutApi(_checkout(payments: [_payment()]));

    expect(await controller(api, storage).discardQuickSaleCheckout(), isFalse);
    expect(api.cancelledCheckoutId, isNull);
    final state = jsonDecode(storage.quickSaleCheckoutState!) as Map<String, dynamic>;
    expect(state['operators']['operator-1']['pending']['reverse:payment-a:'], 'reverse-key');
  });
}

QuickSaleCheckout _checkout({List<QuickSaleCheckoutPayment> payments = const []}) =>
    QuickSaleCheckout(
      id: 'checkout-a',
      status: 'editing',
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
      cashSessionId: 1,
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

  _MemorySecretStore.forCheckout(String checkoutId, {Map<String, dynamic>? pending})
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
  _CheckoutApi(this.checkout);

  final QuickSaleCheckout checkout;
  String? cancelledCheckoutId;

  @override
  Future<QuickSaleCheckout> cancelQuickSaleCheckout({
    required String checkoutId,
  }) async {
    cancelledCheckoutId = checkoutId;
    return checkout;
  }

  @override
  Future<QuickSaleCheckout> getQuickSaleCheckout(String checkoutId) async =>
      checkout;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
