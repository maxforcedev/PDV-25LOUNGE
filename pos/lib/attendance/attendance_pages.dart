import 'dart:async';

import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../sales/sale_models.dart';
import 'attendance_models.dart';

bool _can(AppController controller, String permission) =>
    controller.bootstrapSnapshot?.permissions.contains(permission) == true;

class TablesPage extends StatefulWidget {
  const TablesPage({required this.controller, super.key});
  final AppController controller;
  @override
  State<TablesPage> createState() => _TablesPageState();
}

class _TablesPageState extends State<TablesPage> {
  List<AttendanceTable> _tables = const [];
  bool _loading = true;
  final Set<int> _groupSelection = {};

  bool get _canGroup => _can(widget.controller, 'tables.merge');

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final tables = await widget.controller.attendanceTables();
    if (mounted) {
      setState(() {
        _tables = tables ?? const [];
        _loading = false;
      });
    }
  }

  Future<void> _open(AttendanceTable table) async {
    if (table.isOpen &&
        table.commands.length == 1 &&
        table.commands.single.isPrimary) {
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => CommandDetailPage(
              controller: widget.controller, command: table.commands.single)));
      if (mounted) await _load();
      return;
    }
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) =>
          TableDetailPage(controller: widget.controller, table: table),
    ));
    if (mounted) await _load();
  }

  Future<void> _groupSelected() async {
    if (_groupSelection.length < 2) return;
    final grouped = await widget.controller.groupAttendanceTables(
      tableIds: _groupSelection.toList(),
      idempotencyKey: createIdempotencyKey(),
    );
    if (!mounted || !grouped) return;
    setState(_groupSelection.clear);
    await _load();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
            title: Text(_groupSelection.isEmpty
                ? 'Mesas'
                : '${_groupSelection.length} selecionada(s)'),
            actions: [
              if (_groupSelection.length >= 2)
                IconButton(
                    onPressed: _groupSelected,
                    tooltip: 'Agrupar mesas',
                    icon: const Icon(Icons.merge_type)),
              if (_groupSelection.isNotEmpty)
                IconButton(
                    onPressed: () => setState(_groupSelection.clear),
                    tooltip: 'Cancelar seleção',
                    icon: const Icon(Icons.close)),
              IconButton(
                  onPressed: _loading ? null : _load,
                  icon: const Icon(Icons.refresh)),
            ]),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _load,
                child: GridView.builder(
                  padding: const EdgeInsets.all(16),
                  gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                    maxCrossAxisExtent: 230,
                    mainAxisSpacing: 12,
                    crossAxisSpacing: 12,
                    childAspectRatio: 1.2,
                  ),
                  itemCount: _tables.length,
                  itemBuilder: (_, index) {
                    final table = _tables[index];
                    final locked = table.legacyOccupied;
                    final color = locked
                        ? Colors.orange
                        : table.isOpen
                            ? Colors.red
                            : Colors.green;
                    return Card(
                      child: InkWell(
                        borderRadius: BorderRadius.circular(12),
                        onTap: locked
                            ? null
                            : _groupSelection.isNotEmpty
                                ? () => setState(() =>
                                    _groupSelection.contains(table.id)
                                        ? _groupSelection.remove(table.id)
                                        : _groupSelection.add(table.id))
                                : () => _open(table),
                        onLongPress: _canGroup && !locked
                            ? () => setState(() =>
                                _groupSelection.contains(table.id)
                                    ? _groupSelection.remove(table.id)
                                    : _groupSelection.add(table.id))
                            : null,
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(table.name,
                                    style: Theme.of(context)
                                        .textTheme
                                        .titleLarge
                                        ?.copyWith(
                                            fontWeight: FontWeight.w800)),
                                const Spacer(),
                                Text(
                                    locked
                                        ? 'ATENDIMENTO LEGADO'
                                        : table.isOpen
                                            ? 'OCUPADA'
                                            : 'LIVRE',
                                    style: TextStyle(
                                        color: color.shade700,
                                        fontWeight: FontWeight.w700)),
                                if (table.capacity > 0)
                                  Text('${table.capacity} lugares'),
                                if (table.isOpen)
                                  Text('Saldo: ${formatMoney(table.balance)}'),
                                if (table.billRequested)
                                  const Text('CONTA SOLICITADA',
                                      style: TextStyle(
                                          fontWeight: FontWeight.w700,
                                          color: Colors.deepOrange)),
                                if (table.group != null)
                                  Text(
                                      'Grupo: ${table.group!.tableNames.join(', ')}'),
                                if (_groupSelection.contains(table.id))
                                  const Align(
                                      alignment: Alignment.centerRight,
                                      child: Icon(Icons.check_circle,
                                          color: Colors.blue)),
                              ]),
                        ),
                      ),
                    );
                  },
                ),
              ),
      );
}

