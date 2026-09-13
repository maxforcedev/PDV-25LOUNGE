import 'dart:async';

import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../core/transient_feedback.dart';
import '../network/pos_api_error.dart';
import '../scanner/product_barcode_scanner_page.dart';
import '../sales/quick_sale_page.dart';
import '../sales/sale_models.dart';
import 'attendance_models.dart';

double _tableCartNumber(Object? value) =>
    double.tryParse('$value'.replaceAll(',', '.')) ?? 0;

String _tableQuantityText(Object? value) {
  final quantity = _tableCartNumber(value);
  return quantity == quantity.roundToDouble()
      ? quantity.toInt().toString()
      : quantity.toStringAsFixed(3).replaceFirst(RegExp(r'0+$'), '');
}

QuickSaleModifierOption? _tableModifierOption(
    QuickSaleProduct product, Map<String, dynamic> modifier) {
  final optionId = int.tryParse(
      '${modifier['option'] ?? modifier['option_id'] ?? modifier['id'] ?? ''}');
  if (optionId == null) return null;
  return product.modifierGroups
      .expand((group) => group.options)
      .where((option) => option.id == optionId)
      .firstOrNull;
}

String _tableModifierName(
    QuickSaleProduct product, Map<String, dynamic> modifier) {
  final option = _tableModifierOption(product, modifier);
  return option?.name ??
      '${modifier['option_name'] ?? modifier['modifier_name'] ?? modifier['name'] ?? 'Modificador'}';
}

String _tableModifierText(
    QuickSaleProduct product, Map<String, dynamic> modifier) {
  final quantity = _tableCartNumber(modifier['quantity'] ?? 1);
  final prefix = quantity == 1 ? '' : '${_tableQuantityText(quantity)}x ';
  return '+ $prefix${_tableModifierName(product, modifier)}';
}

double _tableLineTotal(QuickSaleCartItem item) {
  final modifiers = item.modifiers.fold<double>(0, (total, modifier) {
    final option = _tableModifierOption(item.product, modifier);
    return total +
        _tableCartNumber(option?.additionalPrice) *
            _tableCartNumber(modifier['quantity'] ?? 1);
  });
  return (_tableCartNumber(item.product.price) + modifiers) *
      _tableCartNumber(item.quantity);
}

