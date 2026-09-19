import '../sales/sale_models.dart';
import 'payment_contract.dart';

class QuickSalePaymentAdapter {
  const QuickSalePaymentAdapter(this.checkout);

  final QuickSaleCheckout checkout;

  PaymentDisplayEntry payment(QuickSaleCheckoutPayment value) =>
      PaymentDisplayEntry(
        id: value.id,
        methodName: value.methodName,
        amount: value.amount,
        status: value.status,
        receivedAmount: value.receivedAmount,
        changeAmount: value.changeAmount,
        reversalOf: value.reversalOf,
        reversalReason: value.reversalReason,
      );

  PaymentSummaryData get summary => PaymentSummaryData(
        total: checkout.preview.total,
        paid: checkout.paidAmount,
        remaining: checkout.remainingAmount,
        details: [
          PaymentSummaryLine(
              label: 'Subtotal', value: checkout.preview.subtotal),
          PaymentSummaryLine(
              label: 'Promoções',
              value: checkout.preview.promotionDiscountTotal,
              negative: true),
          PaymentSummaryLine(
              label: 'Descontos por item',
              value: checkout.preview.itemDiscountTotal,
              negative: true),
          PaymentSummaryLine(
              label: 'Desconto da venda',
              value: checkout.preview.discount,
              negative: true),
          PaymentSummaryLine(
              label: 'Taxa de serviço',
              value: checkout.preview.serviceFeeAmount),
        ],
      );
}
