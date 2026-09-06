import 'dart:math';

class CashRegisterInfo {
  const CashRegisterInfo({
    required this.id,
    required this.name,
    required this.status,
    this.session,
  });

  factory CashRegisterInfo.fromJson(Map<String, dynamic> json) =>
      CashRegisterInfo(
        id: json['id'] as int,
        name: json['name'] as String? ?? '',
        status: json['status'] as String? ?? 'inactive',
        session: json['session'] is Map<String, dynamic>
            ? CashSessionInfo.fromJson(json['session'] as Map<String, dynamic>)
            : null,
      );

  final int id;
  final String name;
  final String status;
  final CashSessionInfo? session;
}

class CashSessionInfo {
  const CashSessionInfo({
    required this.id,
    required this.registerId,
    required this.registerName,
    required this.status,
    required this.openedByName,
    required this.openedAt,
    this.openingAmount,
  });

  factory CashSessionInfo.fromJson(Map<String, dynamic> json) {
    final register = json['register'] as Map<String, dynamic>?;
    return CashSessionInfo(
      id: json['id'] as int,
      registerId: (register?['id'] ?? json['cash_register']) as int,
      registerName: (register?['name'] ??
              json['register_name'] ??
              json['cash_register_name']) as String? ??
          '',
      status: json['status'] as String? ?? 'open',
      openedByName: json['opened_by_name'] as String? ?? '',
      openedAt: DateTime.tryParse(json['opened_at'] as String? ?? ''),
      openingAmount: json['opening_amount'] as String?,
    );
  }

  final int id;
  final int registerId;
  final String registerName;
  final String status;
  final String openedByName;
  final DateTime? openedAt;
  final String? openingAmount;
}

class CashOverview {
  const CashOverview({
    required this.mode,
    required this.enabled,
    this.register,
    this.session,
    this.registers = const [],
  });

  factory CashOverview.fromJson(Map<String, dynamic> json) => CashOverview(
        mode: json['mode'] as String? ?? 'FLEXIBLE',
        enabled: json['enabled'] as bool? ?? false,
        register: json['register'] is Map<String, dynamic>
            ? CashRegisterInfo.fromJson(
                json['register'] as Map<String, dynamic>)
            : null,
        session: json['session'] is Map<String, dynamic>
            ? CashSessionInfo.fromJson(json['session'] as Map<String, dynamic>)
            : null,
        registers: (json['registers'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(CashRegisterInfo.fromJson)
            .toList(growable: false),
      );

  final String mode;
  final bool enabled;
  final CashRegisterInfo? register;
  final CashSessionInfo? session;
  final List<CashRegisterInfo> registers;

  bool get isFixed => mode == 'FIXED';
  List<CashRegisterInfo> get openRegisters =>
      registers.where((item) => item.session != null).toList(growable: false);
}

class CashSessionSummary {
  const CashSessionSummary({
    required this.status,
    required this.openingAmount,
    required this.manualEntries,
    required this.withdrawals,
    required this.cashPayments,
    required this.expectedAmount,
  });

  factory CashSessionSummary.fromJson(Map<String, dynamic> json) =>
      CashSessionSummary(
        status: json['status'] as String? ?? 'open',
        openingAmount: json['opening_amount'] as String? ?? '0.00',
        manualEntries: json['manual_entries'] as String? ?? '0.00',
        withdrawals: json['withdrawals'] as String? ?? '0.00',
        cashPayments: json['cash_payments'] as String? ?? '0.00',
        expectedAmount: json['expected_amount'] as String? ?? '0.00',
      );

  final String status;
  final String openingAmount;
  final String manualEntries;
  final String withdrawals;
  final String cashPayments;
  final String expectedAmount;
}

class CashBeneficiary {
  const CashBeneficiary(
      {required this.id, required this.name, required this.userType});

  factory CashBeneficiary.fromJson(Map<String, dynamic> json) =>
      CashBeneficiary(
        id: json['id'] as int,
        name: json['name'] as String? ?? '',
        userType: json['user_type'] as String? ?? '',
      );

  final int id;
  final String name;
  final String userType;
}

const withdrawalCategories = {
  'dj': 'DJ',
  'artist': 'Pagode / Artista',
  'advance': 'Vale / Adiantamento',
  'promoter': 'Promoter',
  'supplier': 'Fornecedor',
  'other': 'Outros',
};

bool withdrawalRequiresBeneficiary(String category) =>
    const {'dj', 'artist', 'advance', 'promoter'}.contains(category);

String formatMoney(String? value) =>
    'R\$ ${(value ?? '0.00').replaceAll('.', ',')}';

String createIdempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  final hex =
      bytes.map((byte) => byte.toRadixString(16).padLeft(2, '0')).join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}
