class TicketValidationTicket {
  const TicketValidationTicket({
    required this.number,
    required this.status,
    required this.productName,
    required this.unit,
    required this.totalQuantity,
    required this.redeemedQuantity,
    required this.redeemableQuantity,
    required this.cancelledUnredeemedQuantity,
    required this.modifiers,
    required this.notes,
  });

  factory TicketValidationTicket.fromJson(Map<String, dynamic> json) =>
      TicketValidationTicket(
        number: json['number'] as int,
        status: json['status'] as String? ?? 'issued',
        productName: json['product_name'] as String? ?? '',
        unit: json['unit'] as String? ?? '',
        totalQuantity: json['total_quantity'] as String? ?? '0.000',
        redeemedQuantity: json['redeemed_quantity'] as String? ?? '0.000',
        redeemableQuantity: json['redeemable_quantity'] as String? ?? '0.000',
        cancelledUnredeemedQuantity:
            json['cancelled_unredeemed_quantity'] as String? ?? '0.000',
        modifiers: (json['modifiers'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>(),
        notes: json['notes'] as String? ?? '',
      );
  final int number;
  final String status,
      productName,
      unit,
      totalQuantity,
      redeemedQuantity,
      redeemableQuantity,
      cancelledUnredeemedQuantity,
      notes;
  final List<Map<String, dynamic>> modifiers;
  bool get redeemable => status == 'issued' || status == 'partially_used';
}

class TicketValidationResult {
  const TicketValidationResult({required this.ticket, this.redeemedNow});
  factory TicketValidationResult.fromJson(Map<String, dynamic> json) =>
      TicketValidationResult(
        ticket: TicketValidationTicket.fromJson(
            json['ticket'] as Map<String, dynamic>),
        redeemedNow: (json['redemption'] as Map<String, dynamic>?)?['quantity']
            as String?,
      );
  final TicketValidationTicket ticket;
  final String? redeemedNow;
}
