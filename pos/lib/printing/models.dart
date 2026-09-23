enum PrintDocumentType {
  tableBill('table_bill'),
  tableConference('table_conference'),
  tableFinalReceipt('table_final_receipt'),
  quickSaleReceipt('quick_sale_receipt'),
  paymentReceipt('payment_receipt'),
  ticket('ticket');

  const PrintDocumentType(this.apiValue);
  final String apiValue;

  static PrintDocumentType? fromApiValue(Object? value) {
    for (final type in values) {
      if (type.apiValue == value?.toString().toLowerCase()) return type;
    }
    return null;
  }
}

class PrintDocumentRequest {
  const PrintDocumentRequest({
    required this.type,
    required this.sourceType,
    required this.sourceId,
    required this.idempotencyKey,
  });

  final PrintDocumentType type;
  final String sourceType;
  final String sourceId;
  final String idempotencyKey;

  Map<String, dynamic> toJson() => {
        'document_type': type.apiValue,
        'source_type': sourceType,
        'source_id': sourceId,
        'idempotency_key': idempotencyKey,
      };
}

class PrintDocumentReprintRequest {
  const PrintDocumentReprintRequest({
    required this.documentId,
    required this.idempotencyKey,
    this.reason = '',
  });

  final String documentId;
  final String idempotencyKey;
  final String reason;

  Map<String, dynamic> toJson() => {
        'idempotency_key': idempotencyKey,
        'reason': reason,
      };
}

class PrintDocumentResult {
  const PrintDocumentResult({
    this.id,
    this.documentType,
    this.reprintNumber = 0,
    this.initialPrinted = false,
    this.reprintEligible = false,
    this.queued = false,
  });

  factory PrintDocumentResult.fromJson(Map<String, dynamic> json) {
    final rawDocument = json['document'] is Map
        ? json['document'] as Map
        : json['print_document'] is Map
             ? json['print_document'] as Map
             : json;
    final document = Map<String, dynamic>.from(rawDocument);
    final jobs = document['print_jobs'] is List
        ? document['print_jobs'] as List
        : json['jobs'] is List
            ? json['jobs'] as List
            : const [];
    final initialJobs =
        jobs.whereType<Map>().where((job) => job['reprint_of'] == null);
    final initialPrinted = document['initial_printed'] == true ||
        initialJobs.any((job) => job['status'] == 'printed');
    final reprintEligible = document['reprint_eligible'] == true ||
        initialJobs.any((job) =>
            job['status'] == 'printed' || job['status'] == 'uncertain');
    final reprintNumbers = jobs.whereType<Map>().map(
        (job) => (job['reprint_number'] as num?)?.toInt() ?? 0);
    return PrintDocumentResult(
      id: document['id']?.toString(),
      documentType: PrintDocumentType.fromApiValue(
          document['document_type'] ?? json['document_type']),
      reprintNumber: (document['reprint_number'] as num?)?.toInt() ??
          (json['reprint_number'] as num?)?.toInt() ??
           (reprintNumbers.isEmpty
               ? 0
               : reprintNumbers.reduce((current, next) =>
                   current > next ? current : next)),
      initialPrinted: initialPrinted,
      reprintEligible: reprintEligible,
      queued: json['queued'] == true || jobs.isNotEmpty,
    );
  }

  static PrintDocumentResult? maybeFromJson(Object? value) {
    if (value is Map) return PrintDocumentResult.fromJson(Map<String, dynamic>.from(value));
    if (value is num || value is String) {
      final id = value.toString();
      return id.isEmpty ? null : PrintDocumentResult(id: id);
    }
    return null;
  }

  final String? id;
  final PrintDocumentType? documentType;
  final int reprintNumber;
  final bool initialPrinted;
  final bool reprintEligible;
  final bool queued;
}

class PrintJob {
  const PrintJob({
    required this.id,
    required this.printerId,
    required this.payload,
    required this.idempotencyKey,
    required this.isTest,
    required this.status,
    required this.reprintNumber,
    this.documentType,
    this.documentId,
  });

  factory PrintJob.fromJson(Map<String, dynamic> json) {
    final payload = Map<String, dynamic>.from(
        json['payload_snapshot'] as Map? ?? const {});
    final documentSnapshot = json['document_snapshot'] as Map?;
    if (documentSnapshot != null && documentSnapshot.isNotEmpty) {
      payload['snapshot'] = Map<String, dynamic>.from(documentSnapshot);
    }
    final rawDocument = json['print_document'] is Map
        ? json['print_document'] as Map
        : json['document'] is Map
            ? json['document'] as Map
        : payload['print_document'] is Map
            ? payload['print_document'] as Map
            : payload['document'] is Map
                ? payload['document'] as Map
                : const {};
    final document = Map<String, dynamic>.from(rawDocument);
    return PrintJob(
      id: json['id'] as int,
      printerId: json['printer_device'] as int,
      payload: payload,
      idempotencyKey: json['idempotency_key'].toString(),
      isTest: json['is_test'] == true,
      status: json['status'] as String? ?? 'pending',
      reprintNumber: (json['reprint_number'] as num?)?.toInt() ?? 0,
      documentType: PrintDocumentType.fromApiValue(
          json['document_type'] ??
              document['document_type'] ??
              payload['document_type']),
      documentId: (json['print_document'] is num
              ? json['print_document']
              : json['print_document'] is String
                  ? json['print_document']
                  : document['id'] ??
                      json['print_document_id'] ??
                      payload['print_document_id'])
          ?.toString(),
    );
  }

  final int id;
  final int printerId;
  final Map<String, dynamic> payload;
  final String idempotencyKey;
  final bool isTest;
  final String status;
  final int reprintNumber;
  final PrintDocumentType? documentType;
  final String? documentId;
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
