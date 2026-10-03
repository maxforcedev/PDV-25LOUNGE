import 'dart:convert';

import 'package:core_pos/network/pos_api.dart';
import 'package:core_pos/storage/secret_store.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('adds device and operator credentials outside widgets', () async {
    final secrets = _MemorySecretStore(
      deviceCredential: 'device-secret',
      operatorSession: 'operator-secret',
    );
    late http.Request request;
    final api = HttpPosApi(
      baseUrl: 'https://core.example',
      secrets: secrets,
      client: MockClient((received) async {
        request = received;
        return http.Response(jsonEncode({'operators': const []}), 200);
      }),
    );

    await api.warmCredentials();
    await api.operators();

    expect(request.url.path, '/api/v1/pos/operators/');
    expect(request.headers['x-pos-device-credential'], 'device-secret');
    expect(request.headers['x-pos-operator-session'], 'operator-secret');
  });

  test('does not send a result effect when recording a withdrawal', () async {
    final api = HttpPosApi(
      baseUrl: 'https://core.example',
      secrets: _MemorySecretStore(),
      client: MockClient((request) async {
        expect(jsonDecode(request.body), {
          'amount': '10.00',
          'reason': 'Troco',
          'category': 'other',
          'idempotency_key': 'key',
        });
        return http.Response(
            jsonEncode({
              'cash_state': {
                'mode': 'FLEXIBLE',
                'enabled': true,
                'registers': []
              }
            }),
            201);
      }),
    );

    await api.recordCashWithdrawal(
      sessionId: 1,
      amount: '10.00',
      reason: 'Troco',
      category: 'other',
      idempotencyKey: 'key',
    );
  });

  test('uses POS-5 command contracts and idempotency keys', () async {
    final api = HttpPosApi(
      baseUrl: 'https://core.example',
      secrets: _MemorySecretStore(),
      client: MockClient((request) async {
        switch (request.url.path) {
          case '/api/v1/pos/commands/':
            expect(jsonDecode(request.body), {
              'idempotency_key': 'open-key',
              'identifier': 'Ana',
              'people_count': 2,
              'notes': 'Janela',
            });
            return http.Response(
                jsonEncode({'id': 7, 'number': 'A000007'}), 201);
          case '/api/v1/pos/commands/7/items/':
            expect(jsonDecode(request.body), {
              'items': [
                {
                  'product': 4,
                  'quantity': '1',
                  'modifiers': [],
                  'notes': 'Sem gelo'
                }
              ],
              'idempotency_key': 'items-key',
            });
            return http.Response(
                jsonEncode([
                  {
                    'id': 11,
                    'product': 4,
                    'product_name': 'Suco',
                    'quantity': '1',
                    'unit_price': '8.00'
                  }
                ]),
                201);
          case '/api/v1/pos/command-items/11/confirm/':
            expect(
                jsonDecode(request.body), {'idempotency_key': 'confirm-key'});
            return http.Response(
                jsonEncode({
                  'id': 11,
                  'product': 4,
                  'product_name': 'Suco',
                  'quantity': '1',
                  'unit_price': '8.00',
                  'status': 'confirmed'
                }),
                200);
          case '/api/v1/pos/tables/groups/':
            expect(jsonDecode(request.body), {
              'tables': [3, 4],
              'idempotency_key': 'group-key',
            });
            return http.Response(jsonEncode({'id': 9}), 201);
          case '/api/v1/pos/commands/7/request-bill/':
            expect(jsonDecode(request.body), {'idempotency_key': 'bill-key'});
            return http.Response(
                jsonEncode({
                  'id': 7,
                  'number': 'A000007',
                  'bill_requested_at': '2026-01-01T12:00:00Z'
                }),
                200);
        }
        throw StateError('Unexpected request: ${request.url}');
      }),
    );

    final command = await api.openAttendanceCommand(
      idempotencyKey: 'open-key',
      identifier: 'Ana',
      peopleCount: 2,
      notes: 'Janela',
    );
    expect(command.id, 7);
    final items = await api.addAttendanceItems(
        commandId: command.id,
        items: [
          {'product': 4, 'quantity': '1', 'modifiers': [], 'notes': 'Sem gelo'}
        ],
        idempotencyKey: 'items-key');
    expect(items.single.id, 11);
    expect(
        (await api.confirmAttendanceItem(
                itemId: 11, idempotencyKey: 'confirm-key'))
            .status,
        'confirmed');
    await api
        .groupAttendanceTables(tableIds: [3, 4], idempotencyKey: 'group-key');
    expect(
        (await api.setAttendanceBillRequested(
                commandId: command.id,
                requested: true,
                idempotencyKey: 'bill-key'))
            .billRequested,
        isTrue);
  });

  test('starts physical dispatch and only returns confirmed reconciliation ids',
      () async {
    final api = HttpPosApi(
      baseUrl: 'https://core.example',
      secrets: _MemorySecretStore(deviceCredential: 'device-secret'),
      client: MockClient((request) async {
        if (request.url.path.endsWith('/dispatch/')) {
          expect(request.method, 'POST');
          return http.Response(jsonEncode({'jobs': const []}), 200);
        }
        expect(request.url.path, '/api/v1/pos/printing/reconcile/');
        expect(jsonDecode(request.body), {
          'entries': [
            {'job_id': 10, 'state': 'sent'}
          ]
        });
        return http.Response(
            jsonEncode({
              'job_ids': [10]
            }),
            200);
      }),
    );

    await api.startPrintDispatch(10);
    expect(
        await api.reconcilePrintJobs([
          {'job_id': 10, 'state': 'sent'}
        ]),
        [10]);
  });

  test('uses provider-neutral Quick Sale payment endpoints', () async {
    final api = HttpPosApi(
      baseUrl: 'https://core.example',
      secrets: _MemorySecretStore(),
      client: MockClient((request) async {
        expect(
          request.url.path,
          '/api/v1/pos/sales/checkouts/checkout-1/provider-payments/start/',
        );
        expect(jsonDecode(request.body), {
          'payment_method': 3,
          'provider': 'cielo',
          'mode': 'remaining',
          'idempotency_key': 'intent-1',
        });
        return http.Response(
            jsonEncode({
              'provider': 'cielo',
              'intent_id': 'intent-1',
              'attempt_id': 'attempt-1',
              'status': 'processing',
              'operation': 'payment',
              'launch_uri': 'lio://payment?request=secret',
            }),
            200);
      }),
    );

    final launch = await api.startQuickSaleProviderPayment(
      checkoutId: 'checkout-1',
      paymentMethodId: 3,
      provider: 'cielo',
      mode: 'remaining',
      idempotencyKey: 'intent-1',
    );

    expect(launch.attemptId, 'attempt-1');
    expect(launch.launchUri, 'lio://payment?request=secret');
  });

  test('parses a replayed provider start without a reusable launch URI',
      () async {
    final api = HttpPosApi(
      baseUrl: 'https://core.example',
      secrets: _MemorySecretStore(),
      client: MockClient((request) async => http.Response(
            jsonEncode({
              'provider': 'cielo',
              'intent_id': 'intent-1',
              'attempt_id': 'attempt-1',
              'status': 'processing',
              'replayed': true,
              'launch_available': false,
            }),
            200,
          )),
    );

    final launch = await api.startQuickSaleProviderPayment(
      checkoutId: 'checkout-1',
      paymentMethodId: 3,
      provider: 'cielo',
      mode: 'remaining',
      idempotencyKey: 'intent-1',
    );

    expect(launch.launchUri, isNull);
    expect(launch.replayed, isTrue);
    expect(launch.launchAvailable, isFalse);
  });

  test('uses provider reversal endpoints and parses its launch operation',
      () async {
    var requestCount = 0;
    final api = HttpPosApi(
      baseUrl: 'https://core.example',
      secrets: _MemorySecretStore(),
      client: MockClient((request) async {
        requestCount += 1;
        if (requestCount == 1) {
          expect(
            request.url.path,
            '/api/v1/pos/sales/checkouts/checkout-1/payments/payment-1/provider-reversal/start/',
          );
          expect(jsonDecode(request.body), {
            'idempotency_key': 'reversal-key',
            'reason': 'Cobrança duplicada',
          });
          return http.Response(
              jsonEncode({
                'provider': 'cielo',
                'operation_id': 'reversal-1',
                'status': 'processing',
                'operation': 'reversal',
                'launch_uri': 'lio://payment-reversal?request=secret',
              }),
              200);
        }
        expect(
          request.url.path,
          '/api/v1/pos/sales/checkouts/checkout-1/provider-reversals/reversal-1/result/',
        );
        expect(jsonDecode(request.body), {
          'response': 'callback',
          'responsecode': '0',
        });
        return http.Response(jsonEncode(_checkoutPayload()), 200);
      }),
    );

    final launch = await api.startQuickSaleProviderReversal(
      checkoutId: 'checkout-1',
      paymentId: 'payment-1',
      idempotencyKey: 'reversal-key',
      reason: 'Cobrança duplicada',
    );
    expect(launch.operationId, 'reversal-1');
    expect(launch.launchUri, 'lio://payment-reversal?request=secret');

    final checkout = await api.resolveQuickSaleProviderReversal(
      checkoutId: 'checkout-1',
      operationId: 'reversal-1',
      response: 'callback',
      responseCode: '0',
    );
    final payment = checkout.payments.single;
    expect(payment.sourceType, 'provider');
    expect(payment.paymentAttemptId, 'attempt-1');
    expect(payment.providerReversal?.status, 'cancelled');
  });
}

