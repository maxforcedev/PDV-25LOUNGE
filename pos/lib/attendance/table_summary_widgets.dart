import 'package:flutter/material.dart';

import 'attendance_presentation.dart';

class TableSummaryWidgets extends StatelessWidget {
  const TableSummaryWidgets(this.summary, {super.key});
  final Map<String, dynamic> summary;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _row('Subtotal', summary['subtotal']),
          _row('Descontos', summary['discount_total']),
          _row('Taxa', summary['service_fee_total']),
          _row('TOTAL', summary['total_due'], bold: true),
        ],
      );

  Widget _row(String label, Object? value, {bool bold = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child:
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text(label,
              style: TextStyle(fontWeight: bold ? FontWeight.w800 : null)),
          Text(formatAttendanceMoney(value),
              style: TextStyle(fontWeight: bold ? FontWeight.w800 : null)),
        ]),
      );
}
