import '../attendance/attendance_models.dart';
import 'payment_contract.dart';

class TablePaymentAdapter {
  const TablePaymentAdapter(this.attendance, this.ledger);

  final TableAttendance attendance;
  final TablePaymentLedger? ledger;

  Map<String, dynamic> get _financials => ledger?.summary ?? attendance.summary;
  String _value(String key) => '${_financials[key] ?? '0.00'}';

  PaymentDisplayEntry payment(TablePayment value) => PaymentDisplayEntry(
        id: value.id,
        methodName: value.paymentMethodName,
        amount: value.amount,
        status: value.status,
        receivedAmount: value.receivedAmount,
        changeAmount: value.changeAmount,
        reversalOf: value.reversalOf,
        reversalReason: value.reversalReason,
      );

  PaymentSummaryData get summary => PaymentSummaryData(
        total: _value('total_due'),
        paid: _value('paid_total'),
        remaining: _value('remaining_balance'),
        details: [
          PaymentSummaryLine(label: 'Subtotal', value: _value('subtotal')),
          PaymentSummaryLine(
              label: 'Promoções',
              value: _value('promotion_discount_total'),
              negative: true),
          PaymentSummaryLine(
              label: 'Descontos por item',
              value: _value('item_discount_total'),
              negative: true),
          PaymentSummaryLine(
              label: 'Desconto da mesa',
              value: _value('checkout_discount_total'),
              negative: true),
          PaymentSummaryLine(
              label: 'Taxa de serviço', value: _value('service_fee_total')),
        ],
      );
}