Map<String, dynamic> _checkoutPayload() => {
      'id': 'checkout-1',
      'status': 'open',
      'preview': const {},
      'paid_amount': '10.00',
      'remaining_amount': '0.00',
      'has_payment_history': true,
      'discount_intent': const {},
      'service_fee_waived': false,
      'items': const [],
      'payments': [
        {
          'id': 'payment-1',
          'payment_method_name': 'Cartão',
          'amount': '10.00',
          'status': 'applied',
          'source_type': 'provider',
          'payment_attempt_id': 'attempt-1',
          'provider_reversal': {
            'id': 'reversal-1',
            'status': 'cancelled',
            'provider_message': 'Cancelado',
          },
        },
      ],
      'capabilities': const {},
    };

class _MemorySecretStore implements SecretStore {
  _MemorySecretStore({this.deviceCredential, this.operatorSession});

  String? deviceCredential;
  String? operatorSession;
  String? pendingSaleIntents;

  @override
  Future<void> clearDeviceCredential() async => deviceCredential = null;

  @override
  Future<void> clearOperatorSession() async => operatorSession = null;

  @override
  Future<String?> readDeviceCredential() async => deviceCredential;

  @override
  Future<String?> readOperatorSession() async => operatorSession;

  @override
  Future<String?> readPendingSaleIntents() async => pendingSaleIntents;

  @override
  Future<void> writeDeviceCredential(String credential) async =>
      deviceCredential = credential;

  @override
  Future<void> writeOperatorSession(String token) async =>
      operatorSession = token;

  @override
  Future<void> writePendingSaleIntents(String value) async =>
      pendingSaleIntents = value;
}
