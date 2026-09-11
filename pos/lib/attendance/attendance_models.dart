class AttendanceTable {
  const AttendanceTable({
    required this.id,
    required this.name,
    required this.capacity,
    required this.status,
    required this.total,
    required this.balance,
    this.legacyOccupied = false,
    this.billRequested = false,
    this.group,
    this.commands = const [],
  });

  factory AttendanceTable.fromJson(Map<String, dynamic> json) =>
      AttendanceTable(
        id: json['id'] as int,
        name: json['name'] as String? ?? '',
        capacity: json['capacity'] as int? ?? 0,
        status: json['status'] as String? ?? 'free',
        total: json['total'] as String? ?? '0.00',
        balance: json['balance'] as String? ?? '0.00',
        legacyOccupied: json['legacy_occupied'] == true,
        billRequested: json['bill_requested'] == true,
        group: json['group'] is Map<String, dynamic>
            ? AttendanceTableGroup.fromJson(
                json['group'] as Map<String, dynamic>)
            : null,
        commands: (json['commands'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(AttendanceCommand.fromJson)
            .toList(growable: false),
      );

  final int id;
  final String name;
  final int capacity;
  final String status;
  final String total;
  final String balance;
  final bool legacyOccupied;
  final bool billRequested;
  final AttendanceTableGroup? group;
  final List<AttendanceCommand> commands;

  bool get isOpen => status == 'occupied';
}

class AttendanceTableGroup {
  const AttendanceTableGroup({
    required this.id,
    required this.tableIds,
    required this.tableNames,
  });

  factory AttendanceTableGroup.fromJson(Map<String, dynamic> json) =>
      AttendanceTableGroup(
        id: json['id'] as int,
        tableIds: (json['table_ids'] as List<dynamic>? ?? const []).cast<int>(),
        tableNames:
            (json['table_names'] as List<dynamic>? ?? const []).cast<String>(),
      );

  final int id;
  final List<int> tableIds;
  final List<String> tableNames;
}

class AttendanceCommand {
  const AttendanceCommand({
    required this.id,
    required this.number,
    required this.status,
    this.identifier = '',
    this.tableId,
    this.tableName = '',
    this.customerId,
    this.isPrimary = false,
    this.peopleCount,
    this.notes = '',
    this.summary = const {},
    this.billRequestedAt,
  });

  factory AttendanceCommand.fromJson(Map<String, dynamic> json) =>
      AttendanceCommand(
        id: json['id'] as int,
        number: json['number'] as String? ?? '',
        status: json['status'] as String? ?? 'open',
        identifier: json['identifier'] as String? ?? '',
        tableId: json['table'] as int?,
        tableName: json['table_name'] as String? ?? '',
        customerId: json['customer'] as int?,
        isPrimary: json['is_primary'] == true,
        peopleCount: json['people_count'] as int?,
        notes: json['notes'] as String? ?? '',
        summary: json['summary'] as Map<String, dynamic>? ?? const {},
        billRequestedAt: json['bill_requested_at'] as String?,
      );

  final int id;
  final String number;
  final String status;
  final String identifier;
  final int? tableId;
  final String tableName;
  final int? customerId;
  final bool isPrimary;
  final int? peopleCount;
  final String notes;
  final Map<String, dynamic> summary;
  final String? billRequestedAt;

  bool get billRequested => billRequestedAt != null;

  String get label => identifier.isEmpty ? number : identifier;
}

class AttendanceCommandDetail {
  const AttendanceCommandDetail({
    required this.command,
    required this.items,
    required this.summary,
  });

  factory AttendanceCommandDetail.fromJson(Map<String, dynamic> json) =>
      AttendanceCommandDetail(
        command: AttendanceCommand.fromJson(json),
        items: (json['orders'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(AttendanceOrderItem.fromJson)
            .toList(growable: false),
        summary: json['summary'] as Map<String, dynamic>? ?? const {},
      );

  final AttendanceCommand command;
  final List<AttendanceOrderItem> items;
  final Map<String, dynamic> summary;
}

class AttendanceOrderItem {
  const AttendanceOrderItem({
    required this.id,
    required this.productId,
    required this.productName,
    required this.quantity,
    required this.unitPrice,
    required this.status,
    this.notes = '',
    this.modifiers = const [],
  });

  factory AttendanceOrderItem.fromJson(Map<String, dynamic> json) =>
      AttendanceOrderItem(
        id: json['id'] as int,
        productId: (json['product'] ?? json['product_id']) as int? ?? 0,
        productName: json['product_name'] as String? ?? '',
        quantity: '${json['quantity'] ?? '0'}',
        unitPrice: '${json['unit_price'] ?? '0.00'}',
        status: json['status'] as String? ?? 'pending',
        notes: json['notes'] as String? ?? '',
        modifiers: (json['modifier_snapshot'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>(),
      );

  final int id;
  final int productId;
  final String productName;
  final String quantity;
  final String unitPrice;
  final String status;
  final String notes;
  final List<Map<String, dynamic>> modifiers;
}

class AttendancePayment {
  const AttendancePayment({
    required this.id,
    required this.amount,
    required this.status,
    this.paymentMethodName = '',
    this.paymentMethodCode = '',
    this.receivedAmount = '0.00',
    this.changeAmount = '0.00',
  });

  factory AttendancePayment.fromJson(Map<String, dynamic> json) =>
      AttendancePayment(
        id: json['id'] as int,
        amount: '${json['amount'] ?? '0.00'}',
        status: json['status'] as String? ?? 'applied',
        paymentMethodName: json['payment_method_name'] as String? ?? '',
        paymentMethodCode: json['payment_method_code'] as String? ?? '',
        receivedAmount: '${json['received_amount'] ?? '0.00'}',
        changeAmount: '${json['change_amount'] ?? '0.00'}',
      );

  final int id;
  final String amount;
  final String status;
  final String paymentMethodName;
  final String paymentMethodCode;
  final String receivedAmount;
  final String changeAmount;
}

class AttendanceLedger {
  const AttendanceLedger({required this.summary, required this.payments});

  factory AttendanceLedger.fromJson(Map<String, dynamic> json) =>
      AttendanceLedger(
        summary: json['summary'] as Map<String, dynamic>? ?? const {},
        payments: (json['payments'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>()
            .map(AttendancePayment.fromJson)
            .toList(growable: false),
      );

  final Map<String, dynamic> summary;
  final List<AttendancePayment> payments;
}
