import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import '../sales/sale_presentation.dart';
import '../sales/shared_pos_widgets.dart';
import 'payment_contract.dart';

class PaymentBalanceCard extends StatelessWidget {
  const PaymentBalanceCard({
    required this.summary,
    super.key,
  });

  final PaymentSummaryData summary;

  bool get _isPaid =>
      (double.tryParse(summary.remaining.replaceAll(',', '.')) ?? 0) == 0;

  @override
  Widget build(BuildContext context) {
    final paid = _isPaid;
    final amount = paid ? summary.paid : summary.remaining;
    final color = paid ? const Color(0xff16803c) : const Color(0xff3454d1);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withValues(alpha: .08),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: .28)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 14),
        child: Row(children: [
          Text(paid ? 'PAGO' : 'FALTA',
              style: TextStyle(color: color, fontWeight: FontWeight.w900)),
          const Spacer(),
          Text(formatMoney(amount),
              style: Theme.of(context)
                  .textTheme
                  .titleLarge
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
            height: 56,
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
    required this.working,
    required this.onReverse,
    this.onPrint,
    this.printTooltip,
    this.reversalReason,
    super.key,
  });

  final PaymentDisplayEntry payment;
  final bool reversed;
  final bool working;
  final VoidCallback onReverse;
  final VoidCallback? onPrint;
  final String? printTooltip;
  final String? reversalReason;

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
                if (reversalReason != null && reversalReason!.isNotEmpty)
                  Text('Motivo: $reversalReason',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 12, color: Color(0xff64748b))),
              ]),
        ),
        Text(formatMoney(payment.amount),
            style: const TextStyle(fontWeight: FontWeight.w800)),
        if (!reversed && onPrint != null)
          IconButton(
            onPressed: working ? null : onPrint,
            tooltip: printTooltip ?? 'Imprimir comprovante',
            icon: const Icon(Icons.print_outlined, size: 20),
          ),
        if (!reversed)
          IconButton(
            onPressed: working ? null : onReverse,
            tooltip: 'Estornar',
            icon: const Icon(Icons.undo, size: 20),
          ),
      ]),
    );
  }
}

class PaymentReversalDialog extends StatefulWidget {
  const PaymentReversalDialog({required this.payment, super.key});

  final PaymentDisplayEntry payment;

  @override
  State<PaymentReversalDialog> createState() => _PaymentReversalDialogState();
}

class _PaymentReversalDialogState extends State<PaymentReversalDialog> {
  final _reason = TextEditingController();

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('ESTORNAR PAGAMENTO?'),
        content: SizedBox(
          width: 360,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Text(widget.payment.methodName,
                  style: const TextStyle(fontWeight: FontWeight.w800)),
            ),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(formatMoney(widget.payment.amount)),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _reason,
              maxLength: 1000,
              maxLines: 2,
              decoration: const InputDecoration(labelText: 'Motivo (opcional)'),
            ),
          ]),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('VOLTAR')),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(_reason.text.trim()),
            child: const Text('ESTORNAR PAGAMENTO'),
          ),
        ],
      );
}

class PaymentFinancialSummary extends StatelessWidget {
  const PaymentFinancialSummary({
    required this.summary,
    required this.showDetails,
    required this.onToggleDetails,
    required this.primaryAction,
    super.key,
  });

  final PaymentSummaryData summary;
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
                for (final line in summary.details)
                  SharedTotalsLine(
                      label: line.label,
                      value: line.value,
                      negative: line.negative),
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
                  label: 'Total', value: summary.total, strong: true),
              SharedTotalsLine(label: 'Pago', value: summary.paid),
              SharedTotalsLine(
                  label: 'Falta', value: summary.remaining, strong: true),
            ]),
            if (primaryAction != null) ...[
              const SizedBox(height: 10),
              SizedBox(width: double.infinity, child: primaryAction),
            ],
          ]),
        ),
      );
}
