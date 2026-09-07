import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../auth/auth_models.dart';
import '../bootstrap/bootstrap_models.dart';
import '../cash/cash_models.dart';
import '../network/pos_api.dart';
import '../network/pos_api_error.dart';
import '../pairing/pairing_models.dart';
import '../sales/sale_models.dart';
import '../storage/secret_store.dart';
import '../sync/sync_status.dart';
import 'transient_feedback.dart';

enum AppPhase {
  loading,
  pairingIdentifier,
  pairingChannel,
  pairingOtp,
  operatorSelection,
  operatorPin,
  home,
  deviceUnavailable,
  updateRequired,
  error,
}

class AppController extends ChangeNotifier {
  AppController({
    required PosApi api,
    required SecretStore secrets,
    required DeviceDescriptor device,
  })  : _api = api,
        _secrets = secrets,
        _device = device;

  final PosApi _api;
  final SecretStore _secrets;
  final DeviceDescriptor _device;
  final _transientFeedback = TransientFeedback();
  final Map<String, String> _uncertainCashOperationKeys = {};
  final Map<String, String> _uncertainSaleKeys = {};

  AppPhase phase = AppPhase.loading;
  bool busy = false;
  bool finalizingSale = false;
  String? saleFinalizationError;
  String? errorMessage;
  TransientAlert? get transientAlert => _transientFeedback.alert;
  PairingDiscovery? discovery;
  OtpChallenge? challenge;
  List<PosOperator> operators = const [];
  PosOperator? selectedOperator;
  BootstrapSnapshot? bootstrapSnapshot;
  SyncStatus syncStatus = const SyncStatus();
  PosApiException? deviceError;

  PosCredentialCache? get _credentialCache =>
      _api is PosCredentialCache ? _api as PosCredentialCache : null;

  void logPosAction(String action) =>
      logPosDebugTiming('action_triggered $action');

  Future<void> initialize() async {
    final credentialCache = _credentialCache;
    await credentialCache?.warmCredentials();
    await _restoreUncertainSaleIntents();
    final hasDeviceCredential = credentialCache != null
        ? credentialCache.hasDeviceCredential
        : await _secrets.readDeviceCredential() != null;
    if (!hasDeviceCredential) {
      phase = AppPhase.pairingIdentifier;
      notifyListeners();
      return;
    }
    await recoverPairedDevice();
  }

  Future<void> identify(String identifier) async {
    await _run(() async {
      discovery = await _api.identifyBranch(identifier.trim());
      phase = AppPhase.pairingChannel;
    });
  }

  Future<void> requestOtp(PairingChannel channel) async {
    final flow = discovery;
    if (flow == null) return;
    await _run(() async {
      challenge = await _api.requestOtp(flow.flowId, channel.id);
      phase = AppPhase.pairingOtp;
    });
  }

  Future<void> confirmOtp(String code) async {
    final currentChallenge = challenge;
    if (currentChallenge == null || !RegExp(r'^\d{6}$').hasMatch(code)) {
      _showTransientMessage('Informe o codigo de seis digitos.');
      return;
    }
    await _run(() async {
      final credential = await _api.confirmPairing(
        challengeId: currentChallenge.id,
        code: code,
        device: _device,
      );
      await _secrets.writeDeviceCredential(credential);
      _credentialCache?.cacheDeviceCredential(credential);
      await recoverPairedDevice(notify: false);
    });
  }

  Future<void> recoverPairedDevice({bool notify = true}) async {
    if (notify) {
      busy = true;
      _clearTransientMessage();
      errorMessage = null;
      notifyListeners();
    }
    try {
      syncStatus = syncStatus.begin();
      final heartbeat = await _api.heartbeat(_device);
      syncStatus = syncStatus.heartbeat(DateTime.now());
      if (heartbeat.release.updateRequired) {
        phase = AppPhase.updateRequired;
        return;
      }
      operators = await _api.operators();
      selectedOperator = null;
      phase = AppPhase.operatorSelection;
      syncStatus = syncStatus.succeeded();
    } on PosApiException catch (error) {
      _handleApiError(error, persistent: true);
      if (phase == AppPhase.loading || phase == AppPhase.operatorSelection) {
        phase = AppPhase.error;
      }
    } on PosNetworkException catch (error) {
      errorMessage = error.message;
      syncStatus = syncStatus.failed(error.message);
      phase = AppPhase.error;
    } finally {
      busy = false;
      if (notify) notifyListeners();
    }
  }

  void selectOperator(PosOperator operator) {
    selectedOperator = operator;
    _clearTransientMessage();
    notifyListeners();
  }

