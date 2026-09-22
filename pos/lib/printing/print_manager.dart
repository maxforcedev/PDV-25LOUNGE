import 'dart:async';

import 'package:flutter/widgets.dart';

import '../network/pos_api.dart';
import 'local_print_ledger.dart';
import 'models.dart';
import 'network_printer_transport.dart';
import 'production_ticket_renderer.dart';

class PrintManager with WidgetsBindingObserver {
  PrintManager({
    required PosApi api,
    required LocalPrintLedger ledger,
    NetworkPrinterTransport? transport,
    ProductionTicketRenderer? renderer,
  })  : _api = api,
        _ledger = ledger,
        _transport = transport ?? NetworkPrinterTransport(),
        _renderer = renderer ?? ProductionTicketRenderer();

  final PosApi _api;
  final LocalPrintLedger _ledger;
  final NetworkPrinterTransport _transport;
  final ProductionTicketRenderer _renderer;
  Timer? _timer;
  bool _operational = false;
  bool _foreground = true;
  bool _running = false;

  void setOperational(bool value) {
    _operational = value;
    if (value) {
      _timer ??= Timer.periodic(const Duration(seconds: 3), (_) => _tick());
      unawaited(_tick());
    } else {
      _timer?.cancel();
      _timer = null;
    }
  }

  void start() => WidgetsBinding.instance.addObserver(this);

  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    if (_foreground) unawaited(_tick());
  }

  Future<void> _tick() async {
    if (!_operational || !_foreground || _running) return;
    _running = true;
    try {
      await _reconcile();
      final printers = {
        for (final printer in await _api.networkPrinters()) printer.id: printer
      };
      final available = await _api.printingJobs();
      if (available.isEmpty) return;
      final claimed = await _api.claimPrintJob(available.first.id);
      if (claimed.isEmpty) return;
      final printer = printers[claimed.first.printerId];
      if (printer == null) return;
      await _api.renewPrintLease(claimed.first.id);
      await _execute(claimed, printer);
    } catch (_) {
      // Printing must never block sales or turn transient internet loss into a retry.
    } finally {
      _running = false;
    }
  }

  Future<void> _reconcile() async {
    final entries = await _ledger.entries();
    final sent = entries.where((entry) => entry.state == 'sent').toList();
    if (sent.isEmpty) return;
    try {
      await _api.reconcilePrintJobs([
        for (final entry in sent) {'job_id': entry.jobId, 'state': 'sent'},
      ]);
      await _ledger.removeAll(sent.map((entry) => entry.jobId));
    } catch (_) {
      // Keep the record: an HTTP failure must not cause a second physical send.
    }
  }

  Future<void> _execute(List<PrintJob> jobs, NetworkPrinter printer) async {
    for (final job in jobs) {
      await _ledger.mark(PrintLedgerEntry(
        jobId: job.id,
        printerId: job.printerId,
        idempotencyKey: job.idempotencyKey,
        state: 'attempted',
      ));
    }
    final result = await _transport.send(
      printer,
      _renderer.render(jobs, paperWidth: printer.paperWidth, cut: printer.cut),
    );
    final ids = jobs.map((job) => job.id);
    if (result.state == PrintTransportState.failedBeforeSend) {
      try {
        await _api.reportPrintResult(jobs.first.id, 'failed',
            error: result.detail);
        await _ledger.removeAll(ids);
      } catch (_) {}
      return;
    }
    for (final job in jobs) {
      await _ledger.mark(PrintLedgerEntry(
        jobId: job.id,
        printerId: job.printerId,
        idempotencyKey: job.idempotencyKey,
        state: 'sent',
      ));
    }
    final outcome =
        result.state == PrintTransportState.sent ? 'printed' : 'uncertain';
    try {
      await _api.reportPrintResult(jobs.first.id, outcome,
          error: result.detail, metadata: {'transport': 'tcp_lan'});
      await _ledger.removeAll(ids);
    } catch (_) {
      // The sent ledger is reconciled as uncertain after connectivity returns.
    }
  }
}