String _tableHistoryTime(String? value) {
  if (value == null || value.isEmpty) return '';
  final date = DateTime.tryParse(value)?.toLocal();
  if (date == null) return value;
  String twoDigits(int number) => number.toString().padLeft(2, '0');
  return '${twoDigits(date.day)}/${twoDigits(date.month)}/${date.year} '
      '${twoDigits(date.hour)}:${twoDigits(date.minute)}';
}

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
  bool _actionInProgress = false;
  AttendanceTableGroup? _group;
  final Set<int> _selectedItems = {};

  bool get _canAddItems =>
      widget.controller.bootstrapSnapshot?.permissions
          .contains('tables.add_items') ==
       true;

  bool _can(String permission) =>
      widget.controller.bootstrapSnapshot?.permissions.contains(permission) ==
      true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final results = await Future.wait<Object?>([
      widget.controller.tableAttendanceDetail(_attendance.id),
      widget.controller.attendanceTables(),
    ]);
    if (!mounted) return;
    final detail = results[0] as TableAttendance?;
    final tables = results[1] as List<AttendanceTable>?;
    setState(() {
      _attendance = detail ?? _attendance;
      _group = tables
          ?.where((table) => table.id == _attendance.tableId)
          .firstOrNull
          ?.group;
      _selectedItems.removeWhere((id) => !_attendance.orders
          .expand((order) => order.items)
          .any((item) => item.id == id && item.status == 'confirmed'));
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

  Future<void> _cancelItem(TableOrderItem item) async {
    final reason = await _requiredReasonDialog(context, 'Cancelar item');
    if (reason == null || _actionInProgress) return;
    setState(() => _actionInProgress = true);
    final cancelled = await widget.controller.cancelTableOrderItem(
      itemId: item.id,
      reason: reason,
      idempotencyKey: createIdempotencyKey(),
    );
    if (!mounted) return;
    setState(() => _actionInProgress = false);
    if (cancelled != null) await _load();
  }

  Future<void> _cancelOrder(TableOrder order) async {
    final reason = await _requiredReasonDialog(
        context, 'Cancelar pedido #${order.id}');
    if (reason == null || _actionInProgress) return;
    setState(() => _actionInProgress = true);
    final cancelled = await widget.controller.cancelTableOrder(
      orderId: order.id,
      reason: reason,
      idempotencyKey: createIdempotencyKey(),
    );
    if (!mounted) return;
    setState(() => _actionInProgress = false);
    if (cancelled != null) await _load();
  }

  Future<void> _toggleBill() async {
    if (_actionInProgress) return;
    setState(() => _actionInProgress = true);
    final updated = await widget.controller.setTableBillRequested(
      attendanceId: _attendance.id,
      requested: !_attendance.billRequested,
      idempotencyKey: createIdempotencyKey(),
    );
    if (!mounted) return;
    setState(() => _actionInProgress = false);
    if (updated != null) await _load();
  }

  Future<void> _transferItems() async {
    if (_selectedItems.isEmpty || _actionInProgress) return;
    final tables = await widget.controller.attendanceTables();
    if (!mounted || tables == null) return;
    final target = await showDialog<AttendanceTable>(
      context: context,
      builder: (_) => _TableAttendancePicker(
        tables: tables
            .where((table) =>
                table.attendance != null &&
                table.attendance!.id != _attendance.id &&
                !table.legacyOccupied)
            .toList(growable: false),
      ),
    );
    if (target?.attendance == null || !mounted) return;
    final items = _attendance.orders
        .expand((order) => order.items)
        .where((item) => _selectedItems.contains(item.id))
        .map((item) => {'item': item.id, 'quantity': item.quantity})
        .toList(growable: false);
    setState(() => _actionInProgress = true);
    final moved = await widget.controller.transferTableItems(
      attendanceId: _attendance.id,
      destinationAttendanceId: target!.attendance!.id,
      items: items,
      idempotencyKey: createIdempotencyKey(),
    );
    if (!mounted) return;
    setState(() => _actionInProgress = false);
    if (moved != null) await _load();
  }

  Future<void> _separateFromGroup() async {
    if (_actionInProgress) return;
    setState(() => _actionInProgress = true);
    final separated = await widget.controller.separateAttendanceTable(
      tableId: _attendance.tableId,
      idempotencyKey: createIdempotencyKey(),
    );
    if (!mounted) return;
    setState(() => _actionInProgress = false);
    if (separated) await _load();
  }

  Future<void> _selectCustomer() async {
    final customer = await showDialog<QuickSaleCustomer>(
      context: context,
      builder: (_) => _TableCustomerPicker(
        controller: widget.controller,
        canCreate: _can('customers.add'),
        canReactivate: _can('customers.change'),
      ),
    );
    if (customer != null && mounted) await _setCustomer(customer.id);
  }

  Future<void> _setCustomer(int? customerId) async {
    if (_actionInProgress) return;
    setState(() => _actionInProgress = true);
    final updated = await widget.controller.setTableAttendanceCustomer(
      attendanceId: _attendance.id,
      customerId: customerId,
      idempotencyKey: createIdempotencyKey(),
    );
    if (!mounted) return;
    setState(() => _actionInProgress = false);
    if (updated != null) await _load();
  }

  void _showCustomer() {
    showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Cliente'),
        content: Text([
          _attendance.customerName,
          if (_attendance.customerId != null) 'Código: ${_attendance.customerId}',
        ].join('\n')),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('FECHAR'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: Text(
              _attendance.tableName.isEmpty ? 'Mesa' : _attendance.tableName),
          actions: [
            if (_attendance.status == 'open' && _can('tables.close'))
              IconButton(
                onPressed: _loading || _actionInProgress ? null : _toggleBill,
                tooltip: _attendance.billRequested
                    ? 'Cancelar solicitação de conta'
                    : 'Solicitar conta',
                icon: Icon(_attendance.billRequested
                    ? Icons.remove_done_outlined
                    : Icons.request_quote_outlined),
              ),
            if (_group != null && _can('tables.merge'))
              IconButton(
                onPressed:
                    _loading || _actionInProgress ? null : _separateFromGroup,
                tooltip: 'Separar do grupo',
                icon: const Icon(Icons.call_split_outlined),
              ),
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
                          const SizedBox(height: 12),
                          Text('CLIENTE',
                              style: Theme.of(context).textTheme.labelLarge),
                          Text(_attendance.customerName.isEmpty
                              ? 'Nenhum cliente'
                              : _attendance.customerName),
                          if (_can('customers.view'))
                            Wrap(spacing: 8, children: [
                              if (_attendance.customerId != null)
                                TextButton(
                                  onPressed: _showCustomer,
                                  child: const Text('VER'),
                                ),
                              TextButton(
                                onPressed: _actionInProgress
                                    ? null
                                    : _selectCustomer,
                                child: Text(_attendance.customerId == null
                                    ? 'PESQUISAR'
                                    : 'TROCAR'),
                              ),
                              if (_attendance.customerId != null && _canAddItems)
                                TextButton(
                                  onPressed: _actionInProgress
                                      ? null
                                      : () => _setCustomer(null),
                                  child: const Text('REMOVER'),
                                ),
                            ]),
                          if (_attendance.billRequested)
                            const Padding(
                              padding: EdgeInsets.only(top: 8),
                              child: Text('CONTA SOLICITADA',
                                  style: TextStyle(
                                      color: Colors.deepOrange,
                                      fontWeight: FontWeight.w800)),
                            ),
                          if (_attendance.status == 'open' &&
                              _can('tables.close'))
                            Padding(
                              padding: const EdgeInsets.only(top: 8),
                              child: OutlinedButton.icon(
                                onPressed: _actionInProgress ? null : _toggleBill,
                                icon: Icon(_attendance.billRequested
                                    ? Icons.remove_done_outlined
                                    : Icons.request_quote_outlined),
                                label: Text(_attendance.billRequested
                                    ? 'CANCELAR SOLICITAÇÃO'
                                    : 'SOLICITAR CONTA'),
                              ),
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
                            Text('Status: ${order.status.toUpperCase()}',
                                style: Theme.of(context).textTheme.bodySmall),
                            if (order.createdAt != null ||
                                order.createdByName.isNotEmpty)
                              Text(
                                  [
                                     if (order.createdAt != null)
                                       _tableHistoryTime(order.createdAt),
                                    if (order.createdByName.isNotEmpty)
                                      'Operador: ${order.createdByName}',
                                  ].join(' · '),
                                  style: Theme.of(context).textTheme.bodySmall),
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
                                      Text('Obs: ${item.notes}',
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodySmall),
                                    if (item.cancellationReason.isNotEmpty)
                                      Text('Motivo: ${item.cancellationReason}',
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodySmall),
                                     if (item.modifierSnapshot.isNotEmpty)
                                       Text(
                                           item.modifierSnapshot
                                               .map((row) =>
                                                   '+ ${row['option_name'] ?? row['modifier_name'] ?? row['name'] ?? 'Modificador'}')
                                               .join('\n'),
                                           style: Theme.of(context)
                                               .textTheme
                                               .bodySmall),
                                     if (item.confirmedAt != null)
                                       Text(
                                           'Confirmado em ${_tableHistoryTime(item.confirmedAt)}',
                                           style: Theme.of(context)
                                               .textTheme
                                               .bodySmall),
                                    if (item.status == 'confirmed' &&
                                        _can('tables.transfer_items'))
                                      CheckboxListTile(
                                        contentPadding: EdgeInsets.zero,
                                        dense: true,
                                        title: const Text('Transferir item'),
                                        value: _selectedItems.contains(item.id),
                                        onChanged: _actionInProgress
                                            ? null
                                            : (selected) => setState(() =>
                                                selected == true
                                                    ? _selectedItems.add(item.id)
                                                    : _selectedItems.remove(item.id)),
                                      ),
                                    if (item.status == 'confirmed' &&
                                        _can('tables.cancel_items'))
                                      Align(
                                        alignment: Alignment.centerRight,
                                        child: TextButton.icon(
                                          onPressed: _actionInProgress
                                              ? null
                                              : () => _cancelItem(item),
                                          icon: const Icon(Icons.cancel_outlined),
                                          label: const Text('CANCELAR ITEM'),
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                            if (order.status == 'confirmed' &&
                                _can('tables.cancel_items'))
                              Align(
                                alignment: Alignment.centerRight,
                                child: OutlinedButton.icon(
                                  onPressed: _actionInProgress
                                      ? null
                                      : () => _cancelOrder(order),
                                  icon: const Icon(Icons.cancel_presentation_outlined),
                                  label: const Text('CANCELAR PEDIDO'),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                  if (_selectedItems.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: OutlinedButton.icon(
                        onPressed: _actionInProgress ? null : _transferItems,
                        icon: const Icon(Icons.drive_file_move_outline),
                        label: const Text('TRANSFERIR ITENS'),
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
  String? _orderIdempotencyKey;
  Future<void> _cartMutationQueue = Future.value();

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
    if (_saving) return;
    if (!product.canSell) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(product.availabilityReason?.trim().isNotEmpty == true
            ? product.availabilityReason!
            : 'Este produto está sem estoque no momento.'),
      ));
      return;
    }
    final item = QuickSaleCartItem(
      clientItemId: createIdempotencyKey(),
      product: product,
      quantity: '1',
    );
    if (product.modifierGroups.isNotEmpty) {
      await _editNewItem(product, item);
      return;
    }
    await _addCartItem(item);
  }

  Future<void> _editNewItem(
      QuickSaleProduct product, QuickSaleCartItem item) async {
    final configured = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) => _TableSaleItemEditorDialog(product: product, initial: item),
    );
    if (configured != null && mounted && !_saving) {
      await _addCartItem(configured);
    }
  }

  Future<void> _addCartItem(QuickSaleCartItem item) =>
      _queueCartMutation((cart) {
        final equivalent = cart.indexWhere((entry) =>
            entry.product.id == item.product.id &&
            entry.notes == item.notes &&
            entry.modifiers.toString() == item.modifiers.toString());
        if (equivalent < 0) return [...cart, item];
        final current =
            double.tryParse(cart[equivalent].quantity.replaceAll(',', '.')) ?? 0;
        final added = double.tryParse(item.quantity.replaceAll(',', '.')) ?? 0;
        final quantity = current + added;
        final merged = List<QuickSaleCartItem>.from(cart);
        merged[equivalent] = merged[equivalent].copyWith(
          quantity: quantity == quantity.roundToDouble()
              ? '${quantity.toInt()}'
              : quantity.toStringAsFixed(3),
        );
        return merged;
      });

  Future<void> _replaceCartItem(String clientItemId, QuickSaleCartItem item) =>
      _queueCartMutation((cart) {
        final index =
            cart.indexWhere((entry) => entry.clientItemId == clientItemId);
        if (index < 0) return cart;
        final updated = List<QuickSaleCartItem>.from(cart)..[index] = item;
        return updated;
      });

  Future<void> _queueCartMutation(
      List<QuickSaleCartItem> Function(List<QuickSaleCartItem>) update,
      {bool checkAvailability = true}) {
    return _queueCartTask(() async {
      if (!mounted) return;
      final candidate = update(List<QuickSaleCartItem>.from(_cart));
      if (checkAvailability && candidate.isNotEmpty) {
        final availability = await widget.controller.tableStockAvailability(
          items: _tableCartPayload(candidate),
        );
        if (!mounted || availability == null) return;
        if (!availability.available && availability.enforced) {
          _showStockUnavailable(availability, candidate);
          return;
        }
      }
      setState(() {
        _cart
          ..clear()
          ..addAll(candidate);
        _orderIdempotencyKey = null;
      });
      _notifyCartChanged();
    });
  }

  Future<T> _queueCartTask<T>(FutureOr<T> Function() task) {
    final queued = _cartMutationQueue.then((_) => task());
    _cartMutationQueue = queued.then<void>((_) {}, onError: (_, __) {});
    return queued;
  }

  List<Map<String, dynamic>> _tableCartPayload(
          List<QuickSaleCartItem> cart) =>
      cart
          .map((item) => <String, dynamic>{
                'product': item.product.id,
                'quantity': item.quantity,
                'modifiers': item.modifiers
                    .map((modifier) => Map<String, dynamic>.from(modifier))
                    .toList(growable: false),
                'notes': item.notes,
              })
          .toList(growable: false);

  void _notifyCartChanged() => _cartListenable.value++;

  void _showStockUnavailable(
      QuickSaleStockAvailability availability, List<QuickSaleCartItem> cart) {
    final available = availability.availableQuantity;
    final shortage = availability.shortages.firstOrNull;
    final item = shortage == null
        ? null
        : cart.where((entry) => '${entry.product.id}' == '${shortage['product'] ?? shortage['product_id']}').firstOrNull;
    final requested = item?.quantity;
    final message = available == null
        ? 'Este produto não possui estoque suficiente para essa quantidade.'
        : requested == null
            ? 'Só temos $available disponíveis deste produto.'
            : 'Você tentou adicionar $requested, mas há somente $available disponíveis.';
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _addBatch(QuickSaleProduct product) async {
    if (_saving) return;
    if (!product.canSell) {
      await _add(product);
      return;
    }
    final quantity = await showDialog<String>(
      context: context,
      builder: (_) => BatchQuantityDialog(productName: product.name),
    );
    if (quantity == null || !mounted || _saving) return;
    final item = QuickSaleCartItem(
      clientItemId: createIdempotencyKey(),
      product: product,
      quantity: quantity,
    );
    if (product.modifierGroups.isNotEmpty) {
      await _editNewItem(product, item);
    } else {
      await _addCartItem(item);
    }
  }

  int get _itemCount => _cart.length;

  String get _provisionalTotal => _cart.fold<double>(0, (total, item) {
        return total + _tableLineTotal(item);
      }).toStringAsFixed(2);

  Future<void> _edit(int index) async {
    if (_saving) return;
    final initial = _cart[index];
    final item = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) => _TableSaleItemEditorDialog(
          product: initial.product, initial: initial),
    );
    if (item != null && mounted && !_saving) {
      await _replaceCartItem(initial.clientItemId, item);
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
    if (_saving || _cart.isEmpty) return;
    setState(() => _saving = true);
    _notifyCartChanged();
    var created = false;
    try {
      created = await _queueCartTask(() async {
        if (!mounted || _cart.isEmpty) return false;
        // This immutable payload is captured only after every earlier cart task.
        final snapshot = _tableCartPayload(List<QuickSaleCartItem>.from(_cart));
        final availability = await widget.controller.tableStockAvailability(
          items: snapshot,
        );
        if (!mounted || availability == null) return false;
        if (!availability.available && availability.enforced) {
          _showStockUnavailable(availability, _cart);
          return false;
        }
        final idempotencyKey = _orderIdempotencyKey ??= createIdempotencyKey();
        return (await widget.controller.saveTableOrder(
                  attendanceId: widget.attendance.id,
                  idempotencyKey: idempotencyKey,
                  items: snapshot,
                )) !=
            null;
      });
    } finally {
      if (mounted) {
        setState(() => _saving = false);
        _notifyCartChanged();
      }
    }
    if (!mounted) return;
    if (!created) return;
    _orderIdempotencyKey = null;
    widget.controller.showTransientMessage('Pedido enviado com sucesso.',
        tone: TransientAlertTone.success);
    Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar:
            AppBar(title: Text('Novo pedido • ${widget.attendance.tableName}')),
        bottomNavigationBar: MediaQuery.sizeOf(context).width < 900
            ? ValueListenableBuilder<int>(
                valueListenable: _cartListenable,
                builder: (_, __, ___) => MobileCartBar(
                  itemCount: _itemCount,
                  preview: null,
                  updating: _saving,
                  showTotal: false,
                  actionLabel: 'VER RESUMO',
                  onTap: _showMobileSummary,
                ),
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
                      child: ValueListenableBuilder<int>(
                          valueListenable: _cartListenable,
                          builder: (_, __, ___) => _TableOrderSummaryPanel(
                                cart: _cart,
                                saving: _saving,
                                onEdit: _edit,
                                onRemove: (index) => unawaited(_remove(index)),
                                onSave: _save,
                              ))),
                ]);
              }),
      );

  Future<void> _remove(int index) {
    if (_saving || index >= _cart.length) return Future.value();
    final clientItemId = _cart[index].clientItemId;
    return _queueCartMutation((cart) {
      final index =
          cart.indexWhere((entry) => entry.clientItemId == clientItemId);
      if (index < 0) return cart;
      return List<QuickSaleCartItem>.from(cart)..removeAt(index);
    }, checkAvailability: false);
  }

  Future<void> _showMobileSummary() async {
    final saved = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => Scaffold(
        appBar: AppBar(
            title: Text('Resumo do pedido • ${widget.attendance.tableName}')),
        body: ValueListenableBuilder<int>(
          valueListenable: _cartListenable,
          builder: (_, __, ___) => _TableOrderSummaryPanel(
            cart: _cart,
            saving: _saving,
            onEdit: _edit,
            onRemove: (index) => unawaited(_remove(index)),
            onSave: _save,
          ),
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
                             onTap: saving ? null : () => onEdit(index),
                             title: Text(item.product.name),
                             subtitle: Text([
                               'Qtd. ${item.quantity}',
                               for (final modifier in item.modifiers)
                                 _tableModifierText(item.product, modifier),
                               if (item.notes.isNotEmpty) 'Obs: ${item.notes}'
                             ].join('\n')),
                             leading: SizedBox(
                               width: 76,
                               child: Text(
                                 formatMoney(_tableLineTotal(item).toStringAsFixed(2)),
                                 style: const TextStyle(
                                     fontWeight: FontWeight.w800),
                               ),
                             ),
                             trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                               IconButton(
                                   onPressed: saving ? null : () => onRemove(index),
                                   icon: const Icon(Icons.delete_outline)),
                               const Icon(Icons.chevron_right),
                             ]),
                           );
                        },
                       )),
             const SizedBox(height: 12),
             Text(
               'Total provisório: ${formatMoney(cart.fold<double>(0, (total, item) => total + _tableLineTotal(item)).toStringAsFixed(2))}',
               textAlign: TextAlign.end,
               style: const TextStyle(fontWeight: FontWeight.w800),
             ),
             const SizedBox(height: 8),
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

