import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:core_pos/auth/auth_models.dart';
import 'package:core_pos/bootstrap/bootstrap_models.dart';
import 'package:core_pos/cash/cash_page.dart';
import 'package:core_pos/cash/cash_models.dart';
import 'package:core_pos/core/app_controller.dart';
import 'package:core_pos/core/transient_feedback.dart';
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

  test('pairs, stores secrets, authenticates, and requires PIN after reopen',
      () async {
    final storage = MemorySecretStore();
    final api = FakePosApi();
    final controller =
        AppController(api: api, secrets: storage, device: device);

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
    final api = FakePosApi(
        release: const ReleaseInfo(
      currentVersion: '1.0.0',
      latestVersion: '2.0.0',
      minimumSupportedVersion: '2.0.0',
      updateAvailable: true,
      updateRequired: true,
    ));
    final controller =
        AppController(api: api, secrets: storage, device: device);

    await controller.initialize();

    expect(controller.phase, AppPhase.updateRequired);
  });

  test('shows the device unavailable state for a blocked device', () async {
    final storage = MemorySecretStore(deviceCredential: 'device-secret');
    final controller = AppController(
      api: FakePosApi(
          heartbeatError: const PosApiException(
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

  test('requests a PIN reset for the selected operator through device auth',
      () async {
    final api = FakePosApi();
    final controller = AppController(
      api: api,
      secrets: MemorySecretStore(deviceCredential: 'device-secret'),
      device: device,
    );

    await controller.initialize();
    controller.selectOperator(api.operator);
    await controller.requestSelectedOperatorPinReset();

    expect(api.pinResetOperatorId, api.operator.id);
    expect(controller.transientAlert!.message,
        'Enviamos as instruções para redefinir seu PIN.');
  });

  test('uses the backend-provided session summary capability', () async {
    final api = FakePosApi();
    final controller =
        AppController(api: api, secrets: MemorySecretStore(), device: device);
    const denied = CashSessionInfo(
      id: 1,
      registerId: 1,
      registerName: 'Caixa',
      status: 'open',
      openedByName: 'Joao',
      openedAt: null,
    );
    const allowed = CashSessionInfo(
      id: 1,
      registerId: 1,
      registerName: 'Caixa',
      status: 'open',
      openedByName: 'Joao',
      openedAt: null,
      canView: true,
    );

    expect(await controller.cashSessionSummary(denied), isNull);
    expect(api.cashSummaryCalls, 0);

    expect(await controller.cashSessionSummary(allowed), isNotNull);
    expect(api.cashSummaryCalls, 1);
  });

  test('uses the cash state returned by a successful cash action', () async {
    final failingApi = FakePosApi(
      cashEntryError: const PosApiException(
          statusCode: 400, code: 'invalid_entry', message: 'Entrada inválida.'),
    );
    final failingController = AppController(
        api: failingApi, secrets: MemorySecretStore(), device: device);
    failingController.bootstrapSnapshot = await failingApi.bootstrap();

    expect(
        await failingController.recordCashEntry(
            sessionId: 1, amount: '10.00', reason: 'Troco'),
        isFalse);
    expect(failingApi.cashOverviewCalls, 0);

    final api = FakePosApi();
    final controller =
        AppController(api: api, secrets: MemorySecretStore(), device: device);
    controller.bootstrapSnapshot = await api.bootstrap();

    expect(
        await controller.recordCashEntry(
            sessionId: 1, amount: '10.00', reason: 'Troco'),
        isTrue);
    expect(api.cashOverviewCalls, 0);
  });

  testWidgets(
      'requests one summary when a cash overview refresh changes the session',
      (tester) async {
    final api = FakePosApi(
      cashOverviewResponse: const CashOverview(
        mode: 'FIXED',
        enabled: true,
        session: CashSessionInfo(
          id: 1,
          registerId: 1,
          registerName: 'Caixa',
          status: 'open',
          openedByName: 'Joao',
          openedAt: null,
          canView: true,
        ),
      ),
    );
    final controller =
        AppController(api: api, secrets: MemorySecretStore(), device: device);
    controller.bootstrapSnapshot = BootstrapSnapshot(
      companyName: 'Empresa',
      branchName: 'Centro',
      deviceName: 'Terminal 01',
      operatorName: 'Joao',
      release: api.release,
      modules: const [],
      permissions: const {'cash_registers.view'},
      cash: const CashOverview(mode: 'FIXED', enabled: true),
    );

    await tester
        .pumpWidget(MaterialApp(home: CashPage(controller: controller)));
    await tester.pump();
    expect(api.cashSummaryCalls, 0);

    await tester.tap(find.byTooltip('Atualizar caixa'));
    await tester.pumpAndSettle();

    expect(api.cashSummaryCalls, 1);
  });
}

class MemorySecretStore implements SecretStore {
  MemorySecretStore({this.deviceCredential});

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

class FakePosApi implements PosApi {
  FakePosApi(
      {this.release = const ReleaseInfo(
        currentVersion: '1.0.0',
        latestVersion: '1.0.0',
        minimumSupportedVersion: '1.0.0',
        updateAvailable: false,
        updateRequired: false,
      ),
      this.heartbeatError,
      this.cashEntryError,
      this.cashOverviewError,
      this.cashOverviewResponse});

  final ReleaseInfo release;
  final PosApiException? heartbeatError;
  final PosApiException? cashEntryError;
  final PosNetworkException? cashOverviewError;
  final CashOverview? cashOverviewResponse;
  final operator =
      const PosOperator(id: '1', displayName: 'Joao', initials: 'J');
  String? pinResetOperatorId;
  int cashOverviewCalls = 0;
  int cashSummaryCalls = 0;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);

  @override
  Future<BootstrapSnapshot> bootstrap() async => BootstrapSnapshot(
        companyName: 'Empresa',
        branchName: 'Centro',
        deviceName: 'Terminal 01',
        operatorName: operator.displayName,
        release: release,
        modules: const [HomeModule(key: 'quick_sale', enabled: true)],
        cash: const CashOverview(mode: 'FLEXIBLE', enabled: true),
      );

  @override
  Future<CashOverview> cashOverview() async {
    cashOverviewCalls++;
    if (cashOverviewError != null) throw cashOverviewError!;
    return cashOverviewResponse ??
        const CashOverview(mode: 'FLEXIBLE', enabled: true);
  }

  @override
  Future<List<CashBeneficiary>> cashWithdrawalBeneficiaries(
          String category) async =>
      const [];

  @override
  Future<CashOverview> closeCashSession(
          {required int sessionId, required String closingAmount}) async =>
      _cashMutationResponse;

  @override
  Future<CashSessionSummary> cashSessionSummary(int sessionId) async {
    cashSummaryCalls++;
    return const CashSessionSummary(
      status: 'open',
      openingAmount: '0.00',
      manualEntries: '0.00',
      withdrawals: '0.00',
      cashPayments: '0.00',
      expectedAmount: '0.00',
    );
  }

  @override
  Future<String> confirmPairing(
          {required String challengeId,
          required String code,
          required DeviceDescriptor device}) async =>
      'device-secret';

  @override
  Future<HeartbeatResult> heartbeat(DeviceDescriptor device) async {
    if (heartbeatError != null) throw heartbeatError!;
    return HeartbeatResult(release: release);
  }

  @override
  Future<PairingDiscovery> identifyBranch(String identifier) async =>
      const PairingDiscovery(
        flowId: 'flow',
        branchName: 'Centro',
        channels: [
          PairingChannel(id: 'email', type: 'email', masked: 'a***@core.com')
        ],
      );

  @override
  Future<OperatorSession> login(String operatorId, String pin) async =>
      OperatorSession(token: 'operator-secret', operator: operator);

  @override
  Future<CashOverview> openCashSession(
          {required String openingAmount, int? registerId}) async =>
      _cashMutationResponse;

  @override
  Future<void> logout() async {}

  @override
  Future<List<PosOperator>> operators() async => [operator];

  @override
  Future<void> requestOperatorPinReset(String operatorId) async =>
      pinResetOperatorId = operatorId;

  @override
  Future<OtpChallenge> requestOtp(String flowId, String channelId) async =>
      const OtpChallenge(id: 'challenge', destination: 'a***@core.com');

  @override
  Future<CashOverview> recordCashEntry(
      {required int sessionId,
      required String amount,
      required String reason,
      required String idempotencyKey}) async {
    if (cashEntryError != null) throw cashEntryError!;
    return _cashMutationResponse;
  }

  @override
  Future<CashOverview> recordCashWithdrawal(
          {required int sessionId,
          required String amount,
          required String reason,
          required String category,
          String? beneficiaryType,
          int? beneficiaryId,
          required String idempotencyKey}) async =>
      _cashMutationResponse;

  CashOverview get _cashMutationResponse =>
      cashOverviewResponse ??
      const CashOverview(mode: 'FLEXIBLE', enabled: true);
}
