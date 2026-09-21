import 'dart:convert';

import 'attendance_models.dart';

Object? _normalizedTableOrderItemValue(Object? value) {
  if (value is Map) {
    final entries = value.entries
        .map((entry) => MapEntry(
            '${entry.key}', _normalizedTableOrderItemValue(entry.value)))
        .toList()
      ..sort((a, b) => a.key.compareTo(b.key));
    return Map<String, Object?>.fromEntries(entries);
  }
  if (value is List) {
    final entries = value.map(_normalizedTableOrderItemValue).toList()
      ..sort((a, b) => jsonEncode(a).compareTo(jsonEncode(b)));
    return entries;
  }
  return value;
}

double _tableOrderItemNumber(Object? value) =>
    double.tryParse('$value'.replaceAll(',', '.')) ?? 0;

class TableOrderItemEntry {
  const TableOrderItemEntry({required this.item, required this.order});

  final TableOrderItem item;
  final TableOrder order;
}

class TableOrderItemGroup {
  TableOrderItemGroup(this.first) : entries = [first];

  final TableOrderItemEntry first;
  final List<TableOrderItemEntry> entries;

  TableOrderItem get item => first.item;

  double get quantity => entries.fold(
      0, (total, entry) => total + _tableOrderItemNumber(entry.item.quantity));

  double get lineTotal => entries.fold(0, (total, entry) {
        final item = entry.item;
        final amount = item.lineTotal == null
            ? _tableOrderItemNumber(item.unitPrice) *
                _tableOrderItemNumber(item.quantity)
            : _tableOrderItemNumber(item.lineTotal);
        return total + amount;
      });

  List<TableOrderItemEntry> get entriesByOperationalAge {
    final result = List<TableOrderItemEntry>.from(entries);
    result.sort((a, b) {
      final aTime =
          DateTime.tryParse(a.item.confirmedAt ?? a.order.createdAt ?? '');
      final bTime =
          DateTime.tryParse(b.item.confirmedAt ?? b.order.createdAt ?? '');
      if (aTime != null && bTime != null) {
        final comparison = aTime.compareTo(bTime);
        if (comparison != 0) return comparison;
      } else if (aTime != null) {
        return -1;
      } else if (bTime != null) {
        return 1;
      }
      final orderComparison = a.order.id.compareTo(b.order.id);
      return orderComparison != 0
          ? orderComparison
          : a.item.id.compareTo(b.item.id);
    });
    return result;
  }
}

List<TableOrderItemGroup> tableOrderItemGroups(
  TableAttendance attendance, {
  bool confirmedOnly = false,
}) =>
    tableOrderItemGroupsForEntries(
      attendance.orders.expand((order) => order.items
          .where((item) =>
              !confirmedOnly || item.status.toLowerCase() == 'confirmed')
          .map(
            (item) => TableOrderItemEntry(item: item, order: order),
          )),
    );

List<TableOrderItemGroup> tableOrderItemGroupsForEntries(
    Iterable<TableOrderItemEntry> entries) {
  final groupsByKey = <String, TableOrderItemGroup>{};
  for (final entry in entries) {
    final item = entry.item;
    // This is visual equivalence only; every group retains its real entries.
    final key = [
      item.productId,
      item.unit.toLowerCase(),
      _tableOrderItemNumber(item.unitPrice).toStringAsFixed(2),
      jsonEncode(_normalizedTableOrderItemValue(item.modifierSnapshot)),
      jsonEncode(_normalizedTableOrderItemValue(item.financialSnapshot)),
      item.notes,
      item.status.toLowerCase(),
      item.printStatus?.toLowerCase() ?? '',
      item.cancellationReason,
    ].join('\u0001');
    final group = groupsByKey[key];
    if (group == null) {
      groupsByKey[key] = TableOrderItemGroup(entry);
    } else {
      group.entries.add(entry);
    }
  }
  return groupsByKey.values.toList(growable: false);
}
