import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import 'attendance_models.dart';

class SharedTablesGrid extends StatelessWidget {
  const SharedTablesGrid({
    required this.tables,
    required this.onTap,
    this.onLongPress,
    this.isDisabled,
    this.statusLabel,
    this.isSelected,
    super.key,
  });

  final List<AttendanceTable> tables;
  final ValueChanged<AttendanceTable>? onTap;
  final ValueChanged<AttendanceTable>? onLongPress;
  final bool Function(AttendanceTable table)? isDisabled;
  final String? Function(AttendanceTable table)? statusLabel;
  final bool Function(AttendanceTable table)? isSelected;

  @override
  Widget build(BuildContext context) => GridView.builder(
        padding: const EdgeInsets.all(16),
        gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
          maxCrossAxisExtent: 230,
          mainAxisSpacing: 12,
          crossAxisSpacing: 12,
          childAspectRatio: 1.2,
        ),
        itemCount: tables.length,
        itemBuilder: (_, index) {
          final table = tables[index];
          final disabled = isDisabled?.call(table) ?? table.legacyOccupied;
          return SharedTableCard(
            table: table,
            disabled: disabled,
            statusLabel: statusLabel?.call(table),
            selected: isSelected?.call(table) ?? false,
            onTap: disabled ? null : () => onTap?.call(table),
            onLongPress: disabled ? null : () => onLongPress?.call(table),
          );
        },
      );
}

class SharedTableCard extends StatelessWidget {
  const SharedTableCard({
    required this.table,
    this.disabled = false,
    this.statusLabel,
    this.selected = false,
    this.onTap,
    this.onLongPress,
    super.key,
  });

  final AttendanceTable table;
  final bool disabled;
  final String? statusLabel;
  final bool selected;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  @override
  Widget build(BuildContext context) {
    final locked = table.legacyOccupied;
    final color = locked
        ? Colors.orange
        : table.isOpen
            ? Colors.red
            : Colors.green;
    final label = statusLabel ??
        (locked
            ? 'ATENDIMENTO LEGADO'
            : table.isOpen
                ? 'OCUPADA'
                : 'LIVRE');
    return Opacity(
      opacity: disabled && !locked ? .55 : 1,
      child: Card(
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: onTap,
          onLongPress: onLongPress,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(table.name,
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.w800)),
                const Spacer(),
                Text(label,
                    style: TextStyle(
                        color: color.shade700, fontWeight: FontWeight.w700)),
                if (table.capacity > 0) Text('${table.capacity} lugares'),
                if (table.isOpen) Text('Saldo: ${formatMoney(table.balance)}'),
                if (table.billRequested)
                  const Text('CONTA SOLICITADA',
                      style: TextStyle(
                          fontWeight: FontWeight.w700,
                          color: Colors.deepOrange)),
                if (table.group != null)
                  Text('Grupo: ${table.group!.tableNames.join(', ')}'),
                if (selected)
                  const Align(
                    alignment: Alignment.centerRight,
                    child: Icon(Icons.check_circle, color: Colors.blue),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
