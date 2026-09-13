import 'dart:async';

import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../core/transient_feedback.dart';
import '../scanner/product_barcode_scanner_page.dart';
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
      widget.controller.bootstrapSnapshot?.permissions
          .contains('tables.add_items') ==
      true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final detail =
        await widget.controller.tableAttendanceDetail(_attendance.id);
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
          title: Text(
              _attendance.tableName.isEmpty ? 'Mesa' : _attendance.tableName),
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
                          Text(
                              _attendance.status == 'open'
                                  ? 'ABERTA'
                                  : 'FECHADA',
                              style:
                                  const TextStyle(fontWeight: FontWeight.w800)),
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
                  Text('Pedidos',
                      style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 8),
                  if (_attendance.orders.isEmpty)
                    const Card(
                        child: ListTile(title: Text('Nenhum pedido enviado.'))),
                  for (final order in _attendance.orders)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Pedido #${order.id}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w800)),
                            const SizedBox(height: 6),
                            for (final item in order.items)
                              Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                        '${item.quantity}x ${item.productName}'),
                                    Text(
                                        '${formatMoney(item.unitPrice)} · ${item.status}',
                                        style: Theme.of(context)
                                            .textTheme
                                            .bodySmall),
                                    if (item.notes.isNotEmpty)
                                      Text(item.notes,
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodySmall),
                                    if (item.modifierSnapshot.isNotEmpty)
                                      Text(
                                          '${item.modifierSnapshot.length} modificador(es)',
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodySmall),
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
                      _SummaryRow('Saldo', _summary('remaining_balance'),
                          bold: true),
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
        title: Text(label,
            style: bold ? const TextStyle(fontWeight: FontWeight.w800) : null),
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
  final _cartListenable = ValueNotifier<int>(0);
  List<QuickSaleProduct> _catalog = const [];
  final List<QuickSaleCartItem> _cart = [];
  int? _categoryId;
  bool _favoritesOnly = false;
  bool _loading = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _search.addListener(() => setState(() {}));
    unawaited(_load());
  }

  @override
  void dispose() {
    _search.dispose();
    _cartListenable.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final catalog = await widget.controller.tableCatalog();
    if (!mounted) return;
    setState(() {
      _catalog = catalog ?? const [];
      _loading = false;
    });
  }

  List<QuickSaleProduct> get _visible => _catalog
      .where((product) =>
          (_categoryId == null || product.categoryId == _categoryId) &&
          (!_favoritesOnly || product.favorite) &&
          (_search.text.trim().isEmpty ||
              product.name
                  .toLowerCase()
                  .contains(_search.text.trim().toLowerCase()) ||
              product.internalCode
                  .toLowerCase()
                  .contains(_search.text.trim().toLowerCase()) ||
              (product.barcode
                      ?.toLowerCase()
                      .contains(_search.text.trim().toLowerCase()) ??
                  false)))
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
    if (!product.canSell) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Este produto está sem estoque no momento.'),
      ));
      return;
    }
    final item = QuickSaleCartItem(
      clientItemId: createIdempotencyKey(),
      product: product,
      quantity: '1',
    );
    if (_requiresConfiguration(product)) {
      await _editNewItem(product, item);
      return;
    }
    _addCartItem(item);
  }

  bool _requiresConfiguration(QuickSaleProduct product) =>
      product.modifierGroups.any(
        (group) =>
            group.required ||
            group.minSelections > 0 ||
            (double.tryParse(group.minTotalQuantity.replaceAll(',', '.')) ??
                    0) >
                0 ||
            group.requiredQuantity != null,
      );

  Future<void> _editNewItem(
      QuickSaleProduct product, QuickSaleCartItem item) async {
    final configured = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) => SaleItemEditorDialog(product: product, initial: item),
    );
    if (configured != null && mounted) _addCartItem(configured);
  }

  void _addCartItem(QuickSaleCartItem item) => setState(() {
        _cart.add(item);
        _cartListenable.value = _itemCount;
      });

  Future<void> _addBatch(QuickSaleProduct product) async {
    if (!product.canSell) {
      await _add(product);
      return;
    }
    final quantity = await showDialog<String>(
      context: context,
      builder: (_) => BatchQuantityDialog(productName: product.name),
    );
    if (quantity == null || !mounted) return;
    final item = QuickSaleCartItem(
      clientItemId: createIdempotencyKey(),
      product: product,
      quantity: quantity,
    );
    if (_requiresConfiguration(product)) {
      await _editNewItem(product, item);
    } else {
      _addCartItem(item);
    }
  }

  int get _itemCount => _cart.fold(
      0,
      (total, item) =>
          total +
          (double.tryParse(item.quantity.replaceAll(',', '.')) ?? 0).round());

  String get _provisionalTotal => _cart.fold<double>(0, (total, item) {
        var price =
            double.tryParse(item.product.price.replaceAll(',', '.')) ?? 0;
        for (final modifier in item.modifiers) {
          final option = item.product.modifierGroups
              .expand((group) => group.options)
              .where((option) => option.id == modifier['option'])
              .firstOrNull;
          price += (double.tryParse(
                      option?.additionalPrice.replaceAll(',', '.') ?? '0') ??
                  0) *
              (double.tryParse('${modifier['quantity'] ?? '1'}') ?? 1);
        }
        return total +
            price * (double.tryParse(item.quantity.replaceAll(',', '.')) ?? 0);
      }).toStringAsFixed(2);

  Future<void> _edit(int index) async {
    final item = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) => SaleItemEditorDialog(
          product: _cart[index].product, initial: _cart[index]),
    );
    if (item != null && mounted) {
      setState(() {
        _cart[index] = item;
        _cartListenable.value = _itemCount;
      });
    }
  }

  Future<bool> _scanBarcode(String barcode) async {
    final products = await widget.controller.tableCatalog(search: barcode);
    if (!mounted || products == null) return false;
    final product =
        products.where((item) => item.barcode == barcode).firstOrNull;
    if (product == null) return false;
    await _add(product);
    return true;
  }

  Future<void> _openBarcodeScanner() async {
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => ProductBarcodeScannerPage(
        onBarcode: _scanBarcode,
        cartListenable: _cartListenable,
        itemCount: () => '$_itemCount',
        total: () => formatMoney(_provisionalTotal),
      ),
    ));
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
        appBar:
            AppBar(title: Text('Novo pedido • ${widget.attendance.tableName}')),
        bottomNavigationBar: MediaQuery.sizeOf(context).width < 900
            ? MobileCartBar(
                itemCount: _itemCount,
                preview: null,
                updating: false,
                showTotal: false,
                actionLabel: 'VER RESUMO',
                onTap: _showMobileSummary,
              )
            : null,
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : LayoutBuilder(builder: (context, constraints) {
                final catalog = ProductCatalogPanel(
                  search: _search,
                  loading: false,
                  products: _visible,
                  categories: _categories,
                  categoryId: _categoryId,
                  favoritesOnly: _favoritesOnly,
                  onCategory: (value) => setState(() {
                    _categoryId = value;
                    if (value != null) _favoritesOnly = false;
                  }),
                  onFavorites: () => setState(() {
                    _favoritesOnly = !_favoritesOnly;
                    if (_favoritesOnly) _categoryId = null;
                  }),
                  onBarcode: _openBarcodeScanner,
                  onSearchSubmitted: (_) {},
                  onProduct: _add,
                  onProductLongPress: _addBatch,
                );
                if (constraints.maxWidth < 900) return catalog;
                return Row(children: [
                  Expanded(flex: 3, child: catalog),
                  SizedBox(
                      width: 420,
                      child: _TableOrderSummaryPanel(
                        cart: _cart,
                        saving: _saving,
                        onEdit: _edit,
                        onRemove: _remove,
                        onSave: _save,
                      )),
                ]);
              }),
      );

  void _remove(int index) => setState(() {
        _cart.removeAt(index);
        _cartListenable.value = _itemCount;
      });

  Future<void> _showMobileSummary() async {
    final saved = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => Scaffold(
        appBar: AppBar(
            title: Text('Resumo do pedido • ${widget.attendance.tableName}')),
        body: _TableOrderSummaryPanel(
          cart: _cart,
          saving: _saving,
          onEdit: _edit,
          onRemove: _remove,
          onSave: _save,
        ),
      ),
    ));
    if (saved == true && mounted) Navigator.of(context).pop(true);
  }
}

