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
      attempt: 1,
      state: 'sent',
      printerObserved: true,
    ));
    final recovered = await LocalPrintLedger(store).entries();
    expect(recovered.single.jobId, 10);
    expect(recovered.single.state, 'sent');
    expect(recovered.single.printerObserved, isTrue);
    expect(recovered.single.attempt, 1);
  });

  test('ledger preserves an attempted job for safe reconciliation', () async {
    final store = _Store();
    await LocalPrintLedger(store).mark(const PrintLedgerEntry(
      jobId: 11,
      printerId: 2,
      idempotencyKey: 'attempted-boundary',
      state: 'attempted',
    ));

    final recovered = await LocalPrintLedger(store).entries();
    expect(recovered.single.state, 'attempted');
    expect(recovered.single.attemptedAt, isNotNull);
  });

  test(
      'renderer identifies cancellation, modifiers, and does not include prices',
      () {
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
          'modifiers': [
            {
              'option_type': 'add',
              'option_name': 'Bacon',
              'selected_quantity': '2',
              'stock_product_cost': '3.50',
            },
            {'option_type': 'remove', 'option_name': 'Cebola'},
            {
              'option_type': 'component_substitution',
              'substituted_component_name': 'Queijo',
              'option_name': 'Brioche',
              'selected_quantity': '1',
            },
          ],
          'notes': ''
        },
      },
    );
    final bytes =
        ProductionTicketRenderer().render([job], paperWidth: 80, cut: true);
    expect(bytes, containsAll(<int>[0x1b, 0x40, 0x1d, 0x56]));
    final rendered = String.fromCharCodes(bytes);
    expect(rendered, contains('+ 2 x Bacon'));
    expect(rendered, contains('- SEM Cebola'));
    expect(rendered, contains('SUBSTITUIR Queijo POR 1 x Brioche'));
    expect(rendered, isNot(contains('R\$')));
    expect(rendered, isNot(contains('3.50')));
  });

  test('test ticket keeps a visible safe width for 58mm paper', () {
    const job = PrintJob(
      id: 2,
      printerId: 2,
      idempotencyKey: 'test-width',
      isTest: true,
      status: 'processing',
      reprintNumber: 0,
      payload: {
        'test': true,
        'printer': 'Caixa principal',
        'host': '192.168.0.20',
      },
    );

    final rendered = String.fromCharCodes(
        ProductionTicketRenderer().render([job], paperWidth: 58, cut: true));
    expect(rendered, contains('Papel: 58mm'));
    expect(rendered, contains('-' * 28));
    expect(rendered, isNot(contains('-' * 29)));
  });
}
