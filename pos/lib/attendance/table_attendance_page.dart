import 'dart:async';

import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../core/transient_feedback.dart';
import '../sales/quick_sale_page.dart';
import '../sales/sale_models.dart';
import 'attendance_models.dart';

class TableAttendancePage extends StatefulWidget {
  const TableAttendancePage({
    required this.controller,
    required this.attendance,
    super.key,
  });

  final AppController controller;
  final TableAttendance attendance;

  @override
  State<TableAttendancePage> createState() => _TableAttendancePageState();
}

class _TableAttendancePageState extends State<TableAttendancePage> {
  late TableAttendance _attendance = widget.attendance;
  bool _loading = true;

  bool get _canAddItems =>
      widget.controller.bootstrapSnapshot?.permissions.contains('tables.add_items') == true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final detail = await widget.controller.tableAttendanceDetail(_attendance.id);
    if (!mounted) return;
    setState(() {
      _attendance = detail ?? _attendance;
      _loading = false;
    });
  }

  Future<void> _newOrder() async {
    final saved = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => TableOrderPage(
        controller: widget.controller,
        attendance: _attendance,
      ),
    ));
    if (saved == true && mounted) await _load();
  }

  String _summary(String key) => '${_attendance.summary[key] ?? '0.00'}';

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: Text(_attendance.tableName.isEmpty
              ? 'Mesa'
              : _attendance.tableName),
          actions: [
            IconButton(
              onPressed: _loading ? null : _load,
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        floatingActionButton: _attendance.status == 'open' && _canAddItems
            ? FloatingActionButton.extended(
                onPressed: _newOrder,
                icon: const Icon(Icons.add),
                label: const Text('NOVO PEDIDO'),
              )
            : null,
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _load,
                child: ListView(padding: const EdgeInsets.all(16), children: [
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(_attendance.status == 'open' ? 'ABERTA' : 'FECHADA',
                              style: const TextStyle(fontWeight: FontWeight.w800)),
                          if (_attendance.peopleCount != null)
                            Text('${_attendance.peopleCount} pessoa(s)'),
                          if (_attendance.responsibleName.isNotEmpty)
                            Text('Responsável: ${_attendance.responsibleName}'),
                          if (_attendance.billRequested)
                            const Padding(
                              padding: EdgeInsets.only(top: 8),
                              child: Text('CONTA SOLICITADA',
                                  style: TextStyle(
                                      color: Colors.deepOrange,
                                      fontWeight: FontWeight.w800)),
                            ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text('Pedidos', style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 8),
                  if (_attendance.orders.isEmpty)
                    const Card(child: ListTile(title: Text('Nenhum pedido enviado.'))),
                  for (final order in _attendance.orders)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Pedido #${order.id}',
                                style: const TextStyle(fontWeight: FontWeight.w800)),
                            const SizedBox(height: 6),
                            for (final item in order.items)
                              Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text('${item.quantity}x ${item.productName}'),
                                    Text('${formatMoney(item.unitPrice)} · ${item.status}',
                                        style: Theme.of(context).textTheme.bodySmall),
                                    if (item.notes.isNotEmpty)
                                      Text(item.notes,
                                          style: Theme.of(context).textTheme.bodySmall),
                                    if (item.modifierSnapshot.isNotEmpty)
                                      Text('${item.modifierSnapshot.length} modificador(es)',
                                          style: Theme.of(context).textTheme.bodySmall),
                                  ],
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                  const SizedBox(height: 16),
                  Text('Resumo', style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 8),
                  Card(
                    child: Column(children: [
                      _SummaryRow('Subtotal', _summary('subtotal')),
                      _SummaryRow('Descontos', _summary('discount_total')),
                      _SummaryRow('Taxa', _summary('service_fee_total')),
                      _SummaryRow('Total', _summary('total_due'), bold: true),
                      _SummaryRow('Pago', _summary('paid_total')),
                      _SummaryRow('Saldo', _summary('remaining_balance'), bold: true),
                    ]),
                  ),
                  const SizedBox(height: 96),
                ]),
              ),
      );
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow(this.label, this.value, {this.bold = false});
  final String label;
  final String value;
  final bool bold;

  @override
  Widget build(BuildContext context) => ListTile(
        dense: true,
        title: Text(label, style: bold ? const TextStyle(fontWeight: FontWeight.w800) : null),
        trailing: Text(formatMoney(value),
            style: bold ? const TextStyle(fontWeight: FontWeight.w800) : null),
      );
}

class TableOrderPage extends StatefulWidget {
  const TableOrderPage({
    required this.controller,
    required this.attendance,
    super.key,
  });

  final AppController controller;
  final TableAttendance attendance;

  @override
  State<TableOrderPage> createState() => _TableOrderPageState();
}

