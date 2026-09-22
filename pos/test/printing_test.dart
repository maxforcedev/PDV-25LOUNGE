import 'package:core_pos/printing/local_print_ledger.dart';
import 'package:core_pos/printing/models.dart';
import 'package:core_pos/printing/production_ticket_renderer.dart';
import 'package:core_pos/storage/secret_store.dart';
import 'package:flutter_test/flutter_test.dart';

class _Store implements SecretStore, PrintLedgerStateStore {
  String? value;
  @override
  Future<String?> readPrintLedgerState() async => value;
  @override
  Future<void> writePrintLedgerState(String value) async => this.value = value;
  @override
  Future<String?> readDeviceCredential() async => null;
  @override
  Future<void> writeDeviceCredential(String credential) async {}
  @override
  Future<void> clearDeviceCredential() async {}
  @override
  Future<String?> readOperatorSession() async => null;
  @override
  Future<void> writeOperatorSession(String token) async {}
  @override
  Future<void> clearOperatorSession() async {}
  @override
  Future<String?> readPendingSaleIntents() async => null;
  @override
  Future<void> writePendingSaleIntents(String value) async {}
}

void main() {
  test('ledger preserves a physically sent job across a new instance',
      () async {
    final store = _Store();
    final ledger = LocalPrintLedger(store);
    await ledger.mark(const PrintLedgerEntry(
      jobId: 10,
      printerId: 2,
      idempotencyKey: 'stable',
      state: 'sent',
      printerObserved: true,
    ));
    final recovered = await LocalPrintLedger(store).entries();
    expect(recovered.single.jobId, 10);
    expect(recovered.single.state, 'sent');
    expect(recovered.single.printerObserved, isTrue);
  });

  test('renderer identifies cancellation and does not include prices', () {
    const job = PrintJob(
      id: 1,
      printerId: 2,
      idempotencyKey: 'key',
      isTest: false,
      status: 'processing',
      reprintNumber: 0,
      payload: {
        'event': 'cancel',
        'branch_name': 'CORE PDV',
        'destination': {'name': 'COZINHA'},
        'table': {'name': '10'},
        'cancellation_reason': 'Cliente desistiu',
        'source_item': {
          'quantity': '1',
          'product_name': 'X-Bacon',
          'modifiers': [],
          'notes': ''
        },
      },
    );
    final bytes =
        ProductionTicketRenderer().render([job], paperWidth: 80, cut: true);
    expect(bytes, containsAll(<int>[0x1b, 0x40, 0x1d, 0x56]));
    expect(String.fromCharCodes(bytes), isNot(contains('R\$')));
  });
}
