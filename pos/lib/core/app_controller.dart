import 'package:flutter/foundation.dart';

import '../auth/auth_models.dart';
import '../bootstrap/bootstrap_models.dart';
import '../cash/cash_models.dart';
import '../network/pos_api.dart';
import '../network/pos_api_error.dart';
import '../pairing/pairing_models.dart';
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

  AppPhase phase = AppPhase.loading;
  bool busy = false;
  String? errorMessage;
  TransientAlert? get transientAlert => _transientFeedback.alert;
  PairingDiscovery? discovery;
  OtpChallenge? challenge;
  List<PosOperator> operators = const [];
  PosOperator? selectedOperator;
  BootstrapSnapshot? bootstrapSnapshot;
  SyncStatus syncStatus = const SyncStatus();
  PosApiException? deviceError;

  Future<void> initialize() async {
    await _secrets.clearOperatorSession();
    if (await _secrets.readDeviceCredential() == null) {
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
      syncStatus = syncStatus.succeeded('Dispositivo e operadores atualizados.');
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
      try {
        bootstrapSnapshot = await _api.bootstrap();
      } catch (_) {
        await _secrets.clearOperatorSession();
        rethrow;
      }
      if (bootstrapSnapshot!.release.updateRequired) {
        phase = AppPhase.updateRequired;
        return;
      }
      syncStatus = syncStatus.succeeded('Dados operacionais atualizados.');
      phase = AppPhase.home;
    });
  }

  Future<void> logout() async {
    try {
      await _api.logout();
    } catch (_) {
      // The local operator session must still be removed on a failed logout request.
    } finally {
      await _secrets.clearOperatorSession();
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
      syncStatus = syncStatus.succeeded('Dados operacionais atualizados.');
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

  Future<void> refreshCashOverview() async {
    final snapshot = bootstrapSnapshot;
    if (busy || snapshot == null) return;
    busy = true;
    _clearTransientMessage();
    notifyListeners();
    try {
      bootstrapSnapshot = snapshot.withCash(await _api.cashOverview());
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message, notify: false);
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<void> openCashSession({required String openingAmount, int? registerId}) => _runCashAction(
        () => _api.openCashSession(openingAmount: openingAmount, registerId: registerId),
        'Caixa aberto com sucesso.',
      );

  Future<void> recordCashEntry({required int sessionId, required String amount, required String reason}) => _runCashAction(
        () => _api.recordCashEntry(
          sessionId: sessionId,
          amount: amount,
          reason: reason,
          idempotencyKey: createIdempotencyKey(),
        ),
        'Suprimento registrado com sucesso.',
      );

  Future<void> recordCashWithdrawal({required int sessionId, required String amount, required String reason, required String category}) => _runCashAction(
        () => _api.recordCashWithdrawal(
          sessionId: sessionId,
          amount: amount,
          reason: reason,
          category: category,
          resultEffect: 'operating_expense',
          idempotencyKey: createIdempotencyKey(),
        ),
        'Sangria registrada com sucesso.',
      );

  Future<void> closeCashSession({required int sessionId, required String closingAmount}) => _runCashAction(
        () => _api.closeCashSession(sessionId: sessionId, closingAmount: closingAmount),
        'Caixa fechado com sucesso.',
      );

  Future<CashSessionSummary?> cashSessionSummary(int sessionId) async {
    try {
      return await _api.cashSessionSummary(sessionId);
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<void> forgetDevice() async {
    await _secrets.clearOperatorSession();
    await _secrets.clearDeviceCredential();
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
      >= 500 => 'O CORE PDV está indisponível no momento. Tente novamente em breve.',
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
  }) => _showTransientMessage(message, tone: tone);

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

  Future<void> _runCashAction(Future<void> Function() action, String successMessage) async {
    final snapshot = bootstrapSnapshot;
    if (busy || snapshot == null) return;
    busy = true;
    _clearTransientMessage();
    notifyListeners();
    try {
      await action();
      bootstrapSnapshot = snapshot.withCash(await _api.cashOverview());
      syncStatus = syncStatus.succeeded('Caixa atualizado.');
      _showTransientMessage(successMessage, tone: TransientAlertTone.success, notify: false);
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message, notify: false);
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _transientFeedback.dispose();
    super.dispose();
  }
}
