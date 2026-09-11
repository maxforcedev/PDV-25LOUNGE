import 'dart:async';

import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import 'attendance_models.dart';

class TablesPage extends StatefulWidget {
  const TablesPage({required this.controller, super.key});

  final AppController controller;

  @override
  State<TablesPage> createState() => _TablesPageState();
}

class _TablesPageState extends State<TablesPage> {
  List<AttendanceTable> _tables = const [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final tables = await widget.controller.attendanceTables();
    if (!mounted) return;
    setState(() {
      _tables = tables ?? const [];
      _loading = false;
    });
  }

  Future<void> _open(AttendanceTable table) async {
    final details = await showDialog<_OpenDetails>(
      context: context,
      builder: (_) => const _OpenTableDialog(),
    );
    if (details == null) return;
    final command = await widget.controller.openAttendanceTable(
      tableId: table.id,
      idempotencyKey: createIdempotencyKey(),
      peopleCount: details.peopleCount,
      identifier: details.identifier,
      notes: details.notes,
    );
    if (command != null) unawaited(_load());
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Mesas'),
          actions: [IconButton(onPressed: _loading ? null : _load, icon: const Icon(Icons.refresh))],
        ),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _load,
                child: GridView.builder(
                  padding: const EdgeInsets.all(16),
                  gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                    maxCrossAxisExtent: 220,
                    mainAxisSpacing: 12,
                    crossAxisSpacing: 12,
                    childAspectRatio: 1.15,
                  ),
                  itemCount: _tables.length,
                  itemBuilder: (_, index) {
                    final table = _tables[index];
                    final locked = table.legacyOccupied;
                    return Card(
                      child: InkWell(
                        borderRadius: BorderRadius.circular(12),
                        onTap: table.isOpen || locked ? null : () => _open(table),
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(table.name, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
                              const Spacer(),
                              Text(locked ? 'ATENDIMENTO LEGADO' : table.isOpen ? 'OCUPADA' : 'LIVRE',
                                  style: TextStyle(color: locked ? Colors.orange.shade800 : table.isOpen ? Colors.red.shade700 : Colors.green.shade700, fontWeight: FontWeight.w700)),
                              if (table.capacity > 0) Text('${table.capacity} lugares'),
                              if (table.isOpen) Text('Saldo: R\$ ${table.balance}'),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
      );
}

class CommandsPage extends StatefulWidget {
  const CommandsPage({required this.controller, super.key});

  final AppController controller;

  @override
  State<CommandsPage> createState() => _CommandsPageState();
}

class _CommandsPageState extends State<CommandsPage> {
  final _search = TextEditingController();
  List<AttendanceCommand> _commands = const [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final commands = await widget.controller.attendanceCommands(query: _search.text);
    if (!mounted) return;
    setState(() {
      _commands = commands ?? const [];
      _loading = false;
    });
  }

  Future<void> _open() async {
    final identifier = await showDialog<String>(
      context: context,
      builder: (_) => const _OpenCommandDialog(),
    );
    if (identifier == null) return;
    final command = await widget.controller.openAttendanceCommand(identifier: identifier);
    if (command != null) unawaited(_load());
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Comandas'),
          actions: [IconButton(onPressed: _loading ? null : _load, icon: const Icon(Icons.refresh))],
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: _open,
          icon: const Icon(Icons.add),
          label: const Text('NOVA COMANDA'),
        ),
        body: Column(children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
              controller: _search,
              onSubmitted: (_) => unawaited(_load()),
              decoration: const InputDecoration(labelText: 'Número, nome ou cliente', prefixIcon: Icon(Icons.search)),
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : ListView.separated(
                    itemCount: _commands.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (_, index) {
                      final command = _commands[index];
                      return ListTile(
                        leading: const Icon(Icons.receipt_long_outlined),
                        title: Text(command.label),
                        subtitle: Text(command.tableName.isEmpty ? 'Sem mesa' : command.tableName),
                        trailing: Text(command.status == 'open' ? 'ABERTA' : 'FECHADA'),
                      );
                    },
                  ),
          ),
        ]),
      );
}

class _OpenDetails {
  const _OpenDetails(this.identifier, this.peopleCount, this.notes);
  final String identifier;
  final int? peopleCount;
  final String notes;
}

class _OpenTableDialog extends StatefulWidget {
  const _OpenTableDialog();
  @override
  State<_OpenTableDialog> createState() => _OpenTableDialogState();
}

class _OpenTableDialogState extends State<_OpenTableDialog> {
  final _identifier = TextEditingController();
  final _people = TextEditingController();
  final _notes = TextEditingController();

  @override
  void dispose() {
    _identifier.dispose();
    _people.dispose();
    _notes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Abrir mesa'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: _identifier, decoration: const InputDecoration(labelText: 'Responsável (opcional)')),
          TextField(controller: _people, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Pessoas (opcional)')),
          TextField(controller: _notes, decoration: const InputDecoration(labelText: 'Observação (opcional)')),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('CANCELAR')),
          FilledButton(onPressed: () => Navigator.pop(context, _OpenDetails(_identifier.text.trim(), int.tryParse(_people.text), _notes.text.trim())), child: const Text('ABRIR')),
        ],
      );
}

class _OpenCommandDialog extends StatefulWidget {
  const _OpenCommandDialog();
  @override
  State<_OpenCommandDialog> createState() => _OpenCommandDialogState();
}

class _OpenCommandDialogState extends State<_OpenCommandDialog> {
  final _identifier = TextEditingController();
  @override
  void dispose() {
    _identifier.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Nova comanda'),
        content: TextField(controller: _identifier, autofocus: true, decoration: const InputDecoration(labelText: 'Identificador (opcional)')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('CANCELAR')),
          FilledButton(onPressed: () => Navigator.pop(context, _identifier.text.trim()), child: const Text('ABRIR')),
        ],
      );
}
