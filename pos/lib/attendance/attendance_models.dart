class AttendanceTable {
  const AttendanceTable({
    required this.id,
    required this.name,
    required this.capacity,
    required this.status,
    required this.total,
    required this.balance,
    this.legacyOccupied = false,
    this.commands = const [],
  });

  factory AttendanceTable.fromJson(Map<String, dynamic> json) => AttendanceTable(
        id: json['id'] as int,
        name: json['name'] as String? ?? '',
        capacity: json['capacity'] as int? ?? 0,
        status: json['status'] as String? ?? 'free',
        total: json['total'] as String? ?? '0.00',
        balance: json['balance'] as String? ?? '0.00',
        legacyOccupied: json['legacy_occupied'] == true,
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
  final List<AttendanceCommand> commands;

  bool get isOpen => status == 'occupied';
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

  String get label => identifier.isEmpty ? number : identifier;
}