class TableDetailPage extends StatefulWidget {
  const TableDetailPage(
      {required this.controller, required this.table, super.key});
  final AppController controller;
  final AttendanceTable table;
  @override
  State<TableDetailPage> createState() => _TableDetailPageState();
}

class _TableDetailPageState extends State<TableDetailPage> {
  late AttendanceTable _table = widget.table;
  int? _selectedCommandId;
  bool _loading = false;
  bool get _canOpen => _can(widget.controller, 'tables.open');
  bool get _canCommand => _can(widget.controller, 'commands.open');
  bool get _canGroup => _can(widget.controller, 'tables.merge');

  @override
  void initState() {
    super.initState();
    if (_table.commands.length == 1 && _table.commands.single.isPrimary) {
      _selectedCommandId = _table.commands.single.id;
    }
    if (_table.isOpen) unawaited(_load());
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final tables = await widget.controller.attendanceTables();
    if (!mounted) return;
    setState(() {
      _table =
          tables?.where((table) => table.id == _table.id).firstOrNull ?? _table;
      _loading = false;
    });
  }

  Future<void> _open({bool additional = false}) async {
    final details = await showDialog<_OpenDetails>(
        context: context,
        builder: (_) => _OpenCommandDialog(
            title: additional ? 'Nova comanda' : 'Abrir mesa'));
    if (details == null) return;
    final command = additional
        ? await widget.controller.openAttendanceCommand(
            idempotencyKey: createIdempotencyKey(),
            tableId: _table.id,
            identifier: details.identifier,
            peopleCount: details.peopleCount,
            notes: details.notes)
        : await widget.controller.openAttendanceTable(
            tableId: _table.id,
            idempotencyKey: createIdempotencyKey(),
            identifier: details.identifier,
            peopleCount: details.peopleCount,
            notes: details.notes);
    if (command == null || !mounted) return;
    await _load();
    if (mounted) await _command(command);
  }

