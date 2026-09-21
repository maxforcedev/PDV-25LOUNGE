import 'package:core_pos/payments/payment_flow_components.dart';
import 'package:core_pos/sales/sale_models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const cash = QuickSalePaymentMethod(
    id: 1,
    code: 'cash',
    name: 'Dinheiro',
    kind: 'cash',
  );

  Future<ValueNotifier<PaymentEntryResult?>> openEntry(
      WidgetTester tester) async {
    final result = ValueNotifier<PaymentEntryResult?>(null);
    await tester.binding.setSurfaceSize(const Size(1200, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => FilledButton(
          onPressed: () async {
            result.value = await Navigator.of(context).push<PaymentEntryResult>(
              MaterialPageRoute(
                builder: (_) => const PaymentEntryPage(
                  method: cash,
                  remaining: '10.00',
                  amountContext: PaymentAmountContext.value,
                ),
              ),
            );
          },
          child: const Text('OPEN'),
        ),
      ),
    ));
    await tester.tap(find.text('OPEN'));
    await tester.pumpAndSettle();
    return result;
  }

  testWidgets('backspace on received amount preserves remaining mode',
      (tester) async {
    final result = await openEntry(tester);

    await tester.tap(find.text('PAGAR SALDO'));
    await tester.pump();
    await tester.tap(find.text('Informar valor recebido'));
    await tester.pump();
    await tester.tap(find.text('R\$ 20'));
    await tester.pump();
    await tester.tap(find.text('0'));
    await tester.pump();
    await tester.tap(find.byIcon(Icons.backspace_outlined));
    await tester.pump();
    final confirm = find.widgetWithText(
      FilledButton,
      'CONFIRMAR PAGAMENTO MANUAL',
    );
    expect(tester.widget<FilledButton>(confirm).onPressed, isNotNull);
    await tester.tap(confirm);
    await tester.pumpAndSettle();
    await tester.pump();

    expect(find.byType(PaymentEntryPage), findsNothing);
    expect(result.value?.payingRemaining, isTrue);
  });

  testWidgets('backspace on applied amount clears remaining mode',
      (tester) async {
    final result = await openEntry(tester);
    await tester.tap(find.text('PAGAR SALDO'));
    await tester.pump();
    await tester.tap(find.byIcon(Icons.backspace_outlined));
    await tester.pump();
    final confirm = find.widgetWithText(
      FilledButton,
      'CONFIRMAR PAGAMENTO MANUAL',
    );
    expect(tester.widget<FilledButton>(confirm).onPressed, isNotNull);
    await tester.tap(confirm);
    await tester.pumpAndSettle();
    await tester.pump();

    expect(find.byType(PaymentEntryPage), findsNothing);
    expect(result.value?.payingRemaining, isFalse);
  });
}
