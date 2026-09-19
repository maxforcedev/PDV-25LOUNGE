class PaymentDisplayEntry {
  const PaymentDisplayEntry({
    required this.id,
    required this.methodName,
    required this.amount,
    required this.status,
    this.receivedAmount,
    this.changeAmount,
    this.reversalOf,
    this.reversalReason,
  });

  final Object id;
  final String methodName;
  final String amount;
  final String status;
  final String? receivedAmount;
  final String? changeAmount;
  final Object? reversalOf;
  final String? reversalReason;

  bool get isReversal => reversalOf != null || status == 'reversed';
}

class PaymentSummaryLine {
  const PaymentSummaryLine({
    required this.label,
    required this.value,
    this.negative = false,
  });

  final String label;
  final String value;
  final bool negative;
}

class PaymentSummaryData {
  const PaymentSummaryData({
    required this.total,
    required this.paid,
    required this.remaining,
    this.details = const [],
  });

  final String total;
  final String paid;
  final String remaining;
  final List<PaymentSummaryLine> details;
}