  Future<void> _command(AttendanceCommand command) async {
    await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => CommandDetailPage(
            controller: widget.controller, command: command)));
    if (mounted) await _load();
  }

  Future<void> _separate() async {
    final separated = await widget.controller.separateAttendanceTable(
      tableId: _table.id,
      idempotencyKey: createIdempotencyKey(),
    );
    if (separated && mounted) await _load();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(_table.name), actions: [
          IconButton(
              onPressed: _loading ? null : _load,
              icon: const Icon(Icons.refresh))
        ]),
        floatingActionButton: _table.isOpen && _canCommand
            ? FloatingActionButton.extended(
                onPressed: () => _open(additional: true),
                icon: const Icon(Icons.add),
                label: const Text('COMANDA'))
            : null,
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(padding: const EdgeInsets.all(16), children: [
                _SummaryCard(summary: {
                  'total_due': _table.total,
                  'remaining_balance': _table.balance
                }),
                const SizedBox(height: 16),
                if (!_table.isOpen)
                  FilledButton.icon(
                      onPressed: _canOpen ? _open : null,
                      icon: const Icon(Icons.play_arrow),
                      label: const Text('ABRIR MESA')),
                if (_table.isOpen) ...[
                  if (_table.group != null) ...[
                    Card(
                        child: ListTile(
                      leading: const Icon(Icons.group_work_outlined),
                      title: const Text('Mesas agrupadas'),
                      subtitle: Text(_table.group!.tableNames.join(', ')),
                      trailing: _canGroup
                          ? TextButton(
                              onPressed: _separate,
                              child: const Text('SEPARAR'))
                          : null,
                    )),
                    const SizedBox(height: 8),
                  ],
                  Text('Comandas',
                      style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  ..._table.commands.map((command) => Card(
                          child: ListTile(
                        selected: command.id == _selectedCommandId,
                        leading: Icon(command.isPrimary
                            ? Icons.star
                            : Icons.receipt_long_outlined),
                        title: Text(command.label),
                        subtitle: Text(command.isPrimary
                            ? 'Comanda principal'
                            : command.number),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () {
                          setState(() => _selectedCommandId = command.id);
                          _command(command);
                        },
                      ))),
                ],
              ]),
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
    final commands =
        await widget.controller.attendanceCommands(query: _search.text);
    if (mounted) {
      setState(() {
        _commands = commands ?? const [];
        _loading = false;
      });
    }
  }

  Future<void> _open() async {
    final details = await showDialog<_OpenDetails>(
        context: context,
        builder: (_) => const _OpenCommandDialog(title: 'Nova comanda'));
    if (details == null) return;
    final command = await widget.controller.openAttendanceCommand(
        idempotencyKey: createIdempotencyKey(),
        identifier: details.identifier,
        peopleCount: details.peopleCount,
        notes: details.notes);
    if (command != null && mounted) {
      await Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => CommandDetailPage(
              controller: widget.controller, command: command)));
      if (mounted) await _load();
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Comandas'), actions: [
          IconButton(
              onPressed: _loading ? null : _load,
              icon: const Icon(Icons.refresh))
        ]),
        floatingActionButton: _can(widget.controller, 'commands.open')
            ? FloatingActionButton.extended(
                onPressed: _open,
                icon: const Icon(Icons.add),
                label: const Text('NOVA COMANDA'))
            : null,
        body: Column(children: [
          Padding(
              padding: const EdgeInsets.all(16),
              child: TextField(
                  controller: _search,
                  onSubmitted: (_) => unawaited(_load()),
                  decoration: const InputDecoration(
                      labelText: 'Número ou identificador',
                      prefixIcon: Icon(Icons.search)))),
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
                          subtitle: Text(command.tableName.isEmpty
                              ? 'Sem mesa'
                              : command.tableName),
                          trailing: Text(
                              command.status == 'open' ? 'ABERTA' : 'FECHADA'),
                          onTap: () => Navigator.of(context).push(
                              MaterialPageRoute(
                                  builder: (_) => CommandDetailPage(
                                      controller: widget.controller,
                                      command: command))),
                        );
                      },
                    )),
        ]),
      );
}

class CommandDetailPage extends StatefulWidget {
  const CommandDetailPage(
      {required this.controller, required this.command, super.key});
  final AppController controller;
  final AttendanceCommand command;
  @override
  State<CommandDetailPage> createState() => _CommandDetailPageState();
}

