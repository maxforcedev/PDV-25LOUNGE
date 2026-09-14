import 'package:flutter/material.dart';

import '../cash/cash_models.dart';

class SharedCartItemTile extends StatelessWidget {
  const SharedCartItemTile({
    required this.name,
    required this.quantity,
    required this.amount,
    this.details = '',
    this.status,
    this.warning,
    this.onTap,
    this.onLongPress,
    super.key,
  });

  final String name;
  final String quantity;
  final String amount;
  final String details;
  final String? status;
  final String? warning;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        onLongPress: onLongPress,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 7),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(
                child: Text(name,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              ),
              const SizedBox(width: 8),
              Text(formatMoney(amount),
                  style: const TextStyle(
                      color: Color(0xff3454d1), fontWeight: FontWeight.w800)),
            ]),
            if (status != null)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(status!,
                    style: const TextStyle(
                        color: Color(0xff64748b),
                        fontSize: 11,
                        fontWeight: FontWeight.w700)),
              ),
            if (details.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child:
                    Text(details, maxLines: 3, overflow: TextOverflow.ellipsis),
              ),
            Text('Qtd. $quantity', style: const TextStyle(fontSize: 12)),
            if (warning != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(warning!,
                    style: const TextStyle(
                        color: Color(0xffb42318),
                        fontWeight: FontWeight.w700,
                        fontSize: 12)),
              ),
          ]),
        ),
      );
}

class SharedTotalsLine {
  const SharedTotalsLine(
      {required this.label,
      required this.value,
      this.negative = false,
      this.strong = false});

  final String label;
  final String value;
  final bool negative;
  final bool strong;
}

class SharedTotalsPanel extends StatelessWidget {
  const SharedTotalsPanel({required this.lines, super.key});

  final List<SharedTotalsLine> lines;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final line in lines)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(line.label,
                        style: TextStyle(
                            fontWeight: line.strong
                                ? FontWeight.w800
                                : FontWeight.w400)),
                    Text(
                        '${line.negative ? '- ' : ''}${formatMoney(line.value)}',
                        style: TextStyle(
                            fontWeight: line.strong
                                ? FontWeight.w800
                                : FontWeight.w500)),
                  ]),
            ),
        ],
      );
}
