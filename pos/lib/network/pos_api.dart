import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../auth/auth_models.dart';
import '../attendance/attendance_models.dart';
import '../bootstrap/bootstrap_models.dart';
import '../cash/cash_models.dart';
import '../pairing/pairing_models.dart';
import '../sales/sale_models.dart';
import '../storage/secret_store.dart';
import '../tickets/ticket_models.dart';
import 'pos_api_error.dart';

final _posDebugClock = Stopwatch()..start();

void logPosDebugTiming(String event) {
  if (kDebugMode) {
    debugPrint('[POS PERF] ${_posDebugClock.elapsedMilliseconds}ms $event');
  }
}

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
  Future<void> requestOperatorPinReset(String operatorId);
  Future<OperatorSession> login(String operatorId, String pin);
  Future<void> logout();
  Future<BootstrapSnapshot> bootstrap();
  Future<CashOverview> cashOverview();
  Future<CashOverview> openCashSession(
      {required String openingAmount, int? registerId});
  Future<CashSessionSummary> cashSessionSummary(int sessionId);
  Future<CashOverview> recordCashEntry(
      {required int sessionId,
      required String amount,
      required String reason,
      required String idempotencyKey});
  Future<List<CashBeneficiary>> cashWithdrawalBeneficiaries(String category);
  Future<CashOverview> recordCashWithdrawal(
      {required int sessionId,
      required String amount,
      required String reason,
      required String category,
      String? beneficiaryType,
      int? beneficiaryId,
      required String idempotencyKey});
  Future<CashOverview> closeCashSession(
      {required int sessionId, required String closingAmount});
  Future<List<QuickSaleProduct>> quickSaleCatalog({
    String? search,
    int? categoryId,
    bool favorites = false,
  });
  Future<List<QuickSaleCategory>> quickSaleCategories();
  Future<QuickSaleProduct> quickSaleBarcode(String barcode);
  Future<QuickSaleCustomerSearch> quickSaleCustomers(String query);
  Future<QuickSaleCustomer> createQuickSaleCustomer({
    required String name,
    String phone,
    String document,
    String email,
  });
  Future<QuickSaleCustomer> activateQuickSaleCustomer(int customerId);
  Future<List<AttendanceTable>> attendanceTables();
  Future<void> groupAttendanceTables({
    required List<int> tableIds,
    required String idempotencyKey,
  });
  Future<void> separateAttendanceTable({
    required int tableId,
    required String idempotencyKey,
  });
  Future<AttendanceCommand> openAttendanceTable({
    required int tableId,
    required String idempotencyKey,
    int? peopleCount,
    String identifier,
    String notes,
  });
  Future<List<AttendanceCommand>> attendanceCommands({String? query});
  Future<List<QuickSaleProduct>> attendanceCatalog({String? search});
  Future<QuickSaleCheckoutOptions> attendanceCheckoutOptions();
  Future<AttendanceCommandDetail> attendanceCommandDetail(int commandId);
  Future<AttendanceCommand> setAttendanceBillRequested({
    required int commandId,
    required bool requested,
    required String idempotencyKey,
  });
  Future<AttendanceCommand> openAttendanceCommand({
    required String idempotencyKey,
    String identifier,
    int? tableId,
    int? customerId,
    int? peopleCount,
    String notes,
  });
  Future<List<AttendanceOrderItem>> addAttendanceItems({
    required int commandId,
    required List<Map<String, dynamic>> items,
    required String idempotencyKey,
  });
  Future<AttendanceOrderItem> confirmAttendanceItem({
    required int itemId,
    required String idempotencyKey,
  });
  Future<AttendanceOrderItem> cancelAttendanceItem({
    required int itemId,
    required String idempotencyKey,
    String reason,
  });
  Future<AttendanceLedger> attendanceLedger(int commandId);
  Future<AttendancePayment> recordAttendancePayment({
    required int commandId,
    required int paymentMethodId,
    required String amount,
    required String idempotencyKey,
    String? receivedAmount,
    int? cashSessionId,
  });
  Future<AttendancePayment> reverseAttendancePayment({
    required int paymentId,
    required String idempotencyKey,
    String reason,
  });
  Future<AttendanceCommand> finalizeAttendanceCommand({
    required int commandId,
    required int cashSessionId,
    required String idempotencyKey,
  });
  Future<AttendanceCommand> transferAttendanceCommand({
    required int commandId,
    required int? tableId,
    required String idempotencyKey,
  });
  Future<AttendanceCommand> transferAttendanceItems({
    required int commandId,
    required int destinationCommandId,
    required List<Map<String, dynamic>> items,
    required String idempotencyKey,
  });
  Future<QuickSalePreview> quickSalePreview({
    required List<Map<String, dynamic>> items,
    required Map<String, dynamic> discount,
    required bool serviceFeeWaived,
  });
  Future<QuickSaleStockAvailability> quickSaleStockAvailability({
    required List<Map<String, dynamic>> items,
  });
  Future<List<QuickSaleAuthorizer>> quickSaleDiscountAuthorizers();
  Future<List<QuickSaleAuthorizer>> quickSaleItemDiscountAuthorizers();
  Future<List<QuickSaleAuthorizer>> quickSaleServiceFeeAuthorizers();
  Future<void> validateQuickSaleDiscountAuthorization({
    required String type,
    required Map<String, dynamic> authorization,
  });
  Future<QuickSaleCheckoutOptions> quickSaleCheckoutOptions();
  Future<QuickSaleResult> finalizeQuickSale({
    required String idempotencyKey,
    required List<Map<String, dynamic>> items,
    required int cashSessionId,
    required List<Map<String, dynamic>> payments,
    required Map<String, dynamic> discount,
    required bool serviceFeeWaived,
    int? customerId,
    Map<String, dynamic>? discountAuthorization,
    Map<String, dynamic>? itemDiscountAuthorization,
    Map<String, dynamic>? serviceFeeAuthorization,
  });
  Future<TicketValidationResult> lookupTicket(
      {String? validationCode, int? ticketNumber});
  Future<TicketValidationResult> validateTicket(
      {String? validationCode,
      int? ticketNumber,
      required String quantity,
      required String idempotencyKey,
      required String inputMethod});
}

