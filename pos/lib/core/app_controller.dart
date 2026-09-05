import 'package:flutter/foundation.dart';

import '../auth/auth_models.dart';
import '../bootstrap/bootstrap_models.dart';
import '../network/pos_api.dart';
import '../network/pos_api_error.dart';
import '../pairing/pairing_models.dart';
import '../storage/secret_store.dart';
import '../sync/sync_status.dart';

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

  AppPhase phase = AppPhase.loading;
  bool busy = false;
  String? errorMessage;
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
      errorMessage = 'Informe o codigo de seis digitos.';
      notifyListeners();
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
      errorMessage = null;
      notifyListeners();
    }
    try {
      syncStatus = const SyncStatus(phase: SyncPhase.syncing);
      final heartbeat = await _api.heartbeat(_device);
      if (heartbeat.release.updateRequired) {
        phase = AppPhase.updateRequired;
        return;
      }
      operators = await _api.operators();
      selectedOperator = null;
      phase = AppPhase.operatorSelection;
      syncStatus = SyncStatus(phase: SyncPhase.synced, lastSyncedAt: DateTime.now());
    } on PosApiException catch (error) {
      _handleApiError(error);
      if (phase == AppPhase.loading || phase == AppPhase.operatorSelection) {
        phase = AppPhase.error;
      }
    } on PosNetworkException catch (error) {
      errorMessage = error.message;
      syncStatus = SyncStatus(phase: SyncPhase.error, error: error.message);
      phase = AppPhase.error;
    } finally {
      busy = false;
      if (notify) notifyListeners();
    }
  }

  void selectOperator(PosOperator operator) {
    selectedOperator = operator;
    errorMessage = null;
    notifyListeners();
  }

  Future<void> login(String pin) async {
    final operator = selectedOperator;
    if (operator == null || !RegExp(r'^\d{6}$').hasMatch(pin)) {
      errorMessage = 'Informe o PIN de seis digitos.';
      notifyListeners();
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
      syncStatus = SyncStatus(phase: SyncPhase.synced, lastSyncedAt: DateTime.now());
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
    phase = AppPhase.pairingIdentifier;
    notifyListeners();
  }

  Future<void> _run(Future<void> Function() action) async {
    busy = true;
    errorMessage = null;
    notifyListeners();
    try {
      await action();
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      errorMessage = error.message;
      syncStatus = SyncStatus(phase: SyncPhase.error, error: error.message);
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  void _handleApiError(PosApiException error) {
    errorMessage = switch (error.statusCode) {
      400 => 'Confira o CNPJ ou o código de licenciamento e tente novamente.',
      403 => 'Esta filial não está disponível para pareamento no momento.',
      404 => 'Não encontramos uma filial com estes dados.',
      429 => 'Muitas tentativas. Aguarde alguns instantes e tente novamente.',
      >= 500 => 'O CORE PDV está indisponível no momento. Tente novamente em breve.',
      _ => error.message,
    };
    if (error.code == 'pos_update_required') {
      phase = AppPhase.updateRequired;
      return;
    }
    if (error.isDeviceAccessFailure) {
      deviceError = error;
      phase = AppPhase.deviceUnavailable;
      return;
    }
  }
}
