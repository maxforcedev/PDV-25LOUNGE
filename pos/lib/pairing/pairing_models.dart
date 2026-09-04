class PairingChannel {
  const PairingChannel({
    required this.id,
    required this.type,
    required this.masked,
  });

  factory PairingChannel.fromJson(Map<String, dynamic> json) => PairingChannel(
        id: json['id'] as String,
        type: json['type'] as String,
        masked: json['masked'] as String,
      );

  final String id;
  final String type;
  final String masked;
}

class PairingDiscovery {
  const PairingDiscovery({
    required this.flowId,
    required this.branchName,
    required this.channels,
  });

  factory PairingDiscovery.fromJson(Map<String, dynamic> json) {
    final branch = json['branch'] as Map<String, dynamic>;
    return PairingDiscovery(
      flowId: json['pairing_flow_id'].toString(),
      branchName: branch['display_name'] as String,
      channels: (json['channels'] as List<dynamic>)
          .cast<Map<String, dynamic>>()
          .map(PairingChannel.fromJson)
          .toList(growable: false),
    );
  }

  final String flowId;
  final String branchName;
  final List<PairingChannel> channels;
}

class OtpChallenge {
  const OtpChallenge({
    required this.id,
    required this.destination,
  });

  factory OtpChallenge.fromJson(Map<String, dynamic> json) => OtpChallenge(
        id: json['challenge_id'].toString(),
        destination: json['destination'] as String,
      );

  final String id;
  final String destination;
}

class DeviceDescriptor {
  const DeviceDescriptor({
    required this.name,
    required this.type,
    required this.appVersion,
    required this.osVersion,
    required this.model,
    this.capabilities = const {},
  });

  final String name;
  final String type;
  final String appVersion;
  final String osVersion;
  final String model;
  final Map<String, dynamic> capabilities;

  Map<String, dynamic> toJson() => {
        'name': name,
        'device_type': type,
        'app_version': appVersion,
        'os_version': osVersion,
        'device_model': model,
        'capabilities': capabilities,
      };
}
