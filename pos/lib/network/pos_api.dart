import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../auth/auth_models.dart';
import '../bootstrap/bootstrap_models.dart';
import '../pairing/pairing_models.dart';
import '../storage/secret_store.dart';
import 'pos_api_error.dart';

abstract class PosApi {
  Future<PairingDiscovery> identifyBranch(String identifier);
  Future<OtpChallenge> requestOtp(String flowId, String channelId);
  Future<String> confirmPairing({
    required String challengeId,
    required String code,
    required DeviceDescriptor device,
  });
  Future<HeartbeatResult> heartbeat(DeviceDescriptor device);
  Future<List<PosOperator>> operators();
  Future<OperatorSession> login(String operatorId, String pin);
  Future<void> logout();
  Future<BootstrapSnapshot> bootstrap();
}

class HttpPosApi implements PosApi {
  HttpPosApi({
    required String baseUrl,
    required SecretStore secrets,
    http.Client? client,
  })  : _baseUri = Uri.parse(baseUrl.endsWith('/') ? baseUrl : '$baseUrl/'),
        _secrets = secrets,
        _client = client ?? http.Client();

  final Uri _baseUri;
  final SecretStore _secrets;
  final http.Client _client;

  Uri _uri(String path) => _baseUri.resolve('api/v1/pos/$path');

  Future<Map<String, String>> _headers({bool json = true}) async {
    final deviceCredential = await _secrets.readDeviceCredential();
    final operatorSession = await _secrets.readOperatorSession();
    return {
      if (json) 'Content-Type': 'application/json',
      'Accept': 'application/json',
      if (deviceCredential != null) 'X-POS-Device-Credential': deviceCredential,
      if (operatorSession != null) 'X-POS-Operator-Session': operatorSession,
    };
  }

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    http.Response response;
    try {
      final headers = await _headers();
      final uri = _uri(path);
      response = switch (method) {
        'GET' => await _client.get(uri, headers: headers).timeout(const Duration(seconds: 15)),
        'POST' => await _client.post(uri, headers: headers, body: jsonEncode(body ?? const {})).timeout(const Duration(seconds: 15)),
        _ => throw ArgumentError.value(method, 'method'),
      };
    } on http.ClientException catch (error) {
      throw PosNetworkException(error.message);
    } on TimeoutException {
      throw const PosNetworkException('A conexão demorou demais. Verifique a internet e tente novamente.');
    }
    final decoded = response.body.isEmpty ? <String, dynamic>{} : jsonDecode(response.body);
    final payload = decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    if (response.statusCode >= 200 && response.statusCode < 300) return payload;
    final code = payload['code'] as String? ??
        (response.statusCode == 401 ? 'authentication_failed' : 'request_failed');
    throw PosApiException(
      statusCode: response.statusCode,
      code: code,
      message: payload['message'] as String? ?? payload['detail'] as String? ?? 'Falha ao comunicar com o CORE.',
    );
  }

  @override
  Future<PairingDiscovery> identifyBranch(String identifier) async =>
      PairingDiscovery.fromJson(await _request('POST', 'pairing/identify/', body: {'identifier': identifier}));

  @override
  Future<OtpChallenge> requestOtp(String flowId, String channelId) async => OtpChallenge.fromJson(
        await _request('POST', 'pairing/request-otp/', body: {
          'pairing_flow_id': flowId,
          'channel_id': channelId,
        }),
      );

  @override
  Future<String> confirmPairing({
    required String challengeId,
    required String code,
    required DeviceDescriptor device,
  }) async {
    final payload = await _request('POST', 'pairing/confirm/', body: {
      'challenge_id': challengeId,
      'code': code,
      'device': device.toJson(),
    });
    return payload['device_credential'] as String;
  }

  @override
  Future<HeartbeatResult> heartbeat(DeviceDescriptor device) async => HeartbeatResult.fromJson(
        await _request('POST', 'heartbeat/', body: {
          'app_version': device.appVersion,
          'capabilities': device.capabilities,
        }),
      );

  @override
  Future<List<PosOperator>> operators() async {
    final payload = await _request('GET', 'operators/');
    return (payload['operators'] as List<dynamic>)
        .cast<Map<String, dynamic>>()
        .map(PosOperator.fromJson)
        .toList(growable: false);
  }

  @override
  Future<OperatorSession> login(String operatorId, String pin) async => OperatorSession.fromJson(
        await _request('POST', 'auth/operator/', body: {
          'operator_id': operatorId,
          'pin': pin,
        }),
      );

  @override
  Future<void> logout() async {
    await _request('POST', 'auth/logout/');
  }

  @override
  Future<BootstrapSnapshot> bootstrap() async =>
      BootstrapSnapshot.fromJson(await _request('GET', 'bootstrap/'));
}