  Future<void> login(String pin) async {
    final operator = selectedOperator;
    if (operator == null || !RegExp(r'^\d{6}$').hasMatch(pin)) {
      _showTransientMessage('Informe o PIN de seis digitos.');
      return;
    }
    await _run(() async {
      final session = await _api.login(operator.id, pin);
      await _secrets.writeOperatorSession(session.token);
      _credentialCache?.cacheOperatorSession(session.token);
      try {
        bootstrapSnapshot = await _api.bootstrap();
      } catch (_) {
        await _secrets.clearOperatorSession();
        _credentialCache?.cacheOperatorSession(null);
        rethrow;
      }
      if (bootstrapSnapshot!.release.updateRequired) {
        phase = AppPhase.updateRequired;
        return;
      }
      syncStatus = syncStatus.succeeded();
      phase = AppPhase.home;
    });
  }

  Future<void> requestSelectedOperatorPinReset() async {
    final operator = selectedOperator;
    if (operator == null || busy) return;
    busy = true;
    _clearTransientMessage();
    notifyListeners();
    try {
      await _api.requestOperatorPinReset(operator.id);
      _showTransientMessage(
        'Enviamos as instruções para redefinir seu PIN.',
        tone: TransientAlertTone.success,
        notify: false,
      );
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message, notify: false);
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    try {
      await _api.logout();
    } catch (_) {
      // The local operator session must still be removed on a failed logout request.
    } finally {
      await _secrets.clearOperatorSession();
      _credentialCache?.cacheOperatorSession(null);
    }
    await recoverPairedDevice();
  }

  Future<void> synchronize() async {
    if (busy || bootstrapSnapshot == null) return;
    busy = true;
    _clearTransientMessage();
    syncStatus = syncStatus.begin();
    notifyListeners();
    try {
      final heartbeat = await _api.heartbeat(_device);
      syncStatus = syncStatus.heartbeat(DateTime.now());
      if (heartbeat.release.updateRequired) {
        phase = AppPhase.updateRequired;
        return;
      }
      bootstrapSnapshot = await _api.bootstrap();
      if (bootstrapSnapshot!.release.updateRequired) {
        phase = AppPhase.updateRequired;
        return;
      }
      syncStatus = syncStatus.succeeded();
    } on PosApiException catch (error) {
      _handleApiError(error);
      syncStatus = syncStatus.failed(error.message);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message, notify: false);
      syncStatus = syncStatus.failed(error.message);
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<bool> refreshCashOverview() async {
    final snapshot = bootstrapSnapshot;
    if (busy || snapshot == null) return false;
    busy = true;
    _clearTransientMessage();
    notifyListeners();
    try {
      bootstrapSnapshot = snapshot.withCash(await _api.cashOverview());
      return true;
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message, notify: false);
      syncStatus = syncStatus.failed(error.message);
    } finally {
      busy = false;
      notifyListeners();
    }
    return false;
  }

  Future<bool> openCashSession(
          {required String openingAmount, int? registerId}) =>
      _runCashAction(
        () => _api.openCashSession(
            openingAmount: openingAmount, registerId: registerId),
        'Caixa aberto com sucesso.',
      );

  Future<bool> recordCashEntry({
    required int sessionId,
    required String amount,
    required String reason,
  }) {
    final payload = jsonEncode(['entry', sessionId, amount, reason]);
    return _runCashAction(
      () => _api.recordCashEntry(
        sessionId: sessionId,
        amount: amount,
        reason: reason,
        idempotencyKey: _idempotencyKeyFor(payload),
      ),
      'Suprimento registrado com sucesso.',
      idempotencyPayload: payload,
    );
  }