abstract interface class PosCredentialCache {
  Future<void> warmCredentials();
  bool get hasDeviceCredential;
  void cacheDeviceCredential(String? credential);
  void cacheOperatorSession(String? session);
}

class HttpPosApi implements PosApi, PosCredentialCache {
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
  String? _deviceCredential;
  String? _operatorSession;
  bool _credentialsWarmed = false;

  Uri _uri(String path) => _baseUri.resolve('api/v1/pos/$path');

  CashOverview _cashState(Map<String, dynamic> payload) {
    final state = payload['cash_state'];
    if (state is! Map<String, dynamic>) {
      throw const FormatException(
          'A resposta de caixa não contém o estado atualizado.');
    }
    return CashOverview.fromJson(state);
  }

  @override
  Future<void> warmCredentials() async {
    if (_credentialsWarmed) return;
    final values = await Future.wait<String?>([
      _secrets.readDeviceCredential(),
      _secrets.readOperatorSession(),
    ]);
    _deviceCredential = values[0];
    _operatorSession = values[1];
    _credentialsWarmed = true;
  }

  @override
  bool get hasDeviceCredential => _deviceCredential != null;

  @override
  void cacheDeviceCredential(String? credential) {
    _deviceCredential = credential;
    _credentialsWarmed = true;
  }

  @override
  void cacheOperatorSession(String? session) {
    _operatorSession = session;
    _credentialsWarmed = true;
  }

  Map<String, String> _headers({bool json = true}) {
    return {
      if (json) 'Content-Type': 'application/json',
      'Accept': 'application/json',
      if (_deviceCredential != null)
        'X-POS-Device-Credential': _deviceCredential!,
      if (_operatorSession != null) 'X-POS-Operator-Session': _operatorSession!,
    };
  }

