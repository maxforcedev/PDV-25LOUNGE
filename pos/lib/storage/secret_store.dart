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

abstract interface class QuickSaleCheckoutStateStore {
  Future<String?> readQuickSaleCheckoutState();
  Future<void> writeQuickSaleCheckoutState(String value);
}

abstract interface class TablePaymentStateStore {
  Future<String?> readTablePaymentState();
  Future<void> writeTablePaymentState(String value);
}

abstract interface class PrintLedgerStateStore {
  Future<String?> readPrintLedgerState();
  Future<void> writePrintLedgerState(String value);
}

/// Optional so existing secret-store implementations remain valid.
extension QuickSaleCheckoutSecretStore on SecretStore {
  Future<String?> readQuickSaleCheckoutState() =>
      this is QuickSaleCheckoutStateStore
          ? (this as QuickSaleCheckoutStateStore).readQuickSaleCheckoutState()
          : Future.value(null);

  Future<void> writeQuickSaleCheckoutState(String value) => this
          is QuickSaleCheckoutStateStore
      ? (this as QuickSaleCheckoutStateStore).writeQuickSaleCheckoutState(value)
      : Future.value();
}

extension TablePaymentSecretStore on SecretStore {
  Future<String?> readTablePaymentState() => this is TablePaymentStateStore
      ? (this as TablePaymentStateStore).readTablePaymentState()
      : Future.value(null);
  Future<void> writeTablePaymentState(String value) =>
      this is TablePaymentStateStore
          ? (this as TablePaymentStateStore).writeTablePaymentState(value)
          : Future.value();
}

extension PrintLedgerSecretStore on SecretStore {
  Future<String?> readPrintLedgerState() => this is PrintLedgerStateStore
      ? (this as PrintLedgerStateStore).readPrintLedgerState()
      : Future.value(null);
  Future<void> writePrintLedgerState(String value) =>
      this is PrintLedgerStateStore
          ? (this as PrintLedgerStateStore).writePrintLedgerState(value)
          : Future.value();
}

class FlutterSecretStore
    implements
        SecretStore,
        QuickSaleCheckoutStateStore,
        TablePaymentStateStore,
        PrintLedgerStateStore {
  FlutterSecretStore({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  static const _deviceCredentialKey = 'core_pos.device_credential';
  static const _operatorSessionKey = 'core_pos.operator_session';
  static const _pendingSaleIntentsKey = 'core_pos.pending_sale_intents';
  static const _quickSaleCheckoutStateKey = 'core_pos.quick_sale_checkout';
  static const _tablePaymentStateKey = 'core_pos.table_payment_state';
  static const _printLedgerStateKey = 'core_pos.print_ledger';

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

  @override
  Future<String?> readQuickSaleCheckoutState() =>
      _storage.read(key: _quickSaleCheckoutStateKey);

  @override
  Future<void> writeQuickSaleCheckoutState(String value) =>
      _storage.write(key: _quickSaleCheckoutStateKey, value: value);

  @override
  Future<String?> readTablePaymentState() =>
      _storage.read(key: _tablePaymentStateKey);

  @override
  Future<void> writeTablePaymentState(String value) =>
      _storage.write(key: _tablePaymentStateKey, value: value);

  @override
  Future<String?> readPrintLedgerState() =>
      _storage.read(key: _printLedgerStateKey);

  @override
  Future<void> writePrintLedgerState(String value) =>
      _storage.write(key: _printLedgerStateKey, value: value);
}
