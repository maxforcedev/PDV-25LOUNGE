import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../auth/auth_models.dart';
import '../attendance/attendance_models.dart';
import '../bootstrap/bootstrap_models.dart';
import '../cash/cash_models.dart';
import '../network/pos_api.dart';
import '../network/pos_api_error.dart';
import '../pairing/pairing_models.dart';
import '../sales/sale_models.dart';
import '../storage/secret_store.dart';
import '../sync/sync_status.dart';
import '../tickets/ticket_models.dart';
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

  String? get _quickCheckoutOperatorId => selectedOperator?.id;

  Future<Map<String, dynamic>> _quickCheckoutStorage() async {
    final encoded = await _secrets.readQuickSaleCheckoutState();
    if (encoded == null || encoded.isEmpty) return <String, dynamic>{};
    try {
      return Map<String, dynamic>.from(jsonDecode(encoded) as Map);
    } catch (_) {
      await _secrets.writeQuickSaleCheckoutState('');
      return <String, dynamic>{};
    }
  }

  Future<Map<String, dynamic>> _quickCheckoutState() async {
    final operatorId = _quickCheckoutOperatorId;
    if (operatorId == null) return <String, dynamic>{};
    final storage = await _quickCheckoutStorage();
    final states = storage['operators'];
    if (states is Map && states[operatorId] is Map) {
      return Map<String, dynamic>.from(states[operatorId] as Map);
    }

    // A legacy record can only be recovered when it explicitly names its owner.
    if (storage['operator_id'] == operatorId) {
      return Map<String, dynamic>.from(storage)
        ..remove('operator_id')
        ..remove('operators');
    }
    return <String, dynamic>{};
  }

  Future<void> _writeQuickCheckoutState(Map<String, dynamic> state) async {
    final operatorId = _quickCheckoutOperatorId;
    if (operatorId == null) return;
    final storage = await _quickCheckoutStorage();
    final states =
        Map<String, dynamic>.from(storage['operators'] as Map? ?? const {});
    if (state.isEmpty) {
      states.remove(operatorId);
    } else {
      states[operatorId] = state;
    }
    if (states.isEmpty) {
      storage.remove('operators');
    } else {
      storage['operators'] = states;
    }
    if (storage['operator_id'] == operatorId) {
      for (final key in [
        'operator_id',
        'checkout_id',
        'creation_idempotency_key',
        'creation_request',
        'pending',
      ]) {
        storage.remove(key);
      }
    }
    await _secrets.writeQuickSaleCheckoutState(jsonEncode(storage));
  }

  bool _isTerminalQuickSaleCheckout(QuickSaleCheckout checkout) =>
      checkout.status == 'finalized' || checkout.status == 'cancelled';

  Future<QuickSaleCheckout?> recoverQuickSaleCheckout() async {
    final state = await _quickCheckoutState();
    final id = state['checkout_id'] as String?;
    try {
      if (id != null) {
        final checkout = await _api.getQuickSaleCheckout(id);
        if (_isTerminalQuickSaleCheckout(checkout)) {
          await _writeQuickCheckoutState({});
          return null;
        }
        return checkout;
      }
      final creationKey = state['creation_idempotency_key'] as String?;
      if (creationKey == null) return null;
      final checkout = await _api.recoverQuickSaleCheckout(creationKey);
      if (_isTerminalQuickSaleCheckout(checkout)) {
        await _writeQuickCheckoutState({});
        return null;
      }
      await _writeQuickCheckoutState({'checkout_id': checkout.id});
      return checkout;
    } on PosApiException catch (error) {
      if (error.statusCode < 500) await _writeQuickCheckoutState({});
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<QuickSaleCheckout?> createQuickSaleCheckout({
    required List<Map<String, dynamic>> items,
    required int cashSessionId,
    required Map<String, dynamic> discount,
    required bool serviceFeeWaived,
    QuickSaleCustomer? customer,
    QuickSaleAuthorization? discountAuthorization,
    QuickSaleAuthorization? itemDiscountAuthorization,
    QuickSaleAuthorization? serviceFeeAuthorization,
  }) async {
    var state = await _quickCheckoutState();
    final existing = state['checkout_id'] as String?;
    if (existing != null) {
      final checkout = await recoverQuickSaleCheckout();
      if (checkout == null || !checkout.canEditFinancials) return checkout;
      if (_quickCheckoutNeedsUpdate(
        checkout: checkout,
        items: items,
        cashSessionId: cashSessionId,
        discount: discount,
        serviceFeeWaived: serviceFeeWaived,
        customerId: customer?.id,
      )) {
        return updateQuickSaleCheckout(
          checkoutId: checkout.id,
          items: items,
          cashSessionId: cashSessionId,
          discount: discount,
          serviceFeeWaived: serviceFeeWaived,
          customerId: customer?.id,
          discountAuthorization: discountAuthorization,
          itemDiscountAuthorization: itemDiscountAuthorization,
          serviceFeeAuthorization: serviceFeeAuthorization,
        );
      }
      return checkout;
    }

    final request = _quickCheckoutCreationRequest(
      items: items,
      cashSessionId: cashSessionId,
      discount: discount,
      serviceFeeWaived: serviceFeeWaived,
      customer: customer,
      discountAuthorization: discountAuthorization,
      itemDiscountAuthorization: itemDiscountAuthorization,
      serviceFeeAuthorization: serviceFeeAuthorization,
    );
    var key = state['creation_idempotency_key'] as String?;
    if (key != null &&
        jsonEncode(state['creation_request']) != jsonEncode(request)) {
      try {
        final checkout = await _api.recoverQuickSaleCheckout(key);
        await _writeQuickCheckoutState({'checkout_id': checkout.id});
        return await updateQuickSaleCheckout(
          checkoutId: checkout.id,
          items: items,
          cashSessionId: cashSessionId,
          discount: discount,
          serviceFeeWaived: serviceFeeWaived,
          customerId: customer?.id,
          discountAuthorization: discountAuthorization,
          itemDiscountAuthorization: itemDiscountAuthorization,
          serviceFeeAuthorization: serviceFeeAuthorization,
        );
      } on PosApiException catch (error) {
        if (error.statusCode != 404) {
          _handleApiError(error);
          return null;
        }
        state = <String, dynamic>{};
        key = null;
      } on PosNetworkException catch (error) {
        _showTransientMessage(error.message);
        return null;
      }
    }

    final creationKey = key ?? createIdempotencyKey();
    state = {
      'creation_idempotency_key': creationKey,
      'creation_request': request,
    };
    await _writeQuickCheckoutState(
        state); // Preserve the immutable request before an uncertain create.
    try {
      final checkout = await _api.createQuickSaleCheckout(
        items: items,
        cashSessionId: cashSessionId,
        discount: discount,
        serviceFeeWaived: serviceFeeWaived,
        idempotencyKey: creationKey,
        customerId: customer?.id,
        discountAuthorization: discountAuthorization?.toJson(),
        itemDiscountAuthorization: itemDiscountAuthorization?.toJson(),
        serviceFeeAuthorization: serviceFeeAuthorization?.toJson(),
      );
      await _writeQuickCheckoutState({'checkout_id': checkout.id});
      return checkout;
    } on PosApiException catch (error) {
      if (error.statusCode < 500) await _writeQuickCheckoutState({});
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Map<String, dynamic> _quickCheckoutCreationRequest({
    required List<Map<String, dynamic>> items,
    required int cashSessionId,
    required Map<String, dynamic> discount,
    required bool serviceFeeWaived,
    QuickSaleCustomer? customer,
    QuickSaleAuthorization? discountAuthorization,
    QuickSaleAuthorization? itemDiscountAuthorization,
    QuickSaleAuthorization? serviceFeeAuthorization,
  }) =>
      Map<String, dynamic>.from(jsonDecode(jsonEncode({
        'items': items,
        'cash_session': cashSessionId,
        'discount': discount,
        'service_fee_waived': serviceFeeWaived,
        'customer': customer?.id,
        if (discountAuthorization != null)
          'discount_authorization': discountAuthorization.idempotencyIdentity,
        if (itemDiscountAuthorization != null)
          'item_discount_authorization':
              itemDiscountAuthorization.idempotencyIdentity,
        if (serviceFeeAuthorization != null)
          'service_fee_authorization':
              serviceFeeAuthorization.idempotencyIdentity,
      })) as Map);

  bool _quickCheckoutNeedsUpdate({
    required QuickSaleCheckout checkout,
    required List<Map<String, dynamic>> items,
    required int cashSessionId,
    required Map<String, dynamic> discount,
    required bool serviceFeeWaived,
    required int? customerId,
  }) =>
      jsonEncode(checkout.items.map((item) => item.input).toList()) !=
          jsonEncode(items) ||
      checkout.cashSessionId != cashSessionId ||
      jsonEncode(checkout.discountIntent.toJson()) != jsonEncode(discount) ||
      checkout.serviceFeeWaived != serviceFeeWaived ||
      checkout.customer?.id != customerId;

  Future<QuickSaleCheckout?> recordQuickSalePayment({
    required String checkoutId,
    required int paymentMethodId,
    required String mode,
    required String paymentIntentId,
    String? amount,
    String? receivedAmount,
    List<Map<String, dynamic>> allocations = const [],
  }) async {
    final state = await _quickCheckoutState();
    final attempts = Map<String, dynamic>.from(
        state['payment_attempts'] as Map? ?? const {});
    final stored = attempts[paymentIntentId];
    final attempt = stored is Map
        ? QuickSalePaymentAttempt.fromJson(Map<String, dynamic>.from(stored))
        : QuickSalePaymentAttempt(
            intentId: paymentIntentId,
            paymentMethodId: paymentMethodId,
            mode: mode,
            amount: amount,
            receivedAmount: receivedAmount,
            allocations: allocations,
          );
    attempts[attempt.intentId] = attempt.toJson();
    state['checkout_id'] = checkoutId;
    state['payment_attempts'] = attempts;
    // A payment intent is an operator action, not a fingerprint of its value.
    await _writeQuickCheckoutState(state);
    try {
      final checkout = await _api.recordQuickSalePayment(
        checkoutId: checkoutId,
        paymentMethodId: attempt.paymentMethodId,
        mode: attempt.mode,
        amount: attempt.amount,
        receivedAmount: attempt.receivedAmount,
        allocations: attempt.allocations,
        idempotencyKey: attempt.intentId,
      );
      await _clearQuickSalePaymentAttempt(state, attempt.intentId);
      return checkout;
    } on PosApiException catch (error) {
      if (error.statusCode < 500) {
        await _clearQuickSalePaymentAttempt(state, attempt.intentId);
      }
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<QuickSalePaymentAttempt?> pendingQuickSalePayment(
      String checkoutId) async {
    final state = await _quickCheckoutState();
    if (state['checkout_id'] != checkoutId) return null;
    final attempts = Map<String, dynamic>.from(
        state['payment_attempts'] as Map? ?? const {});
    for (final raw in attempts.values) {
      if (raw is Map) {
        return QuickSalePaymentAttempt.fromJson(Map<String, dynamic>.from(raw));
      }
    }
    return null;
  }

  Future<void> _clearQuickSalePaymentAttempt(
      Map<String, dynamic> state, String intentId) async {
    final attempts = Map<String, dynamic>.from(
        state['payment_attempts'] as Map? ?? const {});
    attempts.remove(intentId);
    if (attempts.isEmpty) {
      state.remove('payment_attempts');
    } else {
      state['payment_attempts'] = attempts;
    }
    await _writeQuickCheckoutState(state);
  }

  Future<QuickSaleCheckout?> updateQuickSaleCheckout({
    required String checkoutId,
    required List<Map<String, dynamic>> items,
    required int cashSessionId,
    required Map<String, dynamic> discount,
    required bool serviceFeeWaived,
    int? customerId,
    QuickSaleAuthorization? discountAuthorization,
    QuickSaleAuthorization? itemDiscountAuthorization,
    QuickSaleAuthorization? serviceFeeAuthorization,
  }) async {
    try {
      return await _api.updateQuickSaleCheckout(
        checkoutId: checkoutId,
        items: items,
        cashSessionId: cashSessionId,
        discount: discount,
        serviceFeeWaived: serviceFeeWaived,
        customerId: customerId,
        discountAuthorization: discountAuthorization?.toJson(),
        itemDiscountAuthorization: itemDiscountAuthorization?.toJson(),
        serviceFeeAuthorization: serviceFeeAuthorization?.toJson(),
      );
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<QuickSaleCheckout?> reverseQuickSalePayment({
    required String checkoutId,
    required String paymentId,
    String reason = '',
  }) =>
      _runQuickCheckoutOperation(
        checkoutId: checkoutId,
        operation: 'reverse:$paymentId:$reason',
        call: (key) => _api.reverseQuickSalePayment(
          checkoutId: checkoutId,
          paymentId: paymentId,
          reason: reason,
          idempotencyKey: key,
        ),
      );

  Future<bool> cancelQuickSaleCheckout(String checkoutId) async {
    try {
      await _api.cancelQuickSaleCheckout(checkoutId: checkoutId);
      await _writeQuickCheckoutState({});
      return true;
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return false;
  }

  Future<QuickSaleCheckout?> _runQuickCheckoutOperation({
    required String checkoutId,
    required String operation,
    required Future<QuickSaleCheckout> Function(String key) call,
  }) async {
    final state = await _quickCheckoutState();
    final pending =
        Map<String, dynamic>.from(state['pending'] as Map? ?? const {});
    final key = pending[operation] as String? ?? createIdempotencyKey();
    pending[operation] = key;
    state['checkout_id'] = checkoutId;
    state['pending'] = pending;
    await _writeQuickCheckoutState(state);
    try {
      final checkout = await call(key);
      pending.remove(operation);
      state['pending'] = pending;
      await _writeQuickCheckoutState(state);
      return checkout;
    } on PosApiException catch (error) {
      if (error.statusCode < 500) {
        pending.remove(operation);
        state['pending'] = pending;
        await _writeQuickCheckoutState(state);
      }
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<QuickSalePaymentPreview?> previewQuickSalePayment({
    required String checkoutId,
    required List<Map<String, dynamic>> allocations,
  }) async {
    try {
      return await _api.previewQuickSalePayment(
          checkoutId: checkoutId, allocations: allocations);
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<QuickSaleResult?> finalizeQuickSaleCheckout(String checkoutId) async {
    final state = await _quickCheckoutState();
    final pending =
        Map<String, dynamic>.from(state['pending'] as Map? ?? const {});
    const operation = 'finalize';
    final key = pending[operation] as String? ?? createIdempotencyKey();
    pending[operation] = key;
    await _writeQuickCheckoutState(
        {'checkout_id': checkoutId, 'pending': pending});
    try {
      final result = await _api.finalizeQuickSaleCheckout(
          checkoutId: checkoutId, idempotencyKey: key);
      await _writeQuickCheckoutState({});
      return result;
    } on PosApiException catch (error) {
      if (error.statusCode < 500) {
        pending.remove(operation);
        await _writeQuickCheckoutState(
            {'checkout_id': checkoutId, 'pending': pending});
      }
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

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
    // Operator sessions are intentionally not resumed after reopening the POS.
    await _secrets.clearOperatorSession();
    _credentialCache?.cacheOperatorSession(null);
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

  Future<QuickSaleCustomer?> activateQuickSaleCustomer(int customerId) async {
    try {
      return await _api.activateQuickSaleCustomer(customerId);
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<List<AttendanceTable>?> attendanceTables() async {
    try {
      return await _api.attendanceTables();
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<bool> groupAttendanceTables({
    required List<int> tableIds,
    required String idempotencyKey,
  }) async {
    final result = await _attendance<bool>(() async {
      await _api.groupAttendanceTables(
        tableIds: tableIds,
        idempotencyKey: idempotencyKey,
      );
      return true;
    });
    return result != null;
  }

  Future<bool> separateAttendanceTable({
    required int tableId,
    required String idempotencyKey,
  }) async {
    final result = await _attendance<bool>(() async {
      await _api.separateAttendanceTable(
        tableId: tableId,
        idempotencyKey: idempotencyKey,
      );
      return true;
    });
    return result != null;
  }

  Future<TableAttendance?> openAttendanceTable({
    required int tableId,
    required String idempotencyKey,
    int? peopleCount,
    String responsibleName = '',
    int? customerId,
    String notes = '',
  }) async {
    try {
      return await _api.openAttendanceTable(
        tableId: tableId,
        idempotencyKey: idempotencyKey,
        peopleCount: peopleCount,
        responsibleName: responsibleName,
        customerId: customerId,
        notes: notes,
      );
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<TableAttendance?> tableAttendanceDetail(int attendanceId) =>
      _attendance(() => _api.tableAttendanceDetail(attendanceId));

  Future<List<QuickSaleProduct>?> tableCatalog({String? search}) =>
      _attendance(() => _api.tableCatalog(search: search));

  Future<QuickSaleStockAvailability?> tableStockAvailability({
    required List<Map<String, dynamic>> items,
  }) =>
      _attendance(() => _api.tableStockAvailability(items: items));

  Future<Map<String, dynamic>?> tableOrderPreview({
    required int attendanceId,
    required List<Map<String, dynamic>> items,
  }) =>
      _attendance(() => _api.tableOrderPreview(
            attendanceId: attendanceId,
            items: items,
          ));

  Future<List<TableOrderItem>?> saveTableOrder({
    required int attendanceId,
    required List<Map<String, dynamic>> items,
    required String idempotencyKey,
  }) =>
      _attendance(() => _api.saveTableOrder(
            attendanceId: attendanceId,
            items: items,
            idempotencyKey: idempotencyKey,
          ));

  Future<TableOrderItem?> cancelTableOrderItem({
    required int itemId,
    required String reason,
    required String idempotencyKey,
  }) =>
      _attendance(() => _api.cancelTableOrderItem(
            itemId: itemId,
            reason: reason,
            idempotencyKey: idempotencyKey,
          ));

  Future<TableOrderItem?> setTableOrderItemDiscount({
    required int itemId,
    required Object discount,
    required String idempotencyKey,
    Map<String, dynamic>? authorization,
  }) =>
      _attendance(() => _api.setTableOrderItemDiscount(
            itemId: itemId,
            discount: discount,
            idempotencyKey: idempotencyKey,
            authorization: authorization,
          ));

  Future<TableOrder?> cancelTableOrder({
    required int orderId,
    required String reason,
    required String idempotencyKey,
  }) =>
      _attendance(() => _api.cancelTableOrder(
            orderId: orderId,
            reason: reason,
            idempotencyKey: idempotencyKey,
          ));

  Future<TableAttendance?> setTableBillRequested({
    required int attendanceId,
    required bool requested,
    required String idempotencyKey,
  }) =>
      _attendance(() => _api.setTableBillRequested(
            attendanceId: attendanceId,
            requested: requested,
            idempotencyKey: idempotencyKey,
          ));

  Future<TableAttendance?> setTableAttendanceCustomer({
    required int attendanceId,
    required int? customerId,
    required String idempotencyKey,
  }) =>
      _attendance(() => _api.setTableAttendanceCustomer(
            attendanceId: attendanceId,
            customerId: customerId,
            idempotencyKey: idempotencyKey,
          ));

  Future<TableAttendance?> setTableCheckoutContext({
    required int attendanceId,
    required Object discount,
    required bool serviceFeeWaived,
    required String idempotencyKey,
    Map<String, dynamic>? discountAuthorization,
    Map<String, dynamic>? serviceFeeAuthorization,
  }) =>
      _attendance(() => _api.setTableCheckoutContext(
            attendanceId: attendanceId,
            discount: discount,
            serviceFeeWaived: serviceFeeWaived,
            idempotencyKey: idempotencyKey,
            discountAuthorization: discountAuthorization,
            serviceFeeAuthorization: serviceFeeAuthorization,
          ));

  Future<TableAttendance?> transferTableItems({
    required int attendanceId,
    required int destinationAttendanceId,
    required List<Map<String, dynamic>> items,
    required String idempotencyKey,
  }) =>
      _attendance(() => _api.transferTableItems(
            attendanceId: attendanceId,
            destinationAttendanceId: destinationAttendanceId,
            items: items,
            idempotencyKey: idempotencyKey,
          ));

  Future<List<AttendanceCommand>?> attendanceCommands({String? query}) async {
    try {
      return await _api.attendanceCommands(query: query);
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<List<QuickSaleProduct>?> attendanceCatalog({String? search}) =>
      _attendance(() => _api.attendanceCatalog(search: search));

  Future<QuickSaleCheckoutOptions?> attendanceCheckoutOptions() =>
      _attendance(_api.attendanceCheckoutOptions);

  Future<AttendanceCommand?> openAttendanceCommand({
    required String idempotencyKey,
    String identifier = '',
    int? tableId,
    int? customerId,
    int? peopleCount,
    String notes = '',
  }) async {
    try {
      return await _api.openAttendanceCommand(
        idempotencyKey: idempotencyKey,
        identifier: identifier,
        tableId: tableId,
        customerId: customerId,
        peopleCount: peopleCount,
        notes: notes,
      );
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<AttendanceCommandDetail?> attendanceCommandDetail(int commandId) =>
      _attendance(() => _api.attendanceCommandDetail(commandId));

  Future<AttendanceCommand?> setAttendanceBillRequested({
    required int commandId,
    required bool requested,
    required String idempotencyKey,
  }) =>
      _attendance(() => _api.setAttendanceBillRequested(
            commandId: commandId,
            requested: requested,
            idempotencyKey: idempotencyKey,
          ));

  Future<List<AttendanceOrderItem>?> addAttendanceItems({
    required int commandId,
    required List<Map<String, dynamic>> items,
    required String idempotencyKey,
  }) =>
      _attendance(() => _api.addAttendanceItems(
            commandId: commandId,
            items: items,
            idempotencyKey: idempotencyKey,
          ));

  Future<AttendanceOrderItem?> confirmAttendanceItem({
    required int itemId,
    required String idempotencyKey,
  }) =>
      _attendance(() => _api.confirmAttendanceItem(
          itemId: itemId, idempotencyKey: idempotencyKey));

  Future<AttendanceOrderItem?> cancelAttendanceItem({
    required int itemId,
    required String idempotencyKey,
    String reason = '',
  }) =>
      _attendance(() => _api.cancelAttendanceItem(
          itemId: itemId, idempotencyKey: idempotencyKey, reason: reason));

  Future<AttendanceLedger?> attendanceLedger(int commandId) =>
      _attendance(() => _api.attendanceLedger(commandId));

  Future<AttendancePayment?> recordAttendancePayment({
    required int commandId,
    required int paymentMethodId,
    required String amount,
    required String idempotencyKey,
    String? receivedAmount,
    int? cashSessionId,
  }) =>
      _attendance(() => _api.recordAttendancePayment(
            commandId: commandId,
            paymentMethodId: paymentMethodId,
            amount: amount,
            idempotencyKey: idempotencyKey,
            receivedAmount: receivedAmount,
            cashSessionId: cashSessionId,
          ));

  Future<AttendancePayment?> reverseAttendancePayment({
    required int paymentId,
    required String idempotencyKey,
    String reason = '',
  }) =>
      _attendance(() => _api.reverseAttendancePayment(
          paymentId: paymentId,
          idempotencyKey: idempotencyKey,
          reason: reason));

  Future<AttendanceCommand?> finalizeAttendanceCommand({
    required int commandId,
    required int cashSessionId,
    required String idempotencyKey,
  }) =>
      _attendance(() => _api.finalizeAttendanceCommand(
          commandId: commandId,
          cashSessionId: cashSessionId,
          idempotencyKey: idempotencyKey));

  Future<AttendanceCommand?> transferAttendanceCommand({
    required int commandId,
    required int? tableId,
    required String idempotencyKey,
  }) =>
      _attendance(() => _api.transferAttendanceCommand(
          commandId: commandId,
          tableId: tableId,
          idempotencyKey: idempotencyKey));

  Future<AttendanceCommand?> transferAttendanceItems({
    required int commandId,
    required int destinationCommandId,
    required List<Map<String, dynamic>> items,
    required String idempotencyKey,
  }) =>
      _attendance(() => _api.transferAttendanceItems(
          commandId: commandId,
          destinationCommandId: destinationCommandId,
          items: items,
          idempotencyKey: idempotencyKey));

  Future<T?> _attendance<T>(Future<T> Function() request) async {
    try {
      return await request();
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

  Future<CashSessionSummary?> cashSessionSummary(
      CashSessionInfo session) async {
    if (!session.canView) {
      return null;
    }
    try {
      return await _api.cashSessionSummary(session.id);
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

  Future<TicketValidationResult?> lookupTicket(
      {String? validationCode, int? ticketNumber}) async {
    try {
      return await _api.lookupTicket(
          validationCode: validationCode, ticketNumber: ticketNumber);
    } on PosApiException catch (error) {
      _showTransientMessage(error.message);
    } on PosNetworkException {
      _showTransientMessage(
          'Não foi possível validar o ticket agora. Verifique a conexão e tente novamente.');
    }
    return null;
  }

  Future<TicketValidationResult?> validateTicket(
      {String? validationCode,
      int? ticketNumber,
      required String quantity,
      required String idempotencyKey,
      required String inputMethod}) async {
    try {
      return await _api.validateTicket(
          validationCode: validationCode,
          ticketNumber: ticketNumber,
          quantity: quantity,
          idempotencyKey: idempotencyKey,
          inputMethod: inputMethod);
    } on PosApiException catch (error) {
      _showTransientMessage(error.message);
    } on PosNetworkException {
      _showTransientMessage(
          'Não foi possível validar o ticket agora. Verifique a conexão e tente novamente.');
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
      if (error.code == 'stock_unavailable') rethrow;
      _showTransientMessage(
          'Não foi possível atualizar a venda agora. Tente novamente.');
    } on PosNetworkException {
      _showTransientMessage(
          'Não foi possível atualizar a venda agora. Tente novamente.');
    }
    return null;
  }

  Future<QuickSaleStockAvailability?> quickSaleStockAvailability({
    required List<Map<String, dynamic>> items,
  }) async {
    try {
      return await _api.quickSaleStockAvailability(items: items);
    } on PosApiException catch (error) {
      if (error.isDeviceAccessFailure) {
        _handleApiError(error);
      } else {
        _showTransientMessage(
            'Não foi possível verificar o estoque agora. Tente novamente.');
      }
    } on PosNetworkException {
      _showTransientMessage(
          'Não foi possível verificar o estoque agora. Tente novamente.');
    }
    return null;
  }

  Future<List<QuickSaleAuthorizer>?> quickSaleDiscountAuthorizers() async {
    try {
      return await _api.quickSaleDiscountAuthorizers();
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<List<QuickSaleAuthorizer>?> quickSaleItemDiscountAuthorizers() async {
    try {
      return await _api.quickSaleItemDiscountAuthorizers();
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<List<QuickSaleAuthorizer>?> quickSaleServiceFeeAuthorizers() async {
    try {
      return await _api.quickSaleServiceFeeAuthorizers();
    } on PosApiException catch (error) {
      _handleApiError(error);
    } on PosNetworkException catch (error) {
      _showTransientMessage(error.message);
    }
    return null;
  }

  Future<String?> validateQuickSaleDiscountAuthorization({
    required String type,
    required QuickSaleAuthorization authorization,
  }) async {
    try {
      await _api.validateQuickSaleDiscountAuthorization(
        type: type,
        authorization: authorization.toJson(),
      );
      return null;
    } on PosApiException catch (error) {
      return error.message;
    } on PosNetworkException catch (error) {
      return error.message;
    }
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

  Future<QuickSaleCustomerSearch?> quickSaleCustomers(String query) async {
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
      if (error.code == 'customer_identity_conflict' ||
          error.code == 'customer_inactive_identity_conflict') {
        if (error.details['customer'] is! Map<String, dynamic>) {
          _handleApiError(error);
          return null;
        }
        rethrow;
      }
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
    QuickSaleAuthorization? discountAuthorization,
    QuickSaleAuthorization? itemDiscountAuthorization,
    QuickSaleAuthorization? serviceFeeAuthorization,
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
    String? payload;
    late final String key;
    var createdIntent = false;
    try {
      payload = jsonEncode(<String, dynamic>{
        'items': items,
        'cash_session': cashSessionId,
        'payments': payments,
        'discount': discount,
        'service_fee_waived': serviceFeeWaived,
        'customer': customer?.id,
        if (discountAuthorization != null)
          'discount_authorization': discountAuthorization.idempotencyIdentity,
        if (itemDiscountAuthorization != null)
          'item_discount_authorization':
              itemDiscountAuthorization.idempotencyIdentity,
        if (serviceFeeAuthorization != null)
          'service_fee_authorization':
              serviceFeeAuthorization.idempotencyIdentity,
      });
      final existingKey = _uncertainSaleKeys[payload];
      createdIntent = existingKey == null;
      key = existingKey ?? createIdempotencyKey();
      _uncertainSaleKeys[payload] = key;
      await _persistUncertainSaleIntents();
    } catch (_) {
      if (createdIntent && payload != null) _uncertainSaleKeys.remove(payload);
      saleFinalizationError =
          'Não foi possível preparar a venda para envio. Tente novamente.';
      _showTransientMessage(saleFinalizationError!);
      notifyListeners();
      return null;
    }
    final fingerprint = payload;
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
        discountAuthorization: discountAuthorization?.toJson(),
        itemDiscountAuthorization: itemDiscountAuthorization?.toJson(),
        serviceFeeAuthorization: serviceFeeAuthorization?.toJson(),
      );
      bootstrapSnapshot = snapshot.withCash(result.cash);
      _uncertainSaleKeys.remove(fingerprint);
      try {
        await _persistUncertainSaleIntents();
      } catch (_) {
        // A sale accepted by the server is safe; a later retry uses its key.
      }
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
        _uncertainSaleKeys.remove(fingerprint);
        try {
          await _persistUncertainSaleIntents();
        } catch (_) {
          // The response is definitive, so local cleanup cannot affect the sale.
        }
      }
      _handleApiError(error);
      saleFinalizationError = error.message;
    } on PosNetworkException catch (error) {
      syncStatus = syncStatus.failed(error.message);
      _showTransientMessage(error.message, notify: false);
      saleFinalizationError = error.message;
    } catch (_) {
      saleFinalizationError =
          'Não foi possível preparar a venda para envio. Tente novamente.';
      _showTransientMessage(saleFinalizationError!, notify: false);
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
        final intent = Map<String, dynamic>.from(raw as Map);
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

  Future<void> _persistUncertainSaleIntents() {
    final intents = _uncertainSaleKeys.entries
        .map((entry) => <String, dynamic>{
              'fingerprint': base64UrlEncode(utf8.encode(entry.key)),
              'payload':
                  Map<String, dynamic>.from(jsonDecode(entry.key) as Map),
              'idempotency_key': entry.value,
            })
        .toList(growable: false);
    return _secrets.writePendingSaleIntents(
      jsonEncode(<String, dynamic>{'intents': intents}),
    );
  }

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
