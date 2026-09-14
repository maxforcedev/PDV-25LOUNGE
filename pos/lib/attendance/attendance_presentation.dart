import '../cash/cash_models.dart';

String normalizedAttendanceMoney(Object? value) {
  final amount = double.tryParse('${value ?? ''}'.replaceAll(',', '.')) ?? 0;
  return amount.toStringAsFixed(2);
}

String formatAttendanceMoney(Object? value) =>
    formatMoney(normalizedAttendanceMoney(value));

String formatAttendanceQuantity(Object? value) {
  final quantity = double.tryParse('${value ?? ''}'.replaceAll(',', '.')) ?? 0;
  return quantity == quantity.roundToDouble()
      ? quantity.toInt().toString()
      : quantity.toStringAsFixed(3).replaceFirst(RegExp(r'0+$'), '');
}

String localizedAttendanceStatus(String status) =>
    switch (status.toLowerCase()) {
      'open' => 'Aberta',
      'closed' => 'Fechada',
      'occupied' => 'Ocupada',
      'free' => 'Livre',
      'confirmed' => 'Confirmado',
      'cancelled' || 'canceled' => 'Cancelado',
      'pending' => 'Pendente',
      'applied' => 'Aplicado',
      _ => 'Indisponível',
    };

String? localizedPrintStatus(String? printStatus) =>
    switch (printStatus?.toLowerCase()) {
      'printed' => 'Impresso',
      'pending' => 'Aguardando impressão',
      'processing' => 'Impressão em andamento',
      'failed' => 'Falha na impressão',
      _ => null,
    };
