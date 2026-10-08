import 'dart:io';

import 'package:flutter/foundation.dart';

import '../pairing/pairing_models.dart';

class AppConfig {
  const AppConfig({required this.apiBaseUrl, required this.device});

  factory AppConfig.fromEnvironment() {
    const baseUrl = String.fromEnvironment(
      'POS_API_BASE_URL',
      defaultValue: '',
    );
    final apiUri = Uri.tryParse(baseUrl);
    if (apiUri == null || !apiUri.hasScheme || !apiUri.hasAuthority) {
      throw ArgumentError.value(
        baseUrl,
        'POS_API_BASE_URL',
        'must be an absolute API URL configured at build time.',
      );
    }
    if (!kDebugMode && apiUri.scheme != 'https') {
      throw ArgumentError.value(
        baseUrl,
        'POS_API_BASE_URL',
        'must use HTTPS outside debug builds.',
      );
    }
    const appVersion =
        String.fromEnvironment('POS_APP_VERSION', defaultValue: '1.0.0');
    const deviceName =
        String.fromEnvironment('POS_DEVICE_NAME', defaultValue: 'Android POS');
    const deviceType =
        String.fromEnvironment('POS_DEVICE_TYPE', defaultValue: 'POS');
    return AppConfig(
      apiBaseUrl: apiUri.toString().replaceFirst(RegExp(r'/$'), ''),
      device: DeviceDescriptor(
        name: deviceName,
        type: deviceType,
        appVersion: appVersion,
        osVersion: Platform.operatingSystemVersion,
        model: Platform.localHostname,
        capabilities: const {'network_printing': true},
      ),
    );
  }

  final String apiBaseUrl;
  final DeviceDescriptor device;
}
