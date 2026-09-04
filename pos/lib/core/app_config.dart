import 'dart:io';

import '../pairing/pairing_models.dart';

class AppConfig {
  const AppConfig({required this.apiBaseUrl, required this.device});

  factory AppConfig.fromEnvironment() {
    const baseUrl = String.fromEnvironment(
      'POS_API_BASE_URL',
      defaultValue: 'http://10.0.2.2:18000',
    );
    const appVersion = String.fromEnvironment('POS_APP_VERSION', defaultValue: '1.0.0');
    const deviceName = String.fromEnvironment('POS_DEVICE_NAME', defaultValue: 'Android POS');
    const deviceType = String.fromEnvironment('POS_DEVICE_TYPE', defaultValue: 'POS');
    return AppConfig(
      apiBaseUrl: baseUrl,
      device: DeviceDescriptor(
        name: deviceName,
        type: deviceType,
        appVersion: appVersion,
        osVersion: Platform.operatingSystemVersion,
        model: Platform.localHostname,
      ),
    );
  }

  final String apiBaseUrl;
  final DeviceDescriptor device;
}