class _CommandDetailPageState extends State<CommandDetailPage> {
  AttendanceCommandDetail? _detail;
  AttendanceLedger? _ledger;
  bool _loading = true;
  final Set<int> _selectedItems = {};
  bool get _open => _detail?.command.status == 'open';
  bool _allowed(String permission) =>
      _open && _can(widget.controller, permission);

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final results = await Future.wait([
      widget.controller.attendanceCommandDetail(widget.command.id),
      widget.controller.attendanceLedger(widget.command.id)
    ]);
    if (mounted) {
      setState(() {
        _detail = results[0] as AttendanceCommandDetail?;
        _ledger = results[1] as AttendanceLedger?;
        _selectedItems.removeWhere(
            (id) => !(_detail?.items.any((item) => item.id == id) ?? false));
        _loading = false;
      });
    }
  }

  Future<void> _addProduct() async {
    final catalog = await widget.controller.attendanceCatalog();
    if (!mounted || catalog == null) return;
    final item = await showDialog<_NewItem>(
        context: context, builder: (_) => _ProductDialog(products: catalog));
    if (item == null) return;
    final created = await widget.controller.addAttendanceItems(
        commandId: widget.command.id,
        items: [item.toJson()],
        idempotencyKey: createIdempotencyKey());
    if (created == null) return;
    for (final order in created) {
      await widget.controller.confirmAttendanceItem(
          itemId: order.id, idempotencyKey: createIdempotencyKey());
    }
    if (mounted) await _load();
  }

  Future<void> _cancel(AttendanceOrderItem item) async {
    final reason = await _reasonDialog(context, 'Cancelar item');
    if (reason == null) return;
    await widget.controller.cancelAttendanceItem(
        itemId: item.id,
        idempotencyKey: createIdempotencyKey(),
        reason: reason);
    if (mounted) await _load();
  }

  Future<void> _payment() async {
    final options = await widget.controller.attendanceCheckoutOptions();
    if (!mounted || options == null) return;
    final payment = await showDialog<_PaymentInput>(
        context: context,
        builder: (_) => _PaymentDialog(
            options: options,
            balance: '${_ledger?.summary['remaining_balance'] ?? '0.00'}'));
    if (payment == null) return;
    await widget.controller.recordAttendancePayment(
        commandId: widget.command.id,
        paymentMethodId: payment.method.id,
        amount: payment.amount,
        receivedAmount: payment.received,
        cashSessionId: payment.session?.id,
        idempotencyKey: createIdempotencyKey());
    if (mounted) await _load();
  }

  Future<void> _reverse(AttendancePayment payment) async {
    final reason = await _reasonDialog(context, 'Estornar pagamento');
    if (reason == null) return;
    await widget.controller.reverseAttendancePayment(
        paymentId: payment.id,
        idempotencyKey: createIdempotencyKey(),
        reason: reason);
    if (mounted) await _load();
  }

  Future<void> _finalize() async {
    final options = await widget.controller.attendanceCheckoutOptions();
    if (!mounted || options == null) return;
    final session = await _pickSession(context, options);
    if (session == null) return;
    await widget.controller.finalizeAttendanceCommand(
        commandId: widget.command.id,
        cashSessionId: session.id,
        idempotencyKey: createIdempotencyKey());
    if (mounted) await _load();
  }

  Future<void> _bill() async {
    final requested = _detail?.command.billRequested != true;
    await widget.controller.setAttendanceBillRequested(
      commandId: widget.command.id,
      requested: requested,
      idempotencyKey: createIdempotencyKey(),
    );
    if (mounted) await _load();
  }

  Future<void> _transfer() async {
    final tables = await widget.controller.attendanceTables();
    if (!mounted || tables == null) return;
    final target = await showDialog<_TableTarget>(
        context: context, builder: (_) => _TablePicker(tables: tables));
    if (target == null) return;
    await widget.controller.transferAttendanceCommand(
        commandId: widget.command.id,
        tableId: target.table?.id,
        idempotencyKey: createIdempotencyKey());
    if (mounted) await _load();
  }

  Future<void> _transferItems() async {
    if (_selectedItems.isEmpty) return;
    final commands = await widget.controller.attendanceCommands();
    if (!mounted || commands == null) return;
    final target = await showDialog<AttendanceCommand>(
        context: context,
        builder: (_) => _CommandPicker(
            commands: commands
                .where((command) => command.id != widget.command.id)
                .toList()));
    if (target == null) return;
    final items = _detail!.items
        .where((item) => _selectedItems.contains(item.id))
        .map((item) => {'item': item.id, 'quantity': item.quantity})
        .toList();
    await widget.controller.transferAttendanceItems(
        commandId: widget.command.id,
        destinationCommandId: target.id,
        items: items,
        idempotencyKey: createIdempotencyKey());
    if (mounted) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    return Scaffold(
      appBar: AppBar(
          title: Text(detail?.command.label ?? widget.command.label),
          actions: [
            IconButton(
                onPressed: _loading ? null : _load,
                icon: const Icon(Icons.refresh))
          ]),
      floatingActionButton: _allowed('commands.add_items')
          ? FloatingActionButton.extended(
              onPressed: _addProduct,
              icon: const Icon(Icons.add_shopping_cart),
              label: const Text('ADICIONAR'))
          : null,
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : detail == null
              ? const Center(
                  child: Text('Não foi possível carregar a comanda.'))
              : ListView(padding: const EdgeInsets.all(16), children: [
                  _SummaryCard(summary: detail.summary),
                  const SizedBox(height: 12),
                  if (detail.command.notes.isNotEmpty)
                    Text('Obs.: ${detail.command.notes}'),
                  if (detail.command.billRequested)
                    const Padding(
                        padding: EdgeInsets.only(top: 8),
                        child: Text('CONTA SOLICITADA',
                            style: TextStyle(
                                color: Colors.deepOrange,
                                fontWeight: FontWeight.w800))),
                  const SizedBox(height: 16),
                  Text('Itens', style: Theme.of(context).textTheme.titleMedium),
                  ...detail.items.map((item) => Card(
                          child: ListTile(
                        leading: _allowed('commands.transfer_items') &&
                                item.status == 'confirmed'
                            ? Checkbox(
                                value: _selectedItems.contains(item.id),
                                onChanged: (value) => setState(() =>
                                    value == true
                                        ? _selectedItems.add(item.id)
                                        : _selectedItems.remove(item.id)))
                            : null,
                        title: Text('${item.quantity} x ${item.productName}'),
                        subtitle: Text(
                            '${formatMoney(item.unitPrice)}${item.notes.isEmpty ? '' : '  ${item.notes}'}'),
                        trailing: item.status == 'confirmed' &&
                                _allowed('commands.cancel_items')
                            ? IconButton(
                                icon: const Icon(Icons.cancel_outlined),
                                onPressed: () => _cancel(item))
                            : Text(item.status.toUpperCase()),
                      ))),
                  if (_selectedItems.isNotEmpty)
                    OutlinedButton.icon(
                        onPressed: _transferItems,
                        icon: const Icon(Icons.drive_file_move_outline),
                        label: const Text('TRANSFERIR ITENS')),
                  const SizedBox(height: 16),
                  _LedgerCard(
                      ledger: _ledger,
                      canReverse: _allowed('commands.payments.reverse'),
                      onReverse: _reverse),
                  if (_allowed('commands.payments.record'))
                    FilledButton.icon(
                        onPressed: _payment,
                        icon: const Icon(Icons.payments_outlined),
                        label: const Text('REGISTRAR PAGAMENTO')),
                  if (_allowed('commands.finalize'))
                    OutlinedButton.icon(
                        onPressed: _bill,
                        icon: Icon(detail.command.billRequested
                            ? Icons.remove_done_outlined
                            : Icons.request_quote_outlined),
                        label: Text(detail.command.billRequested
                            ? 'RESOLVER SOLICITAÇÃO DE CONTA'
                            : 'SOLICITAR CONTA')),
                  if (_allowed('commands.finalize'))
                    FilledButton.icon(
                        onPressed: _finalize,
                        icon: const Icon(Icons.task_alt),
                        label: const Text('FINALIZAR COMANDA')),
                  if (_allowed('commands.transfer'))
                    OutlinedButton.icon(
                        onPressed: _transfer,
                        icon: const Icon(Icons.swap_horiz),
                        label: const Text('TRANSFERIR COMANDA')),
                ]),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.summary});
  final Map<String, dynamic> summary;
  @override
  Widget build(BuildContext context) => Card(
      child: Padding(
          padding: const EdgeInsets.all(16),
          child: Wrap(spacing: 24, runSpacing: 8, children: [
            Text(
                'Total: ${formatMoney('${summary['total_due'] ?? summary['total'] ?? '0.00'}')}',
                style: const TextStyle(fontWeight: FontWeight.w700)),
            Text(
                'Saldo: ${formatMoney('${summary['remaining_balance'] ?? summary['balance'] ?? '0.00'}')}',
                style: const TextStyle(fontWeight: FontWeight.w700)),
            if (summary.containsKey('paid_total'))
              Text('Pago: ${formatMoney('${summary['paid_total']}')}'),
          ])));
}

