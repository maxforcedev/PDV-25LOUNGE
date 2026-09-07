import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract class SecretStore {
  Future<String?> readDeviceCredential();
  Future<void> writeDeviceCredential(String credential);
  Future<void> clearDeviceCredential();
  Future<String?> readOperatorSession();
  Future<void> writeOperatorSession(String token);
  Future<void> clearOperatorSession();
  Future<String?> readPendingSaleIntents() async => null;
  Future<void> writePendingSaleIntents(String value) async {}
}

class FlutterSecretStore implements SecretStore {
  FlutterSecretStore({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  static const _deviceCredentialKey = 'core_pos.device_credential';
  static const _operatorSessionKey = 'core_pos.operator_session';
  static const _pendingSaleIntentsKey = 'core_pos.pending_sale_intents';

  final FlutterSecureStorage _storage;

  @override
  Future<String?> readDeviceCredential() =>
      _storage.read(key: _deviceCredentialKey);

  @override
  Future<void> writeDeviceCredential(String credential) =>
      _storage.write(key: _deviceCredentialKey, value: credential);

  @override
  Future<void> clearDeviceCredential() =>
      _storage.delete(key: _deviceCredentialKey);

  @override
  Future<String?> readOperatorSession() =>
      _storage.read(key: _operatorSessionKey);

  @override
  Future<void> writeOperatorSession(String token) =>
      _storage.write(key: _operatorSessionKey, value: token);

  @override
  Future<void> clearOperatorSession() =>
      _storage.delete(key: _operatorSessionKey);

  @override
  Future<String?> readPendingSaleIntents() =>
      _storage.read(key: _pendingSaleIntentsKey);

  @override
  Future<void> writePendingSaleIntents(String value) =>
      _storage.write(key: _pendingSaleIntentsKey, value: value);
}
