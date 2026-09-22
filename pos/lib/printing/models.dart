class PrintJob {
  const PrintJob({
    required this.id,
    required this.printerId,
    required this.payload,
    required this.idempotencyKey,
    required this.isTest,
    required this.status,
    required this.reprintNumber,
  });

  factory PrintJob.fromJson(Map<String, dynamic> json) => PrintJob(
        id: json['id'] as int,
        printerId: json['printer_device'] as int,
        payload: Map<String, dynamic>.from(
            json['payload_snapshot'] as Map? ?? const {}),
        idempotencyKey: json['idempotency_key'].toString(),
        isTest: json['is_test'] == true,
        status: json['status'] as String? ?? 'pending',
        reprintNumber: json['reprint_number'] as int? ?? 0,
      );

  final int id;
  final int printerId;
  final Map<String, dynamic> payload;
  final String idempotencyKey;
  final bool isTest;
  final String status;
  final int reprintNumber;
}

class NetworkPrinter {
  const NetworkPrinter({
    required this.id,
    required this.name,
    required this.host,
    required this.port,
    required this.timeoutSeconds,
    required this.paperWidth,
    required this.cut,
  });

  factory NetworkPrinter.fromJson(Map<String, dynamic> json) {
    final config =
        Map<String, dynamic>.from(json['configuration'] as Map? ?? const {});
    return NetworkPrinter(
      id: json['id'] as int,
      name: json['name'] as String? ?? 'Impressora',
      host: config['host'] as String? ?? '',
      port: config['port'] as int? ?? 9100,
      timeoutSeconds: (config['timeout'] as num?)?.toInt() ?? 5,
      paperWidth: config['paper_width'] == 58 ? 58 : 80,
      cut: config['cut'] != false,
    );
  }

  final int id;
  final String name;
  final String host;
  final int port;
  final int timeoutSeconds;
  final int paperWidth;
  final bool cut;
}