class _LedgerCard extends StatelessWidget {
  const _LedgerCard(
      {required this.ledger,
      required this.canReverse,
      required this.onReverse});
  final AttendanceLedger? ledger;
  final bool canReverse;
  final ValueChanged<AttendancePayment> onReverse;
  @override
  Widget build(BuildContext context) => Card(
      child: Padding(
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Pagamentos', style: Theme.of(context).textTheme.titleMedium),
            _SummaryCard(summary: ledger?.summary ?? const {}),
            ...?ledger?.payments.map((payment) => ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(payment.paymentMethodName),
                subtitle: Text(
                    'Recebido ${formatMoney(payment.receivedAmount)} | Troco ${formatMoney(payment.changeAmount)}'),
                trailing: canReverse && payment.status == 'applied'
                    ? IconButton(
                        onPressed: () => onReverse(payment),
                        icon: const Icon(Icons.undo))
                    : Text(formatMoney(payment.amount)))),
          ])));
}

class _OpenDetails {
  const _OpenDetails(this.identifier, this.peopleCount, this.notes);
  final String identifier;
  final int? peopleCount;
  final String notes;
}

class _OpenCommandDialog extends StatefulWidget {
  const _OpenCommandDialog({required this.title});
  final String title;
  @override
  State<_OpenCommandDialog> createState() => _OpenCommandDialogState();
}