class _TableOrderSummaryPanel extends StatelessWidget {
  const _TableOrderSummaryPanel(
      {required this.cart,
      required this.saving,
      required this.onEdit,
      required this.onRemove,
      required this.onSave});
  final List<QuickSaleCartItem> cart;
  final bool saving;
  final ValueChanged<int> onEdit;
  final ValueChanged<int> onRemove;
  final Future<void> Function() onSave;

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.white,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text('RESUMO DO PEDIDO',
                style: Theme.of(context)
                    .textTheme
                    .titleMedium
                    ?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            Expanded(
                child: cart.isEmpty
                    ? const Center(
                        child: Text('Adicione produtos para iniciar o pedido.'))
                    : ListView.separated(
                        itemCount: cart.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (_, index) {
                          final item = cart[index];
                          return ListTile(
                            onTap: () => onEdit(index),
                            title: Text(item.product.name),
                            subtitle: Text([
                              'Qtd. ${item.quantity}',
                              if (item.notes.isNotEmpty) 'Obs: ${item.notes}'
                            ].join('\n')),
                            trailing: IconButton(
                                onPressed: () => onRemove(index),
                                icon: const Icon(Icons.delete_outline)),
                          );
                        },
                      )),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: saving || cart.isEmpty ? null : () => onSave(),
              icon: saving
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.send),
              label: Text(saving ? 'ENVIANDO...' : 'SALVAR E ENVIAR PEDIDO'),
            ),
          ]),
        ),
      );
}