  Future<List<CashBeneficiary>?> cashWithdrawalBeneficiaries(
      String category) async {
    try {
      return await _api.cashWithdrawalBeneficiaries(category);
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<bool> recordCashWithdrawal({
    required int sessionId,
    required String amount,
    required String reason,
    required String category,
    String? beneficiaryType,
    int? beneficiaryId,
  }) {
    final payload = jsonEncode([
      'withdrawal',
      sessionId,
      amount,
      reason,
      category,
      beneficiaryType,
      beneficiaryId,
    ]);
    return _runCashAction(
      () => _api.recordCashWithdrawal(
        sessionId: sessionId,
        amount: amount,
        reason: reason,
        category: category,
        beneficiaryType: beneficiaryType,
        beneficiaryId: beneficiaryId,
        idempotencyKey: _idempotencyKeyFor(payload),
      ),
      'Sangria registrada com sucesso.',
      idempotencyPayload: payload,
    );
  }

  Future<bool> closeCashSession(
          {required int sessionId, required String closingAmount}) =>
      _runCashAction(
        () => _api.closeCashSession(
            sessionId: sessionId, closingAmount: closingAmount),
        'Caixa fechado com sucesso.',
      );

  Future<CashSessionSummary?> cashSessionSummary(int sessionId) async {
    final snapshot = bootstrapSnapshot;
    if (snapshot == null ||
        !snapshot.permissions.contains('cash_registers.view')) {
      return null;
    }
    try {
      return await _api.cashSessionSummary(sessionId);
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<List<QuickSaleProduct>?> quickSaleCatalog({
    String? search,
    int? categoryId,
    bool favorites = false,
  }) async {
    try {
      return await _api.quickSaleCatalog(
        search: search,
        categoryId: categoryId,
        favorites: favorites,
      );
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<List<QuickSaleCategory>?> quickSaleCategories() async {
    try {
      return await _api.quickSaleCategories();
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<QuickSaleProduct?> quickSaleBarcode(String barcode) async {
    try {
      return await _api.quickSaleBarcode(barcode);
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<QuickSalePreview?> previewQuickSale({
    required List<Map<String, dynamic>> items,
    required Map<String, dynamic> discount,
    required bool serviceFeeWaived,
  }) async {
    try {
      return await _api.quickSalePreview(
        items: items,
        discount: discount,
        serviceFeeWaived: serviceFeeWaived,
      );
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<QuickSaleCheckoutOptions?> quickSaleCheckoutOptions() async {
    try {
      return await _api.quickSaleCheckoutOptions();
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<List<QuickSaleCustomer>?> quickSaleCustomers(String query) async {
    try {
      return await _api.quickSaleCustomers(query);
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<QuickSaleCustomer?> createQuickSaleCustomer({
    required String name,
    String phone = '',
    String document = '',
    String email = '',
  }) async {
    try {
      return await _api.createQuickSaleCustomer(
        name: name,
        phone: phone,
        document: document,
        email: email,
      );
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<QuickSaleResult?> finalizeQuickSale({
    required List<Map<String, dynamic>> items,
    required int cashSessionId,
    required List<Map<String, dynamic>> payments,
    required Map<String, dynamic> discount,
    required bool serviceFeeWaived,
    QuickSaleCustomer? customer,
  }) async {
    final snapshot = bootstrapSnapshot;
    if (finalizingSale) {
      _showTransientMessage('A venda já está sendo finalizada. Aguarde.');
      return null;
    }
    if (snapshot == null) {
      saleFinalizationError =
          'A sessão do POS não está disponível. Entre novamente.';
      _showTransientMessage(saleFinalizationError!);
      return null;
    }
    final payload = jsonEncode({
      'items': items,
      'cash_session': cashSessionId,
      'payments': payments,
      'discount': discount,
      'service_fee_waived': serviceFeeWaived,
      'customer': customer?.id,
    });
    final key = _uncertainSaleKeys.putIfAbsent(payload, createIdempotencyKey);
    await _persistUncertainSaleIntents();
    finalizingSale = true;
    saleFinalizationError = null;
    _clearTransientMessage();
    notifyListeners();
    try {
      final result = await _api.finalizeQuickSale(
        idempotencyKey: key,
        items: items,
        cashSessionId: cashSessionId,
        payments: payments,
        discount: discount,
        serviceFeeWaived: serviceFeeWaived,
        customerId: customer?.id,
      );
      bootstrapSnapshot = snapshot.withCash(result.cash);
      _uncertainSaleKeys.remove(payload);
      await _persistUncertainSaleIntents();
      syncStatus = syncStatus.succeeded();
      final tickets = result.ticketNumbers.isEmpty
          ? ''
          : ' Tickets: ${result.ticketNumbers.join(', ')}.';
      _showTransientMessage(
          'Venda ${result.saleNumber} concluida com sucesso.$tickets',
          tone: TransientAlertTone.success,
          notify: false);
      return result;
    } on PosApiException catch (error) {
      if (error.statusCode < 500) {
        _uncertainSaleKeys.remove(payload);
        await _persistUncertainSaleIntents();
      }
      _handleApiError(error);
      saleFinalizationError = error.message;
    } on PosNetworkException catch (error) {
      syncStatus = syncStatus.failed(error.message);
      _showTransientMessage(error.message, notify: false);
      saleFinalizationError = error.message;
    } finally {
      finalizingSale = false;
      notifyListeners();
    }
    return null;
  }

  Future<void> _restoreUncertainSaleIntents() async {
    final encoded = await _secrets.readPendingSaleIntents();
    if (encoded == null || encoded.isEmpty) return;
    try {
      final payload = jsonDecode(encoded) as Map<String, dynamic>;
      final intents = payload['intents'] as List<dynamic>? ?? const [];
      for (final raw in intents) {
        final intent = raw as Map<String, dynamic>;
        final body = intent['payload'];
        final key = intent['idempotency_key'] as String?;
        if (body is Map<String, dynamic> && key != null) {
          _uncertainSaleKeys[jsonEncode(body)] = key;
        }
      }
    } catch (_) {
      // Corrupt local state must not prevent an operator from opening the POS.
      await _secrets.writePendingSaleIntents('');
    }
  }

  Future<void> _persistUncertainSaleIntents() =>
      _secrets.writePendingSaleIntents(
        jsonEncode({
          'intents': _uncertainSaleKeys.entries.map((entry) => {
                'fingerprint': base64UrlEncode(utf8.encode(entry.key)),
                'payload': jsonDecode(entry.key),
                'idempotency_key': entry.value,
              }),
        }),
      );

  Future<void> forgetDevice() async {
    await _secrets.clearOperatorSession();
    await _secrets.clearDeviceCredential();
    _credentialCache?.cacheOperatorSession(null);
    _credentialCache?.cacheDeviceCredential(null);
    discovery = null;
    challenge = null;
    operators = const [];
    selectedOperator = null;
    bootstrapSnapshot = null;
    deviceError = null;
    errorMessage = null;
    _clearTransientMessage();
    phase = AppPhase.pairingIdentifier;
    notifyListeners();
  }

  Future<void> _run(Future<void> Function() action) async {
    busy = true;
    _clearTransientMessage();
    notifyListeners();
    try {
      await action();
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message, notify: false);
      syncStatus = syncStatus.failed(error.message);
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  void _handleApiError(PosApiException error, {bool persistent = false}) {
    final message = switch (error.statusCode) {
      429 => 'Muitas tentativas. Aguarde alguns instantes e tente novamente.',
      >= 500 =>
        'O CORE PDV está indisponível no momento. Tente novamente em breve.',
      _ => error.message,
    };
    if (error.code == 'pos_update_required') {
      errorMessage = message;
      _clearTransientMessage();
      phase = AppPhase.updateRequired;
      return;
    }
    if (error.isDeviceAccessFailure) {
      errorMessage = message;
      _clearTransientMessage();
      deviceError = error;
      phase = AppPhase.deviceUnavailable;
      return;
    }
    if (persistent) {
      errorMessage = message;
      _clearTransientMessage();
      return;
    }
    _showTransientMessage(message, notify: false);
  }

  void showTransientMessage(
    String message, {
    TransientAlertTone tone = TransientAlertTone.error,
  }) =>
      _showTransientMessage(message, tone: tone);

  void _showTransientMessage(
    String message, {
    TransientAlertTone tone = TransientAlertTone.error,
    bool notify = true,
  }) {
    _transientFeedback.show(message, notifyListeners, tone: tone);
    if (notify) notifyListeners();
  }

  void _clearTransientMessage() {
    _transientFeedback.clear();
  }

  String _idempotencyKeyFor(String payload) =>
      _uncertainCashOperationKeys.putIfAbsent(payload, createIdempotencyKey);

  Future<bool> _runCashAction(
    Future<CashOverview> Function() action,
    String successMessage, {
    String? idempotencyPayload,
  }) async {
    final snapshot = bootstrapSnapshot;
    if (busy || snapshot == null) return false;
    busy = true;
    _clearTransientMessage();
    notifyListeners();
    try {
      bootstrapSnapshot = snapshot.withCash(await action());
      if (idempotencyPayload != null) {
        _uncertainCashOperationKeys.remove(idempotencyPayload);
      }
      syncStatus = syncStatus.succeeded();
      _showTransientMessage(successMessage,
          tone: TransientAlertTone.success, notify: false);
      return true;
    } on PosApiException catch (error) {
      if (idempotencyPayload != null && error.statusCode < 500) {
        _uncertainCashOperationKeys.remove(idempotencyPayload);
      }
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message, notify: false);
      syncStatus = syncStatus.failed(error.message);
    } finally {
      busy = false;
      notifyListeners();
    }
    return false;
  }

  @override
  void dispose() {
    _transientFeedback.dispose();
    super.dispose();
  }
}
