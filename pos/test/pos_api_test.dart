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
  });
}

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