class _OpenCommandDialogState extends State<_OpenCommandDialog> {
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
          title: Text(widget.title),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(
                controller: _identifier,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'Identificador')),
            TextField(
                controller: _people,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Pessoas')),
            TextField(
                controller: _notes,
                decoration: const InputDecoration(labelText: 'Observação'))
          ]),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('CANCELAR')),
            FilledButton(
                onPressed: () => Navigator.pop(
                    context,
                    _OpenDetails(_identifier.text.trim(),
                        int.tryParse(_people.text), _notes.text.trim())),
                child: const Text('CONFIRMAR'))
          ]);
}

class _NewItem {
  const _NewItem(this.product, this.modifiers, this.notes);
  final QuickSaleProduct product;
  final List<Map<String, dynamic>> modifiers;
  final String notes;
  Map<String, dynamic> toJson() => {
        'product': product.id,
        'quantity': '1',
        'modifiers': modifiers,
        'notes': notes
      };
}

class _ProductDialog extends StatefulWidget {
  const _ProductDialog({required this.products});
  final List<QuickSaleProduct> products;
  @override
  State<_ProductDialog> createState() => _ProductDialogState();
}

class _ProductDialogState extends State<_ProductDialog> {
  QuickSaleProduct? _product;
  final _notes = TextEditingController();
  final Set<int> _options = {};

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  void _save() {
    final product = _product;
    if (product == null) return;
    for (final group in product.modifierGroups) {
      if ((group.required || group.minSelections > 0) &&
          !group.options.any((option) => _options.contains(option.id))) {
        return;
      }
    }
    Navigator.pop(
        context,
        _NewItem(
            product,
            _options.map((id) => {'option': id, 'quantity': '1'}).toList(),
            _notes.text.trim()));
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Adicionar produto'),
        content: SizedBox(
          width: 420,
          child: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              DropdownButtonFormField<QuickSaleProduct>(
                value: _product,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Produto'),
                items: widget.products
                    .where((product) => product.canSell)
                    .map((product) => DropdownMenuItem(
                        value: product, child: Text(product.name)))
                    .toList(),
                onChanged: (product) => setState(() {
                  _product = product;
                  _options.clear();
                }),
              ),
              if (_product != null)
                ..._product!.modifierGroups.map(
                  (group) => Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: Text(group.name,
                                style: const TextStyle(
                                    fontWeight: FontWeight.bold))),
                        ...group.options.map((option) => CheckboxListTile(
                              contentPadding: EdgeInsets.zero,
                              value: _options.contains(option.id),
                              title: Text(
                                  '${option.name} (+${formatMoney(option.additionalPrice)})'),
                              onChanged: (value) => setState(() => value == true
                                  ? _options.add(option.id)
                                  : _options.remove(option.id)),
                            )),
                      ]),
                ),
              TextField(
                  controller: _notes,
                  decoration: const InputDecoration(labelText: 'Observação')),
            ]),
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('CANCELAR')),
          FilledButton(onPressed: _save, child: const Text('ADICIONAR')),
        ],
      );
}

class _PaymentInput {
  const _PaymentInput(this.method, this.amount, this.received, this.session);
  final QuickSalePaymentMethod method;
  final String amount;
  final String? received;
  final QuickSaleCashSession? session;
}

class _PaymentDialog extends StatefulWidget {
  const _PaymentDialog({required this.options, required this.balance});
  final QuickSaleCheckoutOptions options;
  final String balance;
  @override
  State<_PaymentDialog> createState() => _PaymentDialogState();
}

