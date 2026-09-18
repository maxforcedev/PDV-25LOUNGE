String formatQuantity(Object? value) {
  final raw = '$value'.trim();
  final quantity = double.tryParse(raw.replaceAll(',', '.'));
  if (quantity == null) return raw;
  var formatted = quantity.toStringAsFixed(3).replaceFirst(RegExp(r'0+$'), '');
  if (formatted.endsWith('.')) {
    formatted = formatted.substring(0, formatted.length - 1);
  }
  return formatted.replaceAll('.', ',');
}

String formatQuantityForApi(double value) {
  var formatted = value.toStringAsFixed(3).replaceFirst(RegExp(r'0+$'), '');
  if (formatted.endsWith('.')) {
    formatted = formatted.substring(0, formatted.length - 1);
  }
  return formatted;
}

String quickSaleStatusLabel(String status) => switch (status) {
      'editing' || 'open' => 'Em andamento',
      'partial' => 'Pagamento parcial',
      'paid' => 'Pago',
      'finalized' => 'Finalizada',
      'cancelled' => 'Cancelada',
      'applied' => 'Confirmado',
      'reversed' => 'Estornado',
      _ => 'Em processamento',
    };
