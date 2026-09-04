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

    await api.operators();

    expect(request.url.path, '/api/v1/pos/operators/');
    expect(request.headers['x-pos-device-credential'], 'device-secret');
    expect(request.headers['x-pos-operator-session'], 'operator-secret');
  });
}

class _MemorySecretStore implements SecretStore {
  _MemorySecretStore({this.deviceCredential, this.operatorSession});

  String? deviceCredential;
  String? operatorSession;

  @override
  Future<void> clearDeviceCredential() async => deviceCredential = null;

  @override
  Future<void> clearOperatorSession() async => operatorSession = null;

  @override
  Future<String?> readDeviceCredential() async => deviceCredential;

  @override
  Future<String?> readOperatorSession() async => operatorSession;

  @override
  Future<void> writeDeviceCredential(String credential) async => deviceCredential = credential;

  @override
  Future<void> writeOperatorSession(String token) async => operatorSession = token;
}
