class PosApiException implements Exception {
  const PosApiException({
    required this.statusCode,
    required this.code,
    required this.message,
    this.details = const {},
  });

  final int statusCode;
  final String code;
  final String message;
  final Map<String, dynamic> details;

  bool get isDeviceAccessFailure =>
      code == 'device_blocked' ||
      code == 'device_revoked' ||
      code == 'device_replaced' ||
      code == 'device_not_active' ||
      (statusCode == 401 && code == 'authentication_failed');
}

class PosNetworkException implements Exception {
  const PosNetworkException(this.message);

  final String message;
}