class _TableOrderPageState extends State<TableOrderPage> {
  final _search = TextEditingController();
  List<QuickSaleProduct> _catalog = const [];
  final List<QuickSaleCartItem> _cart = [];
  int? _categoryId;
  bool _loading = true;
  bool _saving = false;

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
    final catalog = await widget.controller.tableCatalog(search: _search.text);
    if (!mounted) return;
    setState(() {
      _catalog = catalog ?? const [];
      _loading = false;
    });
  }

  List<QuickSaleProduct> get _visible => _catalog
      .where((product) => _categoryId == null || product.categoryId == _categoryId)
      .toList(growable: false);

  List<QuickSaleCategory> get _categories {
    final byId = <int, QuickSaleCategory>{};
    for (final product in _catalog) {
      if (product.categoryId != null && product.categoryName != null) {
        byId[product.categoryId!] = QuickSaleCategory(
          id: product.categoryId!,
          name: product.categoryName!,
        );
      }
    }
    return byId.values.toList()..sort((a, b) => a.name.compareTo(b.name));
  }

  Future<void> _add(QuickSaleProduct product) async {
    var item = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) => SaleItemEditorDialog(product: product),
    );
    if (item == null || !mounted) return;
    item = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) => _TableCartItemDialog(item: item!),
    );
    if (item != null && mounted) setState(() => _cart.add(item!));
  }

  Future<void> _edit(int index) async {
    var item = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) => SaleItemEditorDialog(product: _cart[index].product, initial: _cart[index]),
    );
    if (item == null || !mounted) return;
    item = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) => _TableCartItemDialog(item: item!),
    );
    if (item != null && mounted) setState(() => _cart[index] = item!);
  }

  Future<void> _save() async {
    if (_cart.isEmpty) return;
    setState(() => _saving = true);
    final created = await widget.controller.saveTableOrder(
      attendanceId: widget.attendance.id,
      idempotencyKey: createIdempotencyKey(),
      items: _cart
          .map((item) => <String, dynamic>{
                'product': item.product.id,
                'quantity': item.quantity,
                'modifiers': item.modifiers,
                'notes': item.notes,
              })
          .toList(growable: false),
    );
    if (!mounted) return;
    setState(() => _saving = false);
    if (created == null) return;
    widget.controller.showTransientMessage('Pedido enviado com sucesso.',
        tone: TransientAlertTone.success);
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Novo pedido')),
        bottomNavigationBar: SafeArea(
          minimum: const EdgeInsets.all(16),
          child: FilledButton.icon(
            onPressed: _saving || _cart.isEmpty ? null : _save,
            icon: _saving
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.send),
            label: Text(_saving ? 'ENVIANDO...' : 'SALVAR E ENVIAR PEDIDO'),
          ),
        ),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : Column(children: [
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: TextField(
                    controller: _search,
                    onSubmitted: (_) => _load(),
                    decoration: InputDecoration(
                      labelText: 'Pesquisar produtos',
                      prefixIcon: const Icon(Icons.search),
                      suffixIcon: IconButton(onPressed: _load, icon: const Icon(Icons.search)),
                    ),
                  ),
                ),
                SizedBox(
                  height: 44,
                  child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: 16), children: [
                    ChoiceChip(label: const Text('Todos'), selected: _categoryId == null, onSelected: (_) => setState(() => _categoryId = null)),
                    for (final category in _categories)
                      Padding(
                        padding: const EdgeInsets.only(left: 8),
                        child: ChoiceChip(
                          label: Text(category.name),
                          selected: _categoryId == category.id,
                          onSelected: (_) => setState(() => _categoryId = category.id),
                        ),
                      ),
                  ]),
                ),
                Expanded(
                  child: GridView.builder(
                    padding: const EdgeInsets.all(16),
                    gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                      maxCrossAxisExtent: 220,
                      mainAxisSpacing: 12,
                      crossAxisSpacing: 12,
                      childAspectRatio: 1.25,
                    ),
                    itemCount: _visible.length,
                    itemBuilder: (_, index) {
                      final product = _visible[index];
                      return Card(
                        child: InkWell(
                          borderRadius: BorderRadius.circular(12),
                          onTap: product.canSell ? () => _add(product) : null,
                          child: Padding(
                            padding: const EdgeInsets.all(12),
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(product.name, maxLines: 2, overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(fontWeight: FontWeight.w800)),
                              const Spacer(),
                              Text(formatMoney(product.price)),
                              if (!product.canSell) Text(product.availabilityReason ?? 'Indisponível', style: const TextStyle(color: Colors.red)),
                            ]),
                          ),
                        ),
                      );
                    },
                  ),
                ),
                if (_cart.isNotEmpty)
                  SizedBox(
                    height: 180,
                    child: Card(
                      margin: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                      child: ListView.builder(
                        itemCount: _cart.length,
                        itemBuilder: (_, index) => ListTile(
                          title: Text('${_cart[index].quantity}x ${_cart[index].product.name}'),
                          subtitle: Text(_cart[index].notes.isEmpty ? formatMoney(_cart[index].product.price) : _cart[index].notes),
                          trailing: IconButton(onPressed: () => setState(() => _cart.removeAt(index)), icon: const Icon(Icons.delete_outline)),
                          onTap: () => _edit(index),
                        ),
                      ),
                    ),
                  ),
              ]),
      );
}

class _TableCartItemDialog extends StatefulWidget {
  const _TableCartItemDialog({required this.item});
  final QuickSaleCartItem item;

  @override
  State<_TableCartItemDialog> createState() => _TableCartItemDialogState();
}

class _TableCartItemDialogState extends State<_TableCartItemDialog> {
  late final _quantity = TextEditingController(text: widget.item.quantity);
  late final _notes = TextEditingController(text: widget.item.notes);

  @override
  void dispose() {
    _quantity.dispose();
    _notes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.item.product.name),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: _quantity, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Quantidade')),
          TextField(controller: _notes, maxLines: 3, decoration: const InputDecoration(labelText: 'Observações')),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('CANCELAR')),
          FilledButton(
            onPressed: () => Navigator.pop(context, widget.item.copyWith(
              quantity: _quantity.text.trim(),
              notes: _notes.text.trim(),
            )),
            child: const Text('ADICIONAR'),
          ),
        ],
      );
}