class _TableSaleItemEditorDialog extends StatefulWidget {
  const _TableSaleItemEditorDialog({
    required this.product,
    required this.initial,
  });

  final QuickSaleProduct product;
  final QuickSaleCartItem initial;

  @override
  State<_TableSaleItemEditorDialog> createState() =>
      _TableSaleItemEditorDialogState();
}

class _TableSaleItemEditorDialogState
    extends State<_TableSaleItemEditorDialog> {
  final Map<int, int> _modifierQuantities = {};
  late final TextEditingController _quantity;
  late final TextEditingController _notes;
  String? _validation;

  @override
  void initState() {
    super.initState();
    _quantity = TextEditingController(text: widget.initial.quantity);
    _notes = TextEditingController(text: widget.initial.notes);
    for (final modifier in widget.initial.modifiers) {
      final optionId = int.tryParse('${modifier['option'] ?? ''}');
      if (optionId != null) {
        _modifierQuantities[optionId] =
            _tableCartNumber(modifier['quantity'] ?? 1).round();
      }
    }
  }

  @override
  void dispose() {
    _quantity.dispose();
    _notes.dispose();
    super.dispose();
  }

  double get _itemQuantity => _tableCartNumber(_quantity.text);

  void _setQuantity(double quantity) {
    if (quantity <= 0) return;
    setState(() {
      _quantity.text = _tableQuantityText(quantity);
      _validation = null;
    });
  }

  void _select(
      QuickSaleModifierGroup group, QuickSaleModifierOption option, bool value) {
    setState(() {
      if (value) {
        if (group.maxSelections == 1) {
          for (final candidate in group.options) {
            _modifierQuantities.remove(candidate.id);
          }
        }
        _modifierQuantities[option.id] = 1;
      } else {
        _modifierQuantities.remove(option.id);
      }
      _validation = null;
    });
  }

  void _increase(QuickSaleModifierGroup group, QuickSaleModifierOption option) {
    setState(() {
      if (group.maxSelections == 1) {
        for (final candidate in group.options) {
          _modifierQuantities.remove(candidate.id);
        }
      }
      _modifierQuantities[option.id] = (_modifierQuantities[option.id] ?? 0) + 1;
      _validation = null;
    });
  }

  void _decrease(QuickSaleModifierOption option) {
    setState(() {
      final current = _modifierQuantities[option.id] ?? 0;
      if (current <= 1) {
        _modifierQuantities.remove(option.id);
      } else {
        _modifierQuantities[option.id] = current - 1;
      }
      _validation = null;
    });
  }

  String? _groupValidation(QuickSaleModifierGroup group) {
    final selected = group.options
        .where((option) => _modifierQuantities.containsKey(option.id));
    final selections = selected.length;
    final total = selected.fold<double>(
        0, (sum, option) => sum + (_modifierQuantities[option.id] ?? 0));
    if (selections < group.minSelections ||
        (group.required && selections == 0)) {
      final missing = (group.minSelections - selections).clamp(1, 999);
      return 'Selecione mais $missing ${missing == 1 ? 'opção' : 'opções'} em ${group.name}.';
    }
    if (group.maxSelections != null && selections > group.maxSelections!) {
      return 'Remova opções em ${group.name} para respeitar o limite.';
    }
    final required = _tableCartNumber(group.requiredQuantity) * _itemQuantity;
    if (group.requiredQuantity != null && (total - required).abs() > .001) {
      return total < required
          ? 'Selecione mais ${_tableQuantityText(required - total)} unidade(s) em ${group.name}.'
          : 'Remova ${_tableQuantityText(total - required)} unidade(s) em ${group.name}.';
    }
    final minimum = _tableCartNumber(group.minTotalQuantity);
    if (minimum > 0 && total < minimum) {
      return 'Selecione mais ${_tableQuantityText(minimum - total)} unidade(s) em ${group.name}.';
    }
    final maximum = group.maxTotalQuantity == null
        ? null
        : _tableCartNumber(group.maxTotalQuantity);
    if (maximum != null && total > maximum) {
      return 'Remova ${_tableQuantityText(total - maximum)} unidade(s) em ${group.name}.';
    }
    return null;
  }

  void _save() {
    if (_itemQuantity <= 0) {
      setState(() => _validation = 'Informe uma quantidade válida.');
      return;
    }
    for (final group in widget.product.modifierGroups) {
      final validation = _groupValidation(group);
      if (validation != null) {
        setState(() => _validation = validation);
        return;
      }
    }
    Navigator.of(context).pop(widget.initial.copyWith(
      quantity: _tableQuantityText(_itemQuantity),
      notes: _notes.text.trim(),
      modifiers: _modifierQuantities.entries
          .map((entry) => <String, dynamic>{
                'option': entry.key,
                'quantity': '${entry.value}',
              })
          .toList(growable: false),
    ));
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text('Editar ${widget.product.name}'),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Row(children: [
                IconButton(
                  onPressed: () => _setQuantity(_itemQuantity - 1),
                  icon: const Icon(Icons.remove_circle_outline),
                  tooltip: 'Diminuir quantidade',
                ),
                Expanded(
                  child: TextField(
                    controller: _quantity,
                    textAlign: TextAlign.center,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    onChanged: (_) => setState(() => _validation = null),
                    decoration: const InputDecoration(labelText: 'Quantidade'),
                  ),
                ),
                IconButton(
                  onPressed: () => _setQuantity(_itemQuantity + 1),
                  icon: const Icon(Icons.add_circle_outline),
                  tooltip: 'Aumentar quantidade',
                ),
              ]),
              for (final group in widget.product.modifierGroups) ...[
                Align(
                  alignment: Alignment.centerLeft,
                  child: Padding(
                    padding: const EdgeInsets.only(top: 16),
                    child: Text(
                      '${group.name}${group.required ? ' *' : ''}',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                  ),
                ),
                for (final option in group.options)
                  Row(children: [
                    Expanded(
                      child: group.allowOptionQuantity
                          ? ListTile(
                              contentPadding: EdgeInsets.zero,
                              onTap: () => _increase(group, option),
                              title: Text(option.name),
                              subtitle: Text(
                                  '+ ${formatMoney(option.additionalPrice)}'),
                              leading: Icon(
                                _modifierQuantities.containsKey(option.id)
                                    ? Icons.add_circle
                                    : Icons.add_circle_outline,
                                color: const Color(0xff3454d1),
                              ),
                            )
                          : CheckboxListTile(
                              contentPadding: EdgeInsets.zero,
                              value: _modifierQuantities.containsKey(option.id),
                              onChanged: (value) =>
                                  _select(group, option, value ?? false),
                              title: Text(option.name),
                              subtitle: Text(
                                  '+ ${formatMoney(option.additionalPrice)}'),
                            ),
                    ),
                    if (group.allowOptionQuantity &&
                        _modifierQuantities.containsKey(option.id)) ...[
                      IconButton(
                        onPressed: () => _decrease(option),
                        icon: const Icon(Icons.remove),
                        tooltip: 'Diminuir ${option.name}',
                      ),
                      Text('${_modifierQuantities[option.id]}'),
                      IconButton(
                        onPressed: () => _increase(group, option),
                        icon: const Icon(Icons.add),
                        tooltip: 'Aumentar ${option.name}',
                      ),
                    ],
                  ]),
              ],
              TextField(
                controller: _notes,
                minLines: 2,
                maxLines: 4,
                maxLength: 1000,
                decoration: const InputDecoration(labelText: 'Observação'),
              ),
              if (_validation != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(_validation!,
                      style: const TextStyle(color: Colors.red)),
                ),
            ]),
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('CANCELAR')),
          FilledButton(onPressed: _save, child: const Text('SALVAR')),
        ],
      );
}

