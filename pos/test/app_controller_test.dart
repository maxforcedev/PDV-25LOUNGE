import 'package:flutter_test/flutter_test.dart';

import 'package:core_pos/auth/auth_models.dart';
import 'package:core_pos/bootstrap/bootstrap_models.dart';
import 'package:core_pos/core/app_controller.dart';
import 'package:core_pos/network/pos_api.dart';
import 'package:core_pos/network/pos_api_error.dart';
import 'package:core_pos/pairing/pairing_models.dart';
import 'package:core_pos/storage/secret_store.dart';

void main() {
  const device = DeviceDescriptor(
    name: 'Terminal 01',
    type: 'POS',
    appVersion: '1.0.0',
    osVersion: 'Android',
    model: 'Test',
  );

  test('pairs, stores secrets, authenticates, and requires PIN after reopen', () async {
    final storage = MemorySecretStore();
    final api = FakePosApi();
    final controller = AppController(api: api, secrets: storage, device: device);

    await controller.initialize();
    expect(controller.phase, AppPhase.pairingIdentifier);

    await controller.identify('CORE-ABC');
    expect(controller.phase, AppPhase.pairingChannel);
    await controller.requestOtp(controller.discovery!.channels.single);
    await controller.confirmOtp('123456');
    expect(await storage.readDeviceCredential(), 'device-secret');
    expect(controller.phase, AppPhase.operatorSelection);

    controller.selectOperator(controller.operators.single);
    await controller.login('123456');
    expect(await storage.readOperatorSession(), 'operator-secret');
    expect(controller.phase, AppPhase.home);

    final reopened = AppController(api: api, secrets: storage, device: device);
    await reopened.initialize();
    expect(reopened.phase, AppPhase.operatorSelection);
    expect(await storage.readOperatorSession(), isNull);
  });

  test('blocks operation when the backend requires an update', () async {
    final storage = MemorySecretStore(deviceCredential: 'device-secret');
    final api = FakePosApi(release: const ReleaseInfo(
      currentVersion: '1.0.0',
      latestVersion: '2.0.0',
      minimumSupportedVersion: '2.0.0',
      updateAvailable: true,
      updateRequired: true,
    ));
    final controller = AppController(api: api, secrets: storage, device: device);

    await controller.initialize();

    expect(controller.phase, AppPhase.updateRequired);
  });

  test('shows the device unavailable state for a blocked device', () async {
    final storage = MemorySecretStore(deviceCredential: 'device-secret');
    final controller = AppController(
      api: FakePosApi(heartbeatError: const PosApiException(
        statusCode: 403,
        code: 'device_blocked',
        message: 'Dispositivo bloqueado.',
      )),
      secrets: storage,
      device: device,
    );

    await controller.initialize();

    expect(controller.phase, AppPhase.deviceUnavailable);
    expect(controller.deviceError!.code, 'device_blocked');
  });
}

class MemorySecretStore implements SecretStore {
  MemorySecretStore({this.deviceCredential});

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

class FakePosApi implements PosApi {
  FakePosApi({this.release = const ReleaseInfo(
    currentVersion: '1.0.0',
    latestVersion: '1.0.0',
    minimumSupportedVersion: '1.0.0',
    updateAvailable: false,
    updateRequired: false,
  ), this.heartbeatError});

  final ReleaseInfo release;
  final PosApiException? heartbeatError;
  final operator = const PosOperator(id: '1', displayName: 'Joao', initials: 'J');

  @override
  Future<BootstrapSnapshot> bootstrap() async => BootstrapSnapshot(
        companyName: 'Empresa',
        branchName: 'Centro',
        deviceName: 'Terminal 01',
        operatorName: operator.displayName,
        release: release,
        modules: const [HomeModule(key: 'quick_sale', enabled: true)],
      );

  @override
  Future<String> confirmPairing({required String challengeId, required String code, required DeviceDescriptor device}) async =>
      'device-secret';

  @override
  Future<HeartbeatResult> heartbeat(DeviceDescriptor device) async {
    if (heartbeatError != null) throw heartbeatError!;
    return HeartbeatResult(release: release);
  }

  @override
  Future<PairingDiscovery> identifyBranch(String identifier) async => const PairingDiscovery(
        flowId: 'flow',
        branchName: 'Centro',
        channels: [PairingChannel(id: 'email', type: 'email', masked: 'a***@core.com')],
      );

  @override
  Future<OperatorSession> login(String operatorId, String pin) async =>
      OperatorSession(token: 'operator-secret', operator: operator);

  @override
  Future<void> logout() async {}

  @override
  Future<List<PosOperator>> operators() async => [operator];

  @override
  Future<OtpChallenge> requestOtp(String flowId, String channelId) async =>
      const OtpChallenge(id: 'challenge', destination: 'a***@core.com');
}