class _PaymentDialogState extends State<_PaymentDialog> {
  late final _amount = TextEditingController(text: widget.balance);
  final _received = TextEditingController();
  QuickSalePaymentMethod? _method;
  QuickSaleCashSession? _session;
  @override
  void initState() {
    super.initState();
    _method = widget.options.paymentMethods.firstOrNull;
    _session = widget.options.cashSessions.firstOrNull;
  }

  @override
  void dispose() {
    _amount.dispose();
    _received.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
          title: const Text('Registrar pagamento'),
          content: Column(mainAxisSize: MainAxisSize.min, children: [
            DropdownButtonFormField<QuickSalePaymentMethod>(
                value: _method,
                items: widget.options.paymentMethods
                    .map((item) =>
                        DropdownMenuItem(value: item, child: Text(item.name)))
                    .toList(),
                onChanged: (value) => setState(() => _method = value),
                decoration:
                    const InputDecoration(labelText: 'Forma de pagamento')),
            TextField(
                controller: _amount,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Valor')),
            if (_method?.code == 'cash')
              TextField(
                  controller: _received,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(labelText: 'Recebido')),
            if (widget.options.cashSessions.isNotEmpty)
              DropdownButtonFormField<QuickSaleCashSession>(
                  value: _session,
                  items: widget.options.cashSessions
                      .map((item) => DropdownMenuItem(
                          value: item, child: Text(item.registerName)))
                      .toList(),
                  onChanged: (value) => setState(() => _session = value),
                  decoration: const InputDecoration(labelText: 'Caixa'))
          ]),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('CANCELAR')),
            FilledButton(
                onPressed: _method == null
                    ? null
                    : () => Navigator.pop(
                        context,
                        _PaymentInput(
                            _method!,
                            _amount.text.trim(),
                            _received.text.trim().isEmpty
                                ? null
                                : _received.text.trim(),
                            _session)),
                child: const Text('REGISTRAR'))
          ]);
}

class _TableTarget {
  const _TableTarget(this.table);
  final AttendanceTable? table;
}

class _TablePicker extends StatelessWidget {
  const _TablePicker({required this.tables});
  final List<AttendanceTable> tables;
  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Transferir comanda'),
        content: SizedBox(
            width: 360,
            child: ListView(shrinkWrap: true, children: [
              ListTile(
                  leading: const Icon(Icons.person_outline),
                  title: const Text('Sem mesa'),
                  onTap: () =>
                      Navigator.pop(context, const _TableTarget(null))),
              ...tables
                  .where((table) => table.isOpen && !table.legacyOccupied)
                  .map((table) => ListTile(
                      title: Text(table.name),
                      subtitle: Text(table.isOpen ? 'Ocupada' : 'Livre'),
                      onTap: () =>
                          Navigator.pop(context, _TableTarget(table)))),
            ])),
      );
}

class _CommandPicker extends StatelessWidget {
  const _CommandPicker({required this.commands});
  final List<AttendanceCommand> commands;
  @override
  Widget build(BuildContext context) => AlertDialog(
      title: const Text('Destino dos itens'),
      content: SizedBox(
          width: 360,
          child: ListView(
              shrinkWrap: true,
              children: commands
                  .map((command) => ListTile(
                      title: Text(command.label),
                      subtitle: Text(command.tableName),
                      onTap: () => Navigator.pop(context, command)))
                  .toList())));
}

Future<String?> _reasonDialog(BuildContext context, String title) async {
  final controller = TextEditingController();
  final result = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
              title: Text(title),
              content: TextField(
                  controller: controller,
                  decoration: const InputDecoration(labelText: 'Motivo')),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('CANCELAR')),
                FilledButton(
                    onPressed: () =>
                        Navigator.pop(context, controller.text.trim()),
                    child: const Text('CONFIRMAR'))
              ]));
  controller.dispose();
  return result;
}

Future<QuickSaleCashSession?> _pickSession(
    BuildContext context, QuickSaleCheckoutOptions options) async {
  if (options.cashSessions.length == 1) return options.cashSessions.single;
  return showDialog<QuickSaleCashSession>(
      context: context,
      builder: (_) => AlertDialog(
          title: const Text('Selecione o caixa'),
          content: ListView(
              shrinkWrap: true,
              children: options.cashSessions
                  .map((session) => ListTile(
                      title: Text(session.registerName),
                      onTap: () => Navigator.pop(context, session)))
                  .toList())));
}