class _TableAttendancePicker extends StatelessWidget {
  const _TableAttendancePicker({required this.tables});

  final List<AttendanceTable> tables;

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Destino dos itens'),
        content: SizedBox(
          width: 360,
          child: tables.isEmpty
              ? const Text('Não há outra mesa aberta disponível.')
              : ListView(
                  shrinkWrap: true,
                  children: tables
                      .map((table) => ListTile(
                            leading: const Icon(Icons.table_restaurant_outlined),
                            title: Text(table.name),
                            subtitle: Text(
                                'Saldo: ${formatMoney(table.balance)}'),
                            onTap: () => Navigator.of(context).pop(table),
                          ))
                      .toList(growable: false),
                ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('CANCELAR'),
          ),
        ],
      );
}

class _TableCustomerPicker extends StatefulWidget {
  const _TableCustomerPicker({
    required this.controller,
    required this.canCreate,
    required this.canReactivate,
  });

  final AppController controller;
  final bool canCreate;
  final bool canReactivate;

  @override
  State<_TableCustomerPicker> createState() => _TableCustomerPickerState();
}

class _TableCustomerPickerState extends State<_TableCustomerPicker> {
  final _search = TextEditingController();
  List<QuickSaleCustomer> _customers = const [];
  QuickSaleCustomer? _inactiveCustomer;
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
    final result = await widget.controller.quickSaleCustomers(_search.text);
    if (!mounted) return;
    setState(() {
      _customers = result?.customers ?? const [];
      _inactiveCustomer = result?.inactiveIdentity;
      _loading = false;
    });
  }

  Future<void> _create() async {
    final customer = await showDialog<QuickSaleCustomer>(
      context: context,
      builder: (_) => _TableCustomerCreate(controller: widget.controller),
    );
    if (customer != null && mounted) Navigator.of(context).pop(customer);
  }

  Future<void> _reactivate() async {
    final customer = _inactiveCustomer;
    if (customer == null || !widget.canReactivate) return;
    final active = await widget.controller.activateQuickSaleCustomer(customer.id);
    if (active != null && mounted) Navigator.of(context).pop(active);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Pesquisar cliente'),
        content: SizedBox(
          width: 460,
          height: 400,
          child: Column(children: [
            TextField(
              controller: _search,
              onChanged: (_) => unawaited(_load()),
              decoration: const InputDecoration(
                labelText: 'Nome, telefone, documento ou e-mail',
                prefixIcon: Icon(Icons.search),
              ),
            ),
            if (_inactiveCustomer case final customer?)
              ListTile(
                leading: const Icon(Icons.person_off_outlined),
                title: Text(customer.name),
                subtitle: const Text('Cliente inativo'),
                trailing: widget.canReactivate
                    ? TextButton(
                        onPressed: _reactivate,
                        child: const Text('REATIVAR'),
                      )
                    : null,
              ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : ListView.builder(
                      itemCount: _customers.length,
                      itemBuilder: (_, index) {
                        final customer = _customers[index];
                        return ListTile(
                          title: Text(customer.name),
                          subtitle: Text([
                            if (customer.phone.isNotEmpty) customer.phone,
                            if (customer.document.isNotEmpty) customer.document,
                          ].join(' | ')),
                          onTap: () => Navigator.of(context).pop(customer),
                        );
                      },
                    ),
            ),
          ]),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('CANCELAR'),
          ),
          if (widget.canCreate)
            FilledButton.icon(
              onPressed: _create,
              icon: const Icon(Icons.person_add_alt_1),
              label: const Text('ADICIONAR'),
            ),
        ],
      );
}

