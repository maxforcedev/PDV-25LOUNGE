import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import '../sales/sale_models.dart';
import '../sales/sale_presentation.dart';
import '../sales/shared_pos_widgets.dart';

class PaymentBalanceCard extends StatelessWidget {
  const PaymentBalanceCard({
    required this.checkout,
    super.key,
  });

  final QuickSaleCheckout checkout;

  bool get _isPaid =>
      (double.tryParse(checkout.remainingAmount.replaceAll(',', '.')) ?? 0) ==
      0;

  @override
  Widget build(BuildContext context) {
    final paid = _isPaid;
    final amount = paid ? checkout.paidAmount : checkout.remainingAmount;
    final color = paid ? const Color(0xff16803c) : const Color(0xff3454d1);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withValues(alpha: .08),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: .28)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 18),
        child: Column(children: [
          Text(paid ? 'PAGO' : 'FALTA',
              style: TextStyle(color: color, fontWeight: FontWeight.w900)),
          const SizedBox(height: 2),
          Text(formatMoney(amount),
              style: Theme.of(context)
                  .textTheme
                  .headlineMedium
                  ?.copyWith(color: color, fontWeight: FontWeight.w900)),
        ]),
      ),
    );
  }
}

class PaymentMethodButton extends StatelessWidget {
  const PaymentMethodButton({
    required this.label,
    required this.icon,
    required this.onTap,
    super.key,
  });

  final String label;
  final IconData icon;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(14),
          child: Ink(
            height: 68,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: const Color(0xffdbe4ff)),
            ),
            child:
                Column(mainAxisAlignment: MainAxisAlignment.center, children: [
              Icon(icon, color: const Color(0xff3454d1)),
              const SizedBox(height: 4),
              Text(label.toUpperCase(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w800)),
            ]),
          ),
        ),
      );
}

class PaymentHistoryItem extends StatelessWidget {
  const PaymentHistoryItem({
    required this.payment,
    required this.reversed,
    required this.canReverse,
    required this.working,
    required this.onReverse,
    super.key,
  });

  final QuickSaleCheckoutPayment payment;
  final bool reversed;
  final bool canReverse;
  final bool working;
  final VoidCallback onReverse;

  @override
  Widget build(BuildContext context) {
    final status = reversed
        ? quickSaleStatusLabel('reversed')
        : payment.status != 'applied'
            ? quickSaleStatusLabel(payment.status)
            : payment.receivedAmount == null
                ? quickSaleStatusLabel(payment.status)
                : 'Recebido ${formatMoney(payment.receivedAmount!)}  Troco ${formatMoney(payment.changeAmount ?? '0.00')}';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        Icon(reversed ? Icons.undo : Icons.check_circle_rounded,
            size: 19,
            color:
                reversed ? const Color(0xffb42318) : const Color(0xff16803c)),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(payment.methodName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w800)),
                Text(status,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 12, color: Color(0xff64748b))),
              ]),
        ),
        Text(formatMoney(payment.amount),
            style: const TextStyle(fontWeight: FontWeight.w800)),
        if (!reversed && canReverse)
          IconButton(
            onPressed: working ? null : onReverse,
            tooltip: 'Estornar',
            icon: const Icon(Icons.undo, size: 20),
          ),
      ]),
    );
  }
}

class PaymentFinancialSummary extends StatelessWidget {
  const PaymentFinancialSummary({
    required this.checkout,
    required this.showDetails,
    required this.onToggleDetails,
    required this.primaryAction,
    super.key,
  });

  final QuickSaleCheckout checkout;
  final bool showDetails;
  final VoidCallback onToggleDetails;
  final Widget? primaryAction;

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.white,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 14),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            if (showDetails)
              SharedTotalsPanel(lines: [
                SharedTotalsLine(
                    label: 'Subtotal', value: checkout.preview.subtotal),
                SharedTotalsLine(
                    label: 'Promoções',
                    value: checkout.preview.promotionDiscountTotal,
                    negative: true),
                SharedTotalsLine(
                    label: 'Descontos por item',
                    value: checkout.preview.itemDiscountTotal,
                    negative: true),
                SharedTotalsLine(
                    label: 'Desconto da venda',
                    value: checkout.preview.discount,
                    negative: true),
                SharedTotalsLine(
                    label: 'Taxa de serviço',
                    value: checkout.preview.serviceFeeAmount),
              ]),
            Row(children: [
              const Text('RESUMO',
                  style: TextStyle(fontWeight: FontWeight.w900)),
              const Spacer(),
              TextButton.icon(
                onPressed: onToggleDetails,
                icon: Icon(showDetails ? Icons.expand_more : Icons.expand_less),
                label: Text(showDetails ? 'OCULTAR' : 'DETALHES'),
              ),
            ]),
            SharedTotalsPanel(lines: [
              SharedTotalsLine(
                  label: 'Total', value: checkout.preview.total, strong: true),
              SharedTotalsLine(label: 'Pago', value: checkout.paidAmount),
              SharedTotalsLine(
                  label: 'Falta',
                  value: checkout.remainingAmount,
                  strong: true),
            ]),
            if (primaryAction != null) ...[
              const SizedBox(height: 10),
              SizedBox(width: double.infinity, child: primaryAction),
            ],
          ]),
        ),
      );
}
