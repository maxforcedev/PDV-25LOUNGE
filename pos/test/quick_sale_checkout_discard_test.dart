import 'dart:convert';

import 'package:core_pos/auth/auth_models.dart';
import 'package:core_pos/bootstrap/bootstrap_models.dart';
import 'package:core_pos/cash/cash_models.dart';
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
    controller.bootstrapSnapshot = const BootstrapSnapshot(
      companyName: 'Empresa',
      companyId: 'company-1',
      branchName: 'Filial',
      branchId: 'branch-1',
      deviceName: 'Terminal',
      deviceId: 'device-1',
      operatorName: 'Operador',
      release: ReleaseInfo(
        currentVersion: '1.0.0',
        latestVersion: '1.0.0',
        minimumSupportedVersion: '1.0.0',
        updateAvailable: false,
        updateRequired: false,
      ),
      modules: [],
    );
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
        jsonDecode(storage.quickSaleCheckoutState!)['scopes']
                ['company-1:branch-1:device-1']['operators']['operator-1']
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
    expect(
        state['scopes']['company-1:branch-1:device-1']['operators']
            ['operator-1']['pending']['reverse:payment-a:'],
        'reverse-key');
  });

  test(
      'starting a new sale reopens an uncertain checkout instead of erasing it',
      () async {
    final storage = _MemorySecretStore.forCheckout('checkout-a', pending: {
      'finalize': 'finalize-key',
    });
    final api = _CheckoutApi(_checkout());

    final recovered = await controller(api, storage).startNewQuickSale();

    expect(recovered.checkout?.id, 'checkout-a');
    final state =
        jsonDecode(storage.quickSaleCheckoutState!) as Map<String, dynamic>;
    expect(
        state['scopes']['company-1:branch-1:device-1']['operators']
            ['operator-1']['pending']['finalize'],
        'finalize-key');
    expect(api.cancelledCheckoutId, isNull);
  });

  test(
      'server-finalized recovery clears local state without replaying finalization',
      () async {
    final storage = _MemorySecretStore.forCheckout('checkout-a', pending: {
      'finalize': 'finalize-key',
    });
    final api = _CheckoutApi(_checkout(status: 'finalized', saleId: 1));

    expect(await controller(api, storage).recoverQuickSaleCheckout(), isNull);
    expect(jsonDecode(storage.quickSaleCheckoutState!), isEmpty);
    expect(api.finalizeCalls, 0);
    expect(api.resultCalls, 1);
  });

  test('keeps storage when cancellation is not confirmed as cancelled',
      () async {
    final storage = _MemorySecretStore.forCheckout('checkout-a');
    final api = _CheckoutApi(_checkout(), cancelResponse: _checkout());

    expect(await controller(api, storage).discardQuickSaleCheckout(), isFalse);
    expect(
        jsonDecode(storage.quickSaleCheckoutState!)['scopes']
                ['company-1:branch-1:device-1']['operators']['operator-1']
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
          jsonDecode(storage.quickSaleCheckoutState!)['scopes']
                  ['company-1:branch-1:device-1']['operators']['operator-1']
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

  test(
      'preserves corrupted financial evidence until authoritative reconciliation',
      () async {
    final storage = _MemorySecretStore()..quickSaleCheckoutState = '{broken';
    final api = _CheckoutApi(_checkout(), reconciliation: const []);

    final recovery = await controller(api, storage).startNewQuickSale();

    expect(recovery.status, QuickSaleRecoveryStatus.none);
    final root =
        jsonDecode(storage.quickSaleCheckoutState!) as Map<String, dynamic>;
    expect(root['recovery_evidence'].single['raw_state'], '{broken');
    expect(api.reconciliationCalls, 1);
  });

  test(
      'recovers the sole authoritative checkout without discarding corrupt bytes',
      () async {
    final storage = _MemorySecretStore()..quickSaleCheckoutState = '{broken';
    final api = _CheckoutApi(_checkout(), reconciliation: [_checkout()]);

    final recovery = await controller(api, storage).startNewQuickSale();

    expect(recovery.checkout?.id, 'checkout-a');
    final root =
        jsonDecode(storage.quickSaleCheckoutState!) as Map<String, dynamic>;
    expect(root['recovery_evidence'].single['raw_state'], '{broken');
    expect(
        root['scopes']['company-1:branch-1:device-1']['operators']['operator-1']
            ['checkout_id'],
        'checkout-a');
  });

  test('read or write storage failure blocks checkout creation before the API',
      () async {
    final readFailure = _MemorySecretStore()..failRead = true;
    final readApi = _CheckoutApi(_checkout());
    expect(
        await controller(readApi, readFailure).createQuickSaleCheckout(
            items: const [], discount: const {}, serviceFeeWaived: false),
        isNull);
    expect(readApi.createCalls, 0);

    final writeFailure = _MemorySecretStore()..failWrite = true;
    final writeApi = _CheckoutApi(_checkout());
    expect(
        await controller(writeApi, writeFailure).createQuickSaleCheckout(
            items: const [], discount: const {}, serviceFeeWaived: false),
        isNull);
    expect(writeApi.createCalls, 0);
  });

  test(
      'unproven legacy namespaces are preserved and never attached to this POS',
      () async {
    final storage = _MemorySecretStore()
      ..quickSaleCheckoutState = jsonEncode({
        'operators': {
          'operator-1': {'checkout_id': 'other-device-checkout'},
        },
      });

    final recovery = await controller(
      _CheckoutApi(
        _checkout(),
        recoveryError: const PosApiException(
            statusCode: 404, code: 'not_found', message: 'Ausente'),
      ),
      storage,
    ).startNewQuickSale();

    expect(recovery.status, QuickSaleRecoveryStatus.none);
    expect(
        jsonDecode(storage.quickSaleCheckoutState!)['operators']['operator-1']
            ['checkout_id'],
        'other-device-checkout');
  });

  test('returns the normal sale result after a lost finalization response',
      () async {
    final storage = _MemorySecretStore.forCheckout('checkout-a', pending: {
      'finalize': 'finalize-key',
    });
    final api = _CheckoutApi(_checkout(status: 'finalized', saleId: 1));

    final recovery = await controller(api, storage).startNewQuickSale();

    expect(recovery.saleResult?.saleNumber, 'V000001');
    expect(api.finalizeCalls, 0);
    expect(api.resultCalls, 1);
  });

  test('migrates a renamed legacy device only after backend scope confirmation',
      () async {
    final storage = _MemorySecretStore()
      ..quickSaleCheckoutState = jsonEncode({
        'devices': {
          'POS:Old terminal:old model': {
            'operators': {
              'operator-1': {'checkout_id': 'checkout-a'},
            },
          },
        },
      });

    final recovery = await controller(_CheckoutApi(_checkout()), storage)
        .startNewQuickSale();

    expect(recovery.checkout?.id, 'checkout-a');
    final root =
        jsonDecode(storage.quickSaleCheckoutState!) as Map<String, dynamic>;
    expect(
        root['scopes']['company-1:branch-1:device-1']['operators']['operator-1']
            ['checkout_id'],
        'checkout-a');
    expect(root['devices']['POS:Old terminal:old model'], isNotNull);
  });
}

QuickSaleCheckout _checkout({
  List<QuickSaleCheckoutPayment> payments = const [],
  String status = 'editing',
  int? saleId,
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
      saleId: saleId,
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
          'scopes': {
            'company-1:branch-1:device-1': {
              'operators': {
                'operator-1': {
                  'checkout_id': checkoutId,
                  if (pending != null) 'pending': pending,
                },
              },
            },
          },
        });

  String? quickSaleCheckoutState;
  bool failRead = false;
  bool failWrite = false;

  @override
  Future<void> clearDeviceCredential() async {}
  @override
  Future<void> clearOperatorSession() async {}
  @override
  Future<String?> readDeviceCredential() async => null;
  @override
  Future<String?> readOperatorSession() async => null;
  @override
  Future<String?> readQuickSaleCheckoutState() async {
    if (failRead) throw StateError('secure storage unavailable');
    return quickSaleCheckoutState;
  }

  @override
  Future<void> writeDeviceCredential(String credential) async {}
  @override
  Future<void> writeOperatorSession(String token) async {}
  @override
  Future<void> writeQuickSaleCheckoutState(String value) async {
    if (failWrite) throw StateError('secure storage unavailable');
    quickSaleCheckoutState = value;
  }
}

class _CheckoutApi implements PosApi {
  _CheckoutApi(this.checkout,
      {this.cancelResponse, this.recoveryError, this.reconciliation});

  final QuickSaleCheckout checkout;
  final QuickSaleCheckout? cancelResponse;
  final PosApiException? recoveryError;
  final List<QuickSaleCheckout>? reconciliation;
  String? cancelledCheckoutId;
  var finalizeCalls = 0;
  var resultCalls = 0;
  var reconciliationCalls = 0;
  var createCalls = 0;

  @override
  Future<QuickSaleCheckout> createQuickSaleCheckout({
    required List<Map<String, dynamic>> items,
    required Map<String, dynamic> discount,
    required bool serviceFeeWaived,
    required String idempotencyKey,
    int? customerId,
    Map<String, dynamic>? discountAuthorization,
    Map<String, dynamic>? itemDiscountAuthorization,
    Map<String, dynamic>? serviceFeeAuthorization,
  }) async {
    createCalls++;
    return checkout;
  }

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
  Future<QuickSaleResult> finalizeQuickSaleCheckout({
    required String checkoutId,
    required String idempotencyKey,
  }) async {
    finalizeCalls++;
    throw UnimplementedError();
  }

  @override
  Future<QuickSaleResult> quickSaleCheckoutResult(String checkoutId) async {
    resultCalls++;
    return const QuickSaleResult(
      saleNumber: 'V000001',
      total: '10.00',
      cash: CashOverview(mode: 'FLEXIBLE', enabled: true),
    );
  }

  @override
  Future<List<QuickSaleCheckout>> reconcileQuickSaleCheckouts() async {
    reconciliationCalls++;
    return reconciliation ?? const [];
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