class _TableCustomerCreate extends StatefulWidget {
  const _TableCustomerCreate({required this.controller});

  final AppController controller;

  @override
  State<_TableCustomerCreate> createState() => _TableCustomerCreateState();
}

class _TableCustomerCreateState extends State<_TableCustomerCreate> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  final _document = TextEditingController();
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _document.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_saving || _name.text.trim().isEmpty || _phone.text.trim().isEmpty) {
      return;
    }
    setState(() => _saving = true);
    QuickSaleCustomer? customer;
    try {
      customer = await widget.controller.createQuickSaleCustomer(
        name: _name.text.trim(),
        phone: _phone.text.trim(),
        document: _document.text.trim(),
      );
    } on PosApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
    if (!mounted) return;
    setState(() => _saving = false);
    if (customer != null) Navigator.of(context).pop(customer);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Adicionar cliente'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
            controller: _name,
            autofocus: true,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(labelText: 'Nome *'),
          ),
          TextField(
            controller: _phone,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(labelText: 'Telefone *'),
          ),
          TextField(
            controller: _document,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'CPF'),
          ),
        ]),
        actions: [
          TextButton(
            onPressed: _saving ? null : () => Navigator.of(context).pop(),
            child: const Text('CANCELAR'),
          ),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: Text(_saving ? 'SALVANDO...' : 'SALVAR'),
          ),
        ],
      );
}

Future<String?> _requiredReasonDialog(BuildContext context, String title) async {
  final controller = TextEditingController();
  var showError = false;
  final result = await showDialog<String>(
    context: context,
    builder: (_) => StatefulBuilder(
      builder: (context, setDialogState) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 2,
          decoration: InputDecoration(
            labelText: 'Motivo *',
            errorText: showError ? 'Informe o motivo do cancelamento.' : null,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('VOLTAR'),
          ),
          FilledButton(
            onPressed: () {
              final reason = controller.text.trim();
              if (reason.isEmpty) {
                setDialogState(() => showError = true);
                return;
              }
              Navigator.of(context).pop(reason);
            },
            child: const Text('CONFIRMAR'),
          ),
        ],
      ),
    ),
  );
  controller.dispose();
  return result;
}
