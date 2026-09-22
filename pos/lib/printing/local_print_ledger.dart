import 'dart:convert';

import '../storage/secret_store.dart';

class PrintLedgerEntry {
  const PrintLedgerEntry({
    required this.jobId,
    required this.printerId,
    required this.idempotencyKey,
    required this.state,
    this.printerObserved = false,
    this.attemptedAt,
    this.sentAt,
    this.acknowledgedAt,
  });

  factory PrintLedgerEntry.fromJson(Map<String, dynamic> json) =>
      PrintLedgerEntry(
        jobId: json['job_id'] as int,
        printerId: json['printer_id'] as int,
        idempotencyKey: json['idempotency_key'] as String? ?? '',
        state: json['state'] as String? ?? 'attempted',
        printerObserved: json['printer_observed'] == true,
        attemptedAt: json['attempted_at'] as String?,
        sentAt: json['sent_at'] as String?,
        acknowledgedAt: json['acknowledged_at'] as String?,
      );

  final int jobId;
  final int printerId;
  final String idempotencyKey;
  final String state;
  final bool printerObserved;
  final String? attemptedAt;
  final String? sentAt;
  final String? acknowledgedAt;

  Map<String, dynamic> toJson() => {
        'job_id': jobId,
        'printer_id': printerId,
        'idempotency_key': idempotencyKey,
        'state': state,
        'printer_observed': printerObserved,
        'attempted_at': attemptedAt,
        'sent_at': sentAt,
        'acknowledged_at': acknowledgedAt,
      };
}

class LocalPrintLedger {
  LocalPrintLedger(this._store);

  final SecretStore _store;

  Future<List<PrintLedgerEntry>> entries() async {
    final encoded = await _store.readPrintLedgerState();
    if (encoded == null || encoded.isEmpty) return const [];
    try {
      return (jsonDecode(encoded) as List<dynamic>)
          .cast<Map<String, dynamic>>()
          .map(PrintLedgerEntry.fromJson)
          .toList();
    } catch (_) {
      await _store.writePrintLedgerState('');
      return const [];
    }
  }

  Future<void> mark(PrintLedgerEntry entry) async {
    final values = await entries();
    PrintLedgerEntry? previous;
    for (final value in values) {
      if (value.jobId == entry.jobId) previous = value;
    }
    final now = DateTime.now().toUtc().toIso8601String();
    final normalized = PrintLedgerEntry(
      jobId: entry.jobId,
      printerId: entry.printerId,
      idempotencyKey: entry.idempotencyKey,
      state: entry.state,
      printerObserved: entry.printerObserved || previous?.printerObserved == true,
      attemptedAt: entry.attemptedAt ?? previous?.attemptedAt ?? now,
      sentAt: entry.sentAt ??
          previous?.sentAt ??
          (entry.state == 'sent' ? now : null),
      acknowledgedAt: entry.acknowledgedAt ?? previous?.acknowledgedAt,
    );
    final updated = [
      for (final value in values)
        if (value.jobId != entry.jobId) value,
      normalized
    ];
    await _store.writePrintLedgerState(
        jsonEncode(updated.map((value) => value.toJson()).toList()));
  }

  Future<void> removeAll(Iterable<int> jobIds) async {
    final ids = jobIds.toSet();
    final values = await entries();
    await _store.writePrintLedgerState(jsonEncode(values
        .where((value) => !ids.contains(value.jobId))
        .map((value) => value.toJson())
        .toList()));
  }
}
