import '../cash/cash_models.dart';

class ReleaseInfo {
  const ReleaseInfo({
    required this.currentVersion,
    required this.latestVersion,
    required this.minimumSupportedVersion,
    required this.updateAvailable,
    required this.updateRequired,
  });

  factory ReleaseInfo.fromJson(Map<String, dynamic> json) => ReleaseInfo(
        currentVersion: json['current_version'] as String? ?? '',
        latestVersion: json['latest_version'] as String? ?? '',
        minimumSupportedVersion: json['minimum_supported_version'] as String? ?? '',
        updateAvailable: json['update_available'] as bool? ?? false,
        updateRequired: json['update_required'] as bool? ?? false,
      );

  final String currentVersion;
  final String latestVersion;
  final String minimumSupportedVersion;
  final bool updateAvailable;
  final bool updateRequired;
}

class HeartbeatResult {
  const HeartbeatResult({required this.release, this.deviceStatus = ''});

  factory HeartbeatResult.fromJson(Map<String, dynamic> json) => HeartbeatResult(
        release: ReleaseInfo.fromJson(json['release'] as Map<String, dynamic>),
        deviceStatus: (json['device'] as Map<String, dynamic>?)?['status'] as String? ?? '',
      );

  final ReleaseInfo release;
  final String deviceStatus;
}

class HomeModule {
  const HomeModule({required this.key, required this.enabled, this.reason});

  final String key;
  final bool enabled;
  final String? reason;
}

class BootstrapSnapshot {
  const BootstrapSnapshot({
    required this.companyName,
    required this.branchName,
    required this.deviceName,
    this.deviceStatus = '',
    required this.operatorName,
    required this.release,
    required this.modules,
    this.permissions = const {},
    this.cash = const CashOverview(mode: 'FLEXIBLE', enabled: false),
  });

  factory BootstrapSnapshot.fromJson(Map<String, dynamic> json) {
    final company = json['company'] as Map<String, dynamic>;
    final branch = json['branch'] as Map<String, dynamic>;
    final device = json['device'] as Map<String, dynamic>;
    final operator = json['operator'] as Map<String, dynamic>;
    final rawModules = json['modules'] as Map<String, dynamic>;
    final modules = rawModules.entries
        .map((entry) {
          final value = entry.value as Map<String, dynamic>;
          return HomeModule(
            key: entry.key,
            enabled: value['enabled'] as bool? ?? false,
            reason: value['reason'] as String?,
          );
        })
        .toList(growable: false);
    return BootstrapSnapshot(
      companyName: company['trade_name'] as String,
      branchName: branch['name'] as String,
      deviceName: device['name'] as String,
      deviceStatus: device['status'] as String? ?? '',
      operatorName: operator['display_name'] as String,
      release: ReleaseInfo.fromJson(json['release'] as Map<String, dynamic>),
      modules: modules,
      permissions: (json['permissions'] as List<dynamic>? ?? const []).cast<String>().toSet(),
      cash: CashOverview.fromJson(json['cash'] as Map<String, dynamic>? ?? const {}),
    );
  }

  final String companyName;
  final String branchName;
  final String deviceName;
  final String deviceStatus;
  final String operatorName;
  final ReleaseInfo release;
  final List<HomeModule> modules;
  final Set<String> permissions;
  final CashOverview cash;

  Iterable<HomeModule> get enabledModules => modules.where((module) => module.enabled);

  BootstrapSnapshot withCash(CashOverview nextCash) => BootstrapSnapshot(
        companyName: companyName,
        branchName: branchName,
        deviceName: deviceName,
        deviceStatus: deviceStatus,
        operatorName: operatorName,
        release: release,
        modules: modules,
        permissions: permissions,
        cash: nextCash,
      );
}