  Future<dynamic> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    http.Response response;
    logPosDebugTiming('$method request_started');
    try {
      final headers = _headers();
      logPosDebugTiming('$method headers_ready');
      final uri = _uri(path);
      logPosDebugTiming('$method http_sent');
      response = switch (method) {
        'GET' => await _client
            .get(uri, headers: headers)
            .timeout(const Duration(seconds: 15)),
        'POST' => await _client
            .post(uri, headers: headers, body: jsonEncode(body ?? const {}))
            .timeout(const Duration(seconds: 15)),
        _ => throw ArgumentError.value(method, 'method'),
      };
      logPosDebugTiming('$method http_received');
    } on http.ClientException catch (error) {
      throw PosNetworkException(error.message);
    } on TimeoutException {
      throw const PosNetworkException(
          'A conexão demorou demais. Verifique a internet e tente novamente.');
    }
    final decoded =
        response.body.isEmpty ? <String, dynamic>{} : jsonDecode(response.body);
    final payload =
        decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    if (response.statusCode >= 200 && response.statusCode < 300) return decoded;
    final code = payload['code'] as String? ??
        (response.statusCode == 401
            ? 'authentication_failed'
            : 'request_failed');
    throw PosApiException(
      statusCode: response.statusCode,
      code: code,
      message: payload['message'] as String? ??
          payload['detail'] as String? ??
          'Falha ao comunicar com o CORE.',
      details: payload['details'] as Map<String, dynamic>? ?? const {},
    );
  }

  @override
  Future<PairingDiscovery> identifyBranch(String identifier) async =>
      PairingDiscovery.fromJson(await _request('POST', 'pairing/identify/',
          body: {'identifier': identifier}));

  @override
  Future<OtpChallenge> requestOtp(String flowId, String channelId) async =>
      OtpChallenge.fromJson(
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
  Future<HeartbeatResult> heartbeat(DeviceDescriptor device) async =>
      HeartbeatResult.fromJson(
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
  Future<void> requestOperatorPinReset(String operatorId) async {
    await _request('POST', 'operators/$operatorId/pin-reset/');
  }

  @override
  Future<OperatorSession> login(String operatorId, String pin) async =>
      OperatorSession.fromJson(
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

  @override
  Future<CashOverview> cashOverview() async =>
      CashOverview.fromJson(await _request('GET', 'cash/overview/'));

  @override
  Future<CashOverview> openCashSession(
          {required String openingAmount, int? registerId}) async =>
      _cashState(await _request('POST', 'cash/sessions/open/', body: {
        'opening_amount': openingAmount,
        if (registerId != null) 'register': registerId,
      }));

  @override
  Future<CashSessionSummary> cashSessionSummary(int sessionId) async =>
      CashSessionSummary.fromJson(
          await _request('GET', 'cash/sessions/$sessionId/summary/'));

  @override
  Future<CashOverview> recordCashEntry(
      {required int sessionId,
      required String amount,
      required String reason,
      required String idempotencyKey}) async {
    return _cashState(
        await _request('POST', 'cash/sessions/$sessionId/entry/', body: {
      'amount': amount,
      'reason': reason,
      'idempotency_key': idempotencyKey,
    }));
  }

  @override
  Future<List<CashBeneficiary>> cashWithdrawalBeneficiaries(
      String category) async {
    final payload =
        await _request('GET', 'cash/beneficiaries/?category=$category');
    return (payload['beneficiaries'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(CashBeneficiary.fromJson)
        .toList(growable: false);
  }

  @override
  Future<CashOverview> recordCashWithdrawal(
      {required int sessionId,
      required String amount,
      required String reason,
      required String category,
      String? beneficiaryType,
      int? beneficiaryId,
      required String idempotencyKey}) async {
    return _cashState(
        await _request('POST', 'cash/sessions/$sessionId/withdrawal/', body: {
      'amount': amount,
      'reason': reason,
      'category': category,
      if (beneficiaryType != null) 'beneficiary_type': beneficiaryType,
      if (beneficiaryId != null) 'beneficiary_id': beneficiaryId,
      'idempotency_key': idempotencyKey,
    }));
  }

  @override
  Future<CashOverview> closeCashSession(
      {required int sessionId, required String closingAmount}) async {
    return _cashState(
        await _request('POST', 'cash/sessions/$sessionId/close/', body: {
      'closing_amount_informed': closingAmount,
    }));
  }

  @override
  Future<List<QuickSaleProduct>> quickSaleCatalog(
      {String? search, int? categoryId, bool favorites = false}) async {
    final query = <String, String>{
      if (search != null && search.trim().isNotEmpty) 'search': search.trim(),
      if (categoryId != null) 'category': '$categoryId',
      if (favorites) 'favorites': 'true',
    };
    final suffix = query.isEmpty ? '' : '?${Uri(queryParameters: query).query}';
    final payload = await _request('GET', 'catalog/$suffix');
    return (payload['products'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(QuickSaleProduct.fromJson)
        .toList(growable: false);
  }

  @override
  Future<List<QuickSaleCategory>> quickSaleCategories() async {
    final payload = await _request('GET', 'catalog/categories/');
    return (payload['categories'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(QuickSaleCategory.fromJson)
        .toList(growable: false);
  }

  @override
  Future<QuickSaleProduct> quickSaleBarcode(String barcode) async =>
      QuickSaleProduct.fromJson(await _request(
          'GET', 'products/barcode/${Uri.encodeComponent(barcode)}/'));

  @override
  Future<QuickSaleCustomerSearch> quickSaleCustomers(String query) async {
    final suffix = query.trim().isEmpty
        ? ''
        : '?${Uri(queryParameters: {'q': query.trim()}).query}';
    final payload = await _request('GET', 'customers/$suffix');
    return QuickSaleCustomerSearch.fromJson(payload);
  }

  @override
  Future<QuickSaleCustomer> createQuickSaleCustomer({
    required String name,
    String phone = '',
    String document = '',
    String email = '',
  }) async =>
      QuickSaleCustomer.fromJson(await _request('POST', 'customers/', body: {
        'name': name,
        'phone': phone,
        'document': document,
        'email': email,
      }));

  @override
  Future<QuickSaleCustomer> activateQuickSaleCustomer(int customerId) async =>
      QuickSaleCustomer.fromJson(await _request(
        'POST',
        'customers/$customerId/activate/',
        body: const {},
      ));

  @override
  Future<List<AttendanceTable>> attendanceTables() async {
    final payload = await _request('GET', 'tables/');
    return (payload['tables'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(AttendanceTable.fromJson)
        .toList(growable: false);
  }

  @override
  Future<void> groupAttendanceTables({
    required List<int> tableIds,
    required String idempotencyKey,
  }) async {
    await _request('POST', 'tables/groups/', body: {
      'tables': tableIds,
      'idempotency_key': idempotencyKey,
    });
  }

  @override
  Future<void> separateAttendanceTable({
    required int tableId,
    required String idempotencyKey,
  }) async {
    await _request('POST', 'tables/$tableId/separate/',
        body: {'idempotency_key': idempotencyKey});
  }

  @override
  Future<AttendanceCommand> openAttendanceTable({
    required int tableId,
    required String idempotencyKey,
    int? peopleCount,
    String identifier = '',
    String notes = '',
  }) async =>
      AttendanceCommand.fromJson(await _request(
        'POST',
        'tables/$tableId/open/',
        body: {
          'idempotency_key': idempotencyKey,
          if (peopleCount != null) 'people_count': peopleCount,
          'identifier': identifier,
          'notes': notes,
        },
      ));

  @override
  Future<List<AttendanceCommand>> attendanceCommands({String? query}) async {
    final suffix = query == null || query.trim().isEmpty
        ? ''
        : '?${Uri(queryParameters: {'q': query.trim()}).query}';
    final payload = await _request('GET', 'commands/$suffix');
    return (payload['commands'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(AttendanceCommand.fromJson)
        .toList(growable: false);
  }

  @override
  Future<List<QuickSaleProduct>> attendanceCatalog({String? search}) async {
    final suffix = search == null || search.trim().isEmpty
        ? ''
        : '?${Uri(queryParameters: {'q': search.trim()}).query}';
    final payload = await _request('GET', 'commands/catalog/$suffix');
    return (payload['products'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(QuickSaleProduct.fromJson)
        .toList(growable: false);
  }

  @override
  Future<QuickSaleCheckoutOptions> attendanceCheckoutOptions() async =>
      QuickSaleCheckoutOptions.fromJson(
          await _request('GET', 'commands/checkout-options/'));

  @override
  Future<AttendanceCommandDetail> attendanceCommandDetail(
          int commandId) async =>
      AttendanceCommandDetail.fromJson(
          await _request('GET', 'commands/$commandId/'));

  @override
  Future<AttendanceCommand> setAttendanceBillRequested({
    required int commandId,
    required bool requested,
    required String idempotencyKey,
  }) async =>
      AttendanceCommand.fromJson(await _request(
        'POST',
        'commands/$commandId/${requested ? 'request-bill' : 'clear-bill'}/',
        body: {'idempotency_key': idempotencyKey},
      ));

  @override
  Future<AttendanceCommand> openAttendanceCommand({
    required String idempotencyKey,
    String identifier = '',
    int? tableId,
    int? customerId,
    int? peopleCount,
    String notes = '',
  }) async =>
      AttendanceCommand.fromJson(await _request('POST', 'commands/', body: {
        'idempotency_key': idempotencyKey,
        'identifier': identifier,
        if (tableId != null) 'table': tableId,
        if (customerId != null) 'customer': customerId,
        if (peopleCount != null) 'people_count': peopleCount,
        'notes': notes,
      }));

  @override
  Future<List<AttendanceOrderItem>> addAttendanceItems({
    required int commandId,
    required List<Map<String, dynamic>> items,
    required String idempotencyKey,
  }) async {
    final payload = await _request('POST', 'commands/$commandId/items/',
        body: {'items': items, 'idempotency_key': idempotencyKey});
    return (payload as List<dynamic>)
        .cast<Map<String, dynamic>>()
        .map(AttendanceOrderItem.fromJson)
        .toList(growable: false);
  }

  @override
  Future<AttendanceOrderItem> confirmAttendanceItem(
          {required int itemId, required String idempotencyKey}) async =>
      AttendanceOrderItem.fromJson(await _request(
          'POST', 'command-items/$itemId/confirm/',
          body: {'idempotency_key': idempotencyKey}));

  @override
  Future<AttendanceOrderItem> cancelAttendanceItem(
          {required int itemId,
          required String idempotencyKey,
          String reason = ''}) async =>
      AttendanceOrderItem.fromJson(await _request(
          'POST', 'command-items/$itemId/cancel/',
          body: {'idempotency_key': idempotencyKey, 'reason': reason}));

  @override
  Future<AttendanceLedger> attendanceLedger(int commandId) async =>
      AttendanceLedger.fromJson(
          await _request('GET', 'commands/$commandId/payments/'));

  @override
  Future<AttendancePayment> recordAttendancePayment(
          {required int commandId,
          required int paymentMethodId,
          required String amount,
          required String idempotencyKey,
          String? receivedAmount,
          int? cashSessionId}) async =>
      AttendancePayment.fromJson(
          await _request('POST', 'commands/$commandId/payments/', body: {
        'payment_method': paymentMethodId,
        'amount': amount,
        'idempotency_key': idempotencyKey,
        if (receivedAmount != null) 'received_amount': receivedAmount,
        if (cashSessionId != null) 'cash_session': cashSessionId,
      }));

  @override
  Future<AttendancePayment> reverseAttendancePayment(
          {required int paymentId,
          required String idempotencyKey,
          String reason = ''}) async =>
      AttendancePayment.fromJson(await _request(
          'POST', 'command-payments/$paymentId/reverse/',
          body: {'idempotency_key': idempotencyKey, 'reason': reason}));

  @override
  Future<AttendanceCommand> finalizeAttendanceCommand(
          {required int commandId,
          required int cashSessionId,
          required String idempotencyKey}) async =>
      AttendanceCommand.fromJson(
          await _request('POST', 'commands/$commandId/finalize/', body: {
        'cash_session': cashSessionId,
        'payments': const [],
        'discount': '0.00',
        'service_fee_waived': false,
        'idempotency_key': idempotencyKey
      }));

  @override
  Future<AttendanceCommand> transferAttendanceCommand(
          {required int commandId,
          required int? tableId,
          required String idempotencyKey}) async =>
      AttendanceCommand.fromJson(await _request(
          'POST', 'commands/$commandId/transfer/',
          body: {'table': tableId, 'idempotency_key': idempotencyKey}));

  @override
  Future<AttendanceCommand> transferAttendanceItems(
      {required int commandId,
      required int destinationCommandId,
      required List<Map<String, dynamic>> items,
      required String idempotencyKey}) async {
    final payload =
        await _request('POST', 'commands/$commandId/transfer-items/', body: {
      'command': destinationCommandId,
      'items': items,
      'idempotency_key': idempotencyKey
    });
    return AttendanceCommand.fromJson(
        payload['command'] as Map<String, dynamic>);
  }

  @override
  Future<QuickSalePreview> quickSalePreview({
    required List<Map<String, dynamic>> items,
    required Map<String, dynamic> discount,
    required bool serviceFeeWaived,
  }) async =>
      QuickSalePreview.fromJson(await _request('POST', 'sales/preview/', body: {
        'items': items,
        'discount': discount,
        'service_fee_waived': serviceFeeWaived,
      }));

  @override
  Future<QuickSaleStockAvailability> quickSaleStockAvailability({
    required List<Map<String, dynamic>> items,
  }) async =>
      QuickSaleStockAvailability.fromJson(await _request(
          'POST', 'sales/availability/',
          body: {'items': items}));

  @override
  Future<List<QuickSaleAuthorizer>> quickSaleDiscountAuthorizers() async {
    final payload = await _request('GET', 'sales/discount-authorizers/');
    return (payload['authorizers'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(QuickSaleAuthorizer.fromJson)
        .toList(growable: false);
  }

  @override
  Future<List<QuickSaleAuthorizer>> quickSaleItemDiscountAuthorizers() async {
    final payload = await _request('GET', 'sales/item-discount-authorizers/');
    return (payload['authorizers'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(QuickSaleAuthorizer.fromJson)
        .toList(growable: false);
  }

  @override
  Future<List<QuickSaleAuthorizer>> quickSaleServiceFeeAuthorizers() async {
    final payload = await _request('GET', 'sales/service-fee-authorizers/');
    return (payload['authorizers'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(QuickSaleAuthorizer.fromJson)
        .toList(growable: false);
  }

  @override
  Future<void> validateQuickSaleDiscountAuthorization({
    required String type,
    required Map<String, dynamic> authorization,
  }) async {
    await _request('POST', 'sales/discount-authorizations/validate/', body: {
      'type': type,
      ...authorization,
    });
  }

  @override
  Future<QuickSaleCheckoutOptions> quickSaleCheckoutOptions() async =>
      QuickSaleCheckoutOptions.fromJson(
          await _request('GET', 'sales/checkout-options/'));

  @override
  Future<QuickSaleResult> finalizeQuickSale({
    required String idempotencyKey,
    required List<Map<String, dynamic>> items,
    required int cashSessionId,
    required List<Map<String, dynamic>> payments,
    required Map<String, dynamic> discount,
    required bool serviceFeeWaived,
    int? customerId,
    Map<String, dynamic>? discountAuthorization,
    Map<String, dynamic>? itemDiscountAuthorization,
    Map<String, dynamic>? serviceFeeAuthorization,
  }) async =>
      QuickSaleResult.fromJson(await _request('POST', 'sales/', body: {
        'idempotency_key': idempotencyKey,
        'items': items,
        'cash_session': cashSessionId,
        'payments': payments,
        'discount': discount,
        'service_fee_waived': serviceFeeWaived,
        if (customerId != null) 'customer': customerId,
        if (discountAuthorization != null)
          'discount_authorization': discountAuthorization,
        if (itemDiscountAuthorization != null)
          'item_discount_authorization': itemDiscountAuthorization,
        if (serviceFeeAuthorization != null)
          'service_fee_authorization': serviceFeeAuthorization,
      }));

  @override
  Future<TicketValidationResult> lookupTicket(
          {String? validationCode, int? ticketNumber}) async =>
      TicketValidationResult.fromJson(
          await _request('POST', 'tickets/lookup/', body: {
        if (validationCode != null) 'validation_code': validationCode,
        if (ticketNumber != null) 'ticket_number': ticketNumber,
      }));

  @override
  Future<TicketValidationResult> validateTicket(
          {String? validationCode,
          int? ticketNumber,
          required String quantity,
          required String idempotencyKey,
          required String inputMethod}) async =>
      TicketValidationResult.fromJson(
          await _request('POST', 'tickets/validate/', body: {
        if (validationCode != null) 'validation_code': validationCode,
        if (ticketNumber != null) 'ticket_number': ticketNumber,
        'quantity': quantity,
        'idempotency_key': idempotencyKey,
        'input_method': inputMethod,
      }));
}
