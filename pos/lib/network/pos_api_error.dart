enum PosApiErrorKind {
  authentication,
  authorization,
  conflict,
  validation,
  rateLimit,
  unavailable,
  invalidResponse,
  request
}

class PosApiException implements Exception {
  const PosApiException({
    required this.statusCode,
    required this.code,
    required this.message,
    this.details = const {},
    this.kind = PosApiErrorKind.request,
  });

  final int statusCode;
  final String code;
  final String message;
  final Map<String, dynamic> details;
  final PosApiErrorKind kind;

  bool get isDeviceAccessFailure =>
      code == 'device_blocked' ||
      code == 'device_revoked' ||
      code == 'device_replaced' ||
      code == 'device_not_active' ||
      (statusCode == 401 && code == 'authentication_failed');
}

enum PosNetworkErrorKind { timeout, unavailable, dns, connection }

class PosNetworkException implements Exception {
  const PosNetworkException(this.message,
      {this.kind = PosNetworkErrorKind.connection});

  final String message;
  final PosNetworkErrorKind kind;
}
