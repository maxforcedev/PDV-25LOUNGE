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
import 'table_summary_widgets.dart';

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
    final reason =
        await _requiredReasonDialog(context, 'Cancelar pedido #${order.id}');
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

  Future<void> _setCheckoutContext({String? discount, bool? waiveFee}) async {
    if (_actionInProgress) return;
    setState(() => _actionInProgress = true);
    final updated = await widget.controller.setTableCheckoutContext(
      attendanceId: _attendance.id,
      discount: discount ?? _attendance.checkoutDiscount,
      serviceFeeWaived: waiveFee ?? _attendance.checkoutServiceFeeWaived,
      idempotencyKey: createIdempotencyKey(),
    );
    if (!mounted) return;
    setState(() => _actionInProgress = false);
    if (updated != null) await _load();
  }

  Future<void> _editDiscount() async {
    final controller =
        TextEditingController(text: _attendance.checkoutDiscount);
    final value = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Desconto da mesa'),
        content: TextField(
          controller: controller,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Valor do desconto'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('CANCELAR')),
          FilledButton(
              onPressed: () => Navigator.pop(
                  context, controller.text.trim().replaceAll(',', '.')),
              child: const Text('SALVAR')),
        ],
      ),
    );
    controller.dispose();
    if (value != null && value.isNotEmpty) {
      await _setCheckoutContext(discount: value);
    }
  }

  void _showCustomer() {
    showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Cliente'),
        content: Text([
          _attendance.customerName,
          if (_attendance.customerId != null)
            'Código: ${_attendance.customerId}',
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
                              if (_can('tables.set_customer'))
                                TextButton(
                                  onPressed: _actionInProgress
                                      ? null
                                      : _selectCustomer,
                                  child: Text(_attendance.customerId == null
                                      ? 'PESQUISAR'
                                      : 'TROCAR'),
                                ),
                              if (_attendance.customerId != null &&
                                  _can('tables.set_customer'))
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
                                onPressed:
                                    _actionInProgress ? null : _toggleBill,
                                icon: Icon(_attendance.billRequested
                                    ? Icons.remove_done_outlined
                                    : Icons.request_quote_outlined),
                                label: Text(_attendance.billRequested
                                    ? 'CANCELAR SOLICITAÇÃO'
                                    : 'SOLICITAR CONTA'),
                              ),
                            ),
                          if (_attendance.status == 'open' &&
                              _can('sales.apply_discount'))
                            Wrap(spacing: 8, children: [
                              OutlinedButton(
                                  onPressed:
                                      _actionInProgress ? null : _editDiscount,
                                  child: Text(
                                      _attendance.checkoutDiscount == '0.00'
                                          ? 'APLICAR DESCONTO'
                                          : 'ALTERAR DESCONTO')),
                              if (_attendance.checkoutDiscount != '0.00')
                                OutlinedButton(
                                    onPressed: _actionInProgress
                                        ? null
                                        : () => _setCheckoutContext(
                                            discount: '0.00'),
                                    child: const Text('REMOVER DESCONTO')),
                            ]),
                          if (_attendance.status == 'open' &&
                              _can('sales.waive_service_fee'))
                            OutlinedButton(
                              onPressed: _actionInProgress
                                  ? null
                                  : () => _setCheckoutContext(
                                      waiveFee: !_attendance
                                          .checkoutServiceFeeWaived),
                              child: Text(_attendance.checkoutServiceFeeWaived
                                  ? 'RESTAURAR TAXA'
                                  : 'REMOVER TAXA'),
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
                                                    ? _selectedItems
                                                        .add(item.id)
                                                    : _selectedItems
                                                        .remove(item.id)),
                                      ),
                                    if (item.status == 'confirmed' &&
                                        _can('tables.cancel_items'))
                                      Align(
                                        alignment: Alignment.centerRight,
                                        child: TextButton.icon(
                                          onPressed: _actionInProgress
                                              ? null
                                              : () => _cancelItem(item),
                                          icon:
                                              const Icon(Icons.cancel_outlined),
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
                                  icon: const Icon(
                                      Icons.cancel_presentation_outlined),
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
  late TableAttendance _attendance = widget.attendance;
  final _search = TextEditingController();
  final _cartListenable = ValueNotifier<int>(0);
  List<QuickSaleProduct> _catalog = const [];
  final List<QuickSaleCartItem> _cart = [];
  int? _categoryId;
  bool _favoritesOnly = false;
  bool _loading = true;
  bool _saving = false;
  bool _actionInProgress = false;
  bool _previewLoading = false;
  String? _orderIdempotencyKey;
  Map<String, dynamic>? _preview;
  AttendanceTableGroup? _group;
  Timer? _previewDebounce;
  int _previewRequestVersion = 0;
  Future<void> _cartMutationQueue = Future.value();

  @override
  void initState() {
    super.initState();
    _search.addListener(() => setState(() {}));
    unawaited(_load());
  }

  @override
  void dispose() {
    _previewDebounce?.cancel();
    _search.dispose();
    _cartListenable.dispose();
    super.dispose();
  }

  bool _can(String permission) =>
      widget.controller.bootstrapSnapshot?.permissions.contains(permission) ==
      true;

  Future<void> _load() async {
    setState(() => _loading = true);
    final results = await Future.wait<Object?>([
      widget.controller.tableCatalog(),
      widget.controller.tableAttendanceDetail(widget.attendance.id),
      widget.controller.attendanceTables(),
    ]);
    if (!mounted) return;
    final attendance = results[1] as TableAttendance? ?? _attendance;
    final tables = results[2] as List<AttendanceTable>?;
    setState(() {
      _catalog = results[0] as List<QuickSaleProduct>? ?? const [];
      _attendance = attendance;
      _group = tables
          ?.where((table) => table.id == attendance.tableId)
          .firstOrNull
          ?.group;
      _loading = false;
    });
    _notifyCartChanged();
    _schedulePreview();
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
    if (_requiresConfiguration(product)) {
      await _editNewItem(product, item);
      return;
    }
    await _addCartItem(item);
  }

  bool _requiresConfiguration(QuickSaleProduct product) =>
      product.modifierGroups.any(
        (group) =>
            group.required ||
            group.minSelections > 0 ||
            _tableCartNumber(group.minTotalQuantity) > 0 ||
            group.requiredQuantity != null,
      );

  Future<void> _editNewItem(
      QuickSaleProduct product, QuickSaleCartItem item) async {
    final configured = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) =>
          _TableSaleItemEditorDialog(product: product, initial: item),
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
            double.tryParse(cart[equivalent].quantity.replaceAll(',', '.')) ??
                0;
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
          items: _tableAvailabilityPayload(candidate),
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
      _schedulePreview();
    });
  }

  Future<T> _queueCartTask<T>(FutureOr<T> Function() task) {
    final queued = _cartMutationQueue.then((_) => task());
    _cartMutationQueue = queued.then<void>((_) {}, onError: (_, __) {});
    return queued;
  }

  List<Map<String, dynamic>> _tableOrderPayload(List<QuickSaleCartItem> cart) =>
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

  List<Map<String, dynamic>> _tableAvailabilityPayload(
          List<QuickSaleCartItem> cart) =>
      cart
          .map((item) => <String, dynamic>{
                'client_item_id': item.clientItemId,
                ..._tableOrderPayload([item]).single,
              })
          .toList(growable: false);

  void _notifyCartChanged() => _cartListenable.value++;

  void _schedulePreview() {
    _previewDebounce?.cancel();
    final requestVersion = ++_previewRequestVersion;
    if (_cart.isEmpty) {
      if (_preview != null || _previewLoading) {
        setState(() {
          _preview = null;
          _previewLoading = false;
        });
      }
      return;
    }
    setState(() => _previewLoading = true);
    _previewDebounce = Timer(const Duration(milliseconds: 250), () async {
      if (!mounted) return;
      final preview = await widget.controller.tableOrderPreview(
        attendanceId: _attendance.id,
        items: _tableAvailabilityPayload(List<QuickSaleCartItem>.from(_cart)),
      );
      if (!mounted || requestVersion != _previewRequestVersion) return;
      setState(() {
        if (preview != null) _preview = preview;
        _previewLoading = false;
      });
    });
  }

  void _showStockUnavailable(
      QuickSaleStockAvailability availability, List<QuickSaleCartItem> cart) {
    final available = availability.availableQuantity;
    final shortage = availability.shortages.firstOrNull;
    final item = shortage == null
        ? null
        : cart
            .where((entry) =>
                '${entry.product.id}' ==
                '${shortage['product'] ?? shortage['product_id']}')
            .firstOrNull;
    final requested = item?.quantity;
    final message = available == null
        ? 'Este produto não possui estoque suficiente para essa quantidade.'
        : requested == null
            ? 'Só temos $available disponíveis deste produto.'
            : 'Você tentou adicionar $requested, mas há somente $available disponíveis.';
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
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

  int get _itemCount =>
      _attendance.orders
          .fold<int>(0, (count, order) => count + order.items.length) +
      _cart.length;

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
        total: () => formatMoney(
            '${_preview?['total'] ?? _attendance.summary['total_due'] ?? '0.00'}'),
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
        final snapshotCart = List<QuickSaleCartItem>.from(_cart);
        final availability = await widget.controller.tableStockAvailability(
          items: _tableAvailabilityPayload(snapshotCart),
        );
        if (!mounted || availability == null) return false;
        if (!availability.available && availability.enforced) {
          _showStockUnavailable(availability, _cart);
          return false;
        }
        final idempotencyKey = _orderIdempotencyKey ??= createIdempotencyKey();
        return (await widget.controller.saveTableOrder(
              attendanceId: _attendance.id,
              idempotencyKey: idempotencyKey,
              items: _tableOrderPayload(snapshotCart),
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
    await _load();
    if (!mounted) return;
    setState(() {
      _cart.clear();
      _orderIdempotencyKey = null;
    });
    _notifyCartChanged();
    _schedulePreview();
  }

  Future<QuickSaleAuthorization?> _requestAuthorization(String type) async {
    final authorizers = switch (type) {
      'item' => await widget.controller.quickSaleItemDiscountAuthorizers(),
      'service_fee' => await widget.controller.quickSaleServiceFeeAuthorizers(),
      _ => await widget.controller.quickSaleDiscountAuthorizers(),
    };
    if (!mounted || authorizers == null) return null;
    if (authorizers.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content:
            Text('Nenhum autorizador elegível está disponível nesta filial.'),
      ));
      return null;
    }
    return showDialog<QuickSaleAuthorization>(
      context: context,
      builder: (_) => _TableAuthorizationDialog(
        authorizers: authorizers,
        onAuthorize: (authorization) =>
            widget.controller.validateQuickSaleDiscountAuthorization(
          type: type,
          authorization: authorization,
        ),
      ),
    );
  }

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
    final reason =
        await _requiredReasonDialog(context, 'Cancelar pedido #${order.id}');
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

  Future<void> _transferItems([List<TableOrderItem>? selected]) async {
    if (_actionInProgress) return;
    final eligible = _attendance.orders
        .expand((order) => order.items)
        .where((item) => item.status == 'confirmed')
        .toList(growable: false);
    final items = selected ??
        await showDialog<List<TableOrderItem>>(
          context: context,
          builder: (_) => _TableItemTransferPicker(items: eligible),
        );
    if (items == null || items.isEmpty || !mounted) return;
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
    setState(() => _actionInProgress = true);
    final moved = await widget.controller.transferTableItems(
      attendanceId: _attendance.id,
      destinationAttendanceId: target!.attendance!.id,
      items: items
          .map((item) => {'item': item.id, 'quantity': item.quantity})
          .toList(growable: false),
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

  Future<void> _manageCustomer() async {
    final action = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Cliente'),
        content: Text(_attendance.customerName.isEmpty
            ? 'Nenhum cliente'
            : _attendance.customerName),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('VOLTAR'),
          ),
          if (_attendance.customerId != null && _can('customers.view'))
            TextButton(
              onPressed: () => Navigator.of(context).pop('view'),
              child: const Text('VER'),
            ),
          if (_can('tables.set_customer') && _can('customers.view'))
            TextButton(
              onPressed: () => Navigator.of(context).pop('select'),
              child:
                  Text(_attendance.customerId == null ? 'PESQUISAR' : 'TROCAR'),
            ),
          if (_attendance.customerId == null &&
              _can('tables.set_customer') &&
              _can('customers.add'))
            TextButton(
              onPressed: () => Navigator.of(context).pop('create'),
              child: const Text('ADICIONAR'),
            ),
          if (_attendance.customerId != null && _can('tables.set_customer'))
            FilledButton(
              onPressed: () => Navigator.of(context).pop('remove'),
              child: const Text('REMOVER'),
            ),
        ],
      ),
    );
    if (!mounted || action == null) return;
    if (action == 'view') {
      await showDialog<void>(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Cliente'),
          content: Text([
            _attendance.customerName,
            if (_attendance.customerId != null)
              'Código: ${_attendance.customerId}',
          ].join('\n')),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('FECHAR'),
            ),
          ],
        ),
      );
    } else if (action == 'remove') {
      await _setCustomer(null);
    } else {
      final customer = action == 'create'
          ? await showDialog<QuickSaleCustomer>(
              context: context,
              builder: (_) =>
                  _TableCustomerCreate(controller: widget.controller),
            )
          : await showDialog<QuickSaleCustomer>(
              context: context,
              builder: (_) => _TableCustomerPicker(
                controller: widget.controller,
                canCreate: _can('customers.add'),
                canReactivate: _can('customers.change'),
              ),
            );
      if (customer != null && mounted) await _setCustomer(customer.id);
    }
  }

  Future<void> _setCheckoutContext({
    String? discount,
    bool? waiveFee,
    QuickSaleAuthorization? discountAuthorization,
    QuickSaleAuthorization? serviceFeeAuthorization,
  }) async {
    if (_actionInProgress) return;
    setState(() => _actionInProgress = true);
    final updated = await widget.controller.setTableCheckoutContext(
      attendanceId: _attendance.id,
      discount: discount ?? _attendance.checkoutDiscount,
      serviceFeeWaived: waiveFee ?? _attendance.checkoutServiceFeeWaived,
      idempotencyKey: createIdempotencyKey(),
      discountAuthorization: discountAuthorization?.toJson(),
      serviceFeeAuthorization: serviceFeeAuthorization?.toJson(),
    );
    if (!mounted) return;
    setState(() => _actionInProgress = false);
    if (updated != null) await _load();
  }

  Future<void> _manageCheckoutDiscount() async {
    final action = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Desconto da mesa'),
        content: Text(_attendance.checkoutDiscount == '0.00'
            ? 'Nenhum desconto aplicado.'
            : 'Desconto atual: ${formatMoney(_attendance.checkoutDiscount)}'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('VOLTAR'),
          ),
          if (_attendance.checkoutDiscount != '0.00')
            TextButton(
              onPressed: () => Navigator.of(context).pop('remove'),
              child: const Text('REMOVER'),
            ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop('edit'),
            child: Text(_attendance.checkoutDiscount == '0.00'
                ? 'APLICAR DESCONTO'
                : 'ALTERAR'),
          ),
        ],
      ),
    );
    if (!mounted || action == null) return;
    if (action == 'remove') {
      await _setCheckoutContext(discount: '0.00');
      return;
    }
    final controller =
        TextEditingController(text: _attendance.checkoutDiscount);
    final discount = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Desconto da mesa'),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: const InputDecoration(labelText: 'Valor do desconto'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('CANCELAR'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context)
                .pop(controller.text.trim().replaceAll(',', '.')),
            child: const Text('SALVAR'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (discount == null || discount.isEmpty || !mounted) return;
    final authorization = _can('sales.apply_discount')
        ? null
        : await _requestAuthorization('sale');
    if (!mounted || (!_can('sales.apply_discount') && authorization == null)) {
      return;
    }
    await _setCheckoutContext(
      discount: discount,
      discountAuthorization: authorization,
    );
  }

  Future<void> _toggleServiceFee() async {
    final waiveFee = !_attendance.checkoutServiceFeeWaived;
    final authorization = waiveFee && !_can('sales.waive_service_fee')
        ? await _requestAuthorization('service_fee')
        : null;
    if (!mounted ||
        (waiveFee &&
            !_can('sales.waive_service_fee') &&
            authorization == null)) {
      return;
    }
    await _setCheckoutContext(
      waiveFee: waiveFee,
      serviceFeeAuthorization: authorization,
    );
  }

  Future<void> _editItemDiscount(TableOrderItem item) async {
    final discount = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (_) => const _TableItemDiscountDialog(),
    );
    if (discount == null || !mounted) return;
    final authorization = _can('sales.apply_item_discount')
        ? null
        : await _requestAuthorization('item');
    if (!mounted ||
        (!_can('sales.apply_item_discount') && authorization == null) ||
        _actionInProgress) {
      return;
    }
    setState(() => _actionInProgress = true);
    final updated = await widget.controller.setTableOrderItemDiscount(
      itemId: item.id,
      discount: discount,
      idempotencyKey: createIdempotencyKey(),
      authorization: authorization?.toJson(),
    );
    if (!mounted) return;
    setState(() => _actionInProgress = false);
    if (updated != null) await _load();
  }

  Future<bool> _confirmDiscardDraft() async =>
      await showDialog<bool>(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Descartar itens novos?'),
          content: const Text('Os itens ainda não enviados serão removidos.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('CONTINUAR EDITANDO'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('DESCARTAR'),
            ),
          ],
        ),
      ) ??
      false;

  @override
  Widget build(BuildContext context) => PopScope(
        canPop: _cart.isEmpty && !_saving,
        onPopInvokedWithResult: (didPop, _) async {
          if (didPop || _cart.isEmpty || _saving) return;
          if (await _confirmDiscardDraft() && mounted) {
            setState(() => _cart.clear());
            _notifyCartChanged();
            Navigator.of(this.context).pop();
          }
        },
        child: Scaffold(
          appBar: AppBar(title: Text(_attendance.tableName), actions: [
            if (_attendance.billRequested)
              const Padding(
                padding: EdgeInsets.only(right: 8),
                child: Center(
                    child: Text('CONTA SOLICITADA',
                        style: TextStyle(
                            fontSize: 11, fontWeight: FontWeight.w800))),
              ),
          ]),
          bottomNavigationBar: MediaQuery.sizeOf(context).width < 900
              ? ValueListenableBuilder<int>(
                  valueListenable: _cartListenable,
                  builder: (_, __, ___) => _TableMobileSummaryBar(
                    total: _preview == null
                        ? '${_attendance.summary['total_due'] ?? '0.00'}'
                        : '${_preview!['total']}',
                    updating: _saving || _previewLoading,
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
                                  attendance: _attendance,
                                  saving: _saving,
                                  onEdit: _edit,
                                  onRemove: (index) =>
                                      unawaited(_remove(index)),
                                  onSave: _save,
                                  onConference: _showConference,
                                  preview: _preview,
                                  previewLoading: _previewLoading,
                                  actionsInProgress: _actionInProgress,
                                  canManageCustomer: _can('customers.view') ||
                                      _can('tables.set_customer'),
                                  canCancelItems: _can('tables.cancel_items'),
                                  canTransferItems:
                                      _can('tables.transfer_items'),
                                  canRequestBill: _can('tables.close'),
                                  canSeparateFromGroup:
                                      _group != null && _can('tables.merge'),
                                  onCustomer: _manageCustomer,
                                  onCheckoutDiscount: _manageCheckoutDiscount,
                                  onServiceFee: _toggleServiceFee,
                                  onBill: _toggleBill,
                                  onTransferItems: _transferItems,
                                  onSeparateFromGroup: _separateFromGroup,
                                  onCancelItem: _cancelItem,
                                  onTransferItem: (item) =>
                                      _transferItems([item]),
                                  onItemDiscount: _editItemDiscount,
                                  onCancelOrder: _cancelOrder,
                                ))),
                  ]);
                }),
        ),
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
        appBar: AppBar(title: Text(_attendance.tableName)),
        body: ValueListenableBuilder<int>(
          valueListenable: _cartListenable,
          builder: (_, __, ___) => _TableOrderSummaryPanel(
            cart: _cart,
            attendance: _attendance,
            saving: _saving,
            onEdit: _edit,
            onRemove: (index) => unawaited(_remove(index)),
            onSave: _save,
            onConference: _showConference,
            preview: _preview,
            previewLoading: _previewLoading,
            actionsInProgress: _actionInProgress,
            canManageCustomer:
                _can('customers.view') || _can('tables.set_customer'),
            canCancelItems: _can('tables.cancel_items'),
            canTransferItems: _can('tables.transfer_items'),
            canRequestBill: _can('tables.close'),
            canSeparateFromGroup: _group != null && _can('tables.merge'),
            onCustomer: _manageCustomer,
            onCheckoutDiscount: _manageCheckoutDiscount,
            onServiceFee: _toggleServiceFee,
            onBill: _toggleBill,
            onTransferItems: _transferItems,
            onSeparateFromGroup: _separateFromGroup,
            onCancelItem: _cancelItem,
            onTransferItem: (item) => _transferItems([item]),
            onItemDiscount: _editItemDiscount,
            onCancelOrder: _cancelOrder,
          ),
        ),
      ),
    ));
    if (saved == true && mounted) await _load();
  }

  Future<void> _showConference() async {
    if (_cart.isNotEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text(
            'Existem itens ainda não enviados. Envie o pedido antes de gerar a conferência.'),
      ));
      return;
    }
    await showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(_attendance.tableName),
        content: SizedBox(
            width: 360,
            child: SingleChildScrollView(
                child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text('CONFERÊNCIA SEM VALOR FISCAL',
                    style: TextStyle(fontWeight: FontWeight.w800)),
                Text(_attendance.tableName),
                if (_attendance.openedAt != null)
                  Text(_tableHistoryTime(_attendance.openedAt)),
                if (_attendance.responsibleName.isNotEmpty)
                  Text('Atendente: ${_attendance.responsibleName}'),
                const Divider(),
                for (final order in _attendance.orders)
                  for (final item in order.items)
                    if (item.status == 'confirmed')
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Column(children: [
                          Row(children: [
                            Expanded(
                                child: Text(
                                    '${item.quantity}x ${item.productName}')),
                            Text(formatMoney(item.lineTotal ?? item.unitPrice))
                          ]),
                          for (final modifier in item.modifierSnapshot)
                            Align(
                                alignment: Alignment.centerLeft,
                                child: Text(
                                    '+ ${modifier['name'] ?? modifier['option_name'] ?? 'Modificador'}')),
                          if (item.notes.isNotEmpty)
                            Align(
                                alignment: Alignment.centerLeft,
                                child: Text('Obs: ${item.notes}')),
                        ]),
                      ),
                const Divider(),
                TableSummaryWidgets(_attendance.summary),
                if (_attendance.customerName.isNotEmpty)
                  Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Text('Cliente: ${_attendance.customerName}')),
              ],
            ))),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('FECHAR'))
        ],
      ),
    );
  }
}

class _TableOrderSummaryPanel extends StatelessWidget {
  const _TableOrderSummaryPanel(
      {required this.cart,
      required this.attendance,
      required this.saving,
      required this.onEdit,
      required this.onRemove,
      required this.onSave,
      required this.onConference,
      required this.preview,
      required this.previewLoading,
      required this.actionsInProgress,
      required this.canManageCustomer,
      required this.canCancelItems,
      required this.canTransferItems,
      required this.canRequestBill,
      required this.canSeparateFromGroup,
      required this.onCustomer,
      required this.onCheckoutDiscount,
      required this.onServiceFee,
      required this.onBill,
      required this.onTransferItems,
      required this.onSeparateFromGroup,
      required this.onCancelItem,
      required this.onTransferItem,
      required this.onItemDiscount,
      required this.onCancelOrder});
  final List<QuickSaleCartItem> cart;
  final TableAttendance attendance;
  final bool saving;
  final ValueChanged<int> onEdit;
  final ValueChanged<int> onRemove;
  final Future<void> Function() onSave;
  final Future<void> Function() onConference;
  final Map<String, dynamic>? preview;
  final bool previewLoading;
  final bool actionsInProgress;
  final bool canManageCustomer;
  final bool canCancelItems;
  final bool canTransferItems;
  final bool canRequestBill;
  final bool canSeparateFromGroup;
  final Future<void> Function() onCustomer;
  final Future<void> Function() onCheckoutDiscount;
  final Future<void> Function() onServiceFee;
  final Future<void> Function() onBill;
  final Future<void> Function() onTransferItems;
  final Future<void> Function() onSeparateFromGroup;
  final Future<void> Function(TableOrderItem) onCancelItem;
  final Future<void> Function(TableOrderItem) onTransferItem;
  final Future<void> Function(TableOrderItem) onItemDiscount;
  final Future<void> Function(TableOrder) onCancelOrder;

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.white,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              Expanded(
                  child: Text('RESUMO DA MESA',
                      style: Theme.of(context)
                          .textTheme
                          .titleMedium
                          ?.copyWith(fontWeight: FontWeight.w800))),
              PopupMenuButton<String>(
                onSelected: (value) {
                  switch (value) {
                    case 'customer':
                      unawaited(onCustomer());
                      break;
                    case 'discount':
                      unawaited(onCheckoutDiscount());
                      break;
                    case 'service_fee':
                      unawaited(onServiceFee());
                      break;
                    case 'conference':
                      unawaited(onConference());
                      break;
                    case 'bill':
                      unawaited(onBill());
                      break;
                    case 'transfer':
                      unawaited(onTransferItems());
                      break;
                    case 'separate':
                      unawaited(onSeparateFromGroup());
                      break;
                  }
                },
                itemBuilder: (_) => [
                  if (canManageCustomer)
                    const PopupMenuItem(
                        value: 'customer', child: Text('CLIENTE')),
                  if (attendance.status == 'open') ...[
                    const PopupMenuItem(
                        value: 'discount', child: Text('DESCONTO')),
                    PopupMenuItem(
                      value: 'service_fee',
                      child: Text(attendance.checkoutServiceFeeWaived
                          ? 'RESTAURAR TAXA'
                          : 'REMOVER TAXA'),
                    ),
                  ],
                  const PopupMenuItem(
                    value: 'conference',
                    child: Text('VISUALIZAR CONFERÊNCIA'),
                  ),
                  if (attendance.status == 'open' && canRequestBill)
                    PopupMenuItem(
                      value: 'bill',
                      child: Text(attendance.billRequested
                          ? 'CANCELAR SOLICITAÇÃO'
                          : 'SOLICITAR CONTA'),
                    ),
                  if (attendance.status == 'open' &&
                      canTransferItems &&
                      attendance.orders
                          .expand((order) => order.items)
                          .any((item) => item.status == 'confirmed'))
                    const PopupMenuItem(
                      value: 'transfer',
                      child: Text('TRANSFERIR ITENS'),
                    ),
                  if (attendance.status == 'open' && canSeparateFromGroup)
                    const PopupMenuItem(
                      value: 'separate',
                      child: Text('SEPARAR DO GRUPO'),
                    ),
                ],
                enabled: !actionsInProgress,
              ),
            ]),
            const SizedBox(height: 8),
            Expanded(
                child: cart.isEmpty && attendance.orders.isEmpty
                    ? const Center(
                        child: Text('Adicione produtos para iniciar o pedido.'))
                    : ListView(children: [
                        for (final order in attendance.orders) ...[
                          Padding(
                            padding: const EdgeInsets.only(top: 8),
                            child: Row(children: [
                              Expanded(
                                child: Text('PEDIDO #${order.id}',
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w800)),
                              ),
                              if (order.status == 'confirmed' && canCancelItems)
                                PopupMenuButton<String>(
                                  enabled: !actionsInProgress,
                                  onSelected: (_) =>
                                      unawaited(onCancelOrder(order)),
                                  itemBuilder: (_) => const [
                                    PopupMenuItem(
                                      value: 'cancel',
                                      child: Text('CANCELAR PEDIDO'),
                                    ),
                                  ],
                                ),
                            ]),
                          ),
                          for (final item in order.items)
                            ListTile(
                              title:
                                  Text('${item.quantity}x ${item.productName}'),
                              subtitle: Text([
                                item.status.toUpperCase(),
                                for (final modifier in item.modifierSnapshot)
                                  '+ ${modifier['name'] ?? modifier['option_name'] ?? 'Modificador'}',
                                if (item.notes.isNotEmpty) 'Obs: ${item.notes}',
                                if (item.cancellationReason.isNotEmpty)
                                  'Cancelado: ${item.cancellationReason}',
                              ].join('\n')),
                              trailing: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text(formatMoney(
                                        item.lineTotal ?? item.unitPrice)),
                                    if (item.status == 'confirmed')
                                      PopupMenuButton<String>(
                                        enabled: !actionsInProgress,
                                        onSelected: (value) {
                                          switch (value) {
                                            case 'cancel':
                                              unawaited(onCancelItem(item));
                                              break;
                                            case 'transfer':
                                              unawaited(onTransferItem(item));
                                              break;
                                            case 'discount':
                                              unawaited(onItemDiscount(item));
                                              break;
                                          }
                                        },
                                        itemBuilder: (_) => [
                                          if (canCancelItems)
                                            const PopupMenuItem(
                                              value: 'cancel',
                                              child: Text('CANCELAR ITEM'),
                                            ),
                                          if (canTransferItems)
                                            const PopupMenuItem(
                                              value: 'transfer',
                                              child: Text('TRANSFERIR'),
                                            ),
                                          const PopupMenuItem(
                                            value: 'discount',
                                            child: Text('DESCONTO DO ITEM'),
                                          ),
                                        ],
                                      ),
                                  ]),
                            ),
                          const Divider(height: 1),
                        ],
                        if (cart.isNotEmpty) ...[
                          const Padding(
                            padding: EdgeInsets.only(top: 12, bottom: 4),
                            child: Text('NOVOS ITENS',
                                style: TextStyle(fontWeight: FontWeight.w800)),
                          ),
                          for (var draftIndex = 0;
                              draftIndex < cart.length;
                              draftIndex++)
                            _TableDraftItemTile(
                              item: cart[draftIndex],
                              saving: saving,
                              onEdit: () => onEdit(draftIndex),
                              onRemove: () => onRemove(draftIndex),
                            ),
                        ],
                      ])),
            const SizedBox(height: 12),
            if (previewLoading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 4),
                child: LinearProgressIndicator(),
              )
            else if (preview != null)
              Text(
                'Total projetado: ${formatMoney('${preview!['total']}')}',
                textAlign: TextAlign.end,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
            const SizedBox(height: 4),
            TableSummaryWidgets(attendance.summary),
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

class _TableDraftItemTile extends StatelessWidget {
  const _TableDraftItemTile({
    required this.item,
    required this.saving,
    required this.onEdit,
    required this.onRemove,
  });

  final QuickSaleCartItem item;
  final bool saving;
  final VoidCallback onEdit;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) => ListTile(
        onTap: saving ? null : onEdit,
        title: Text(item.product.name),
        subtitle: Text([
          'Qtd. ${item.quantity}',
          for (final modifier in item.modifiers)
            _tableModifierText(item.product, modifier),
          if (item.notes.isNotEmpty) 'Obs: ${item.notes}',
        ].join('\n')),
        leading: SizedBox(
          width: 76,
          child: Text(
            formatMoney(_tableLineTotal(item).toStringAsFixed(2)),
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
        ),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          IconButton(
            onPressed: saving ? null : onRemove,
            icon: const Icon(Icons.delete_outline),
          ),
          const Icon(Icons.chevron_right),
        ]),
      );
}

class _TableAuthorizationDialog extends StatefulWidget {
  const _TableAuthorizationDialog({
    required this.authorizers,
    required this.onAuthorize,
  });

  final List<QuickSaleAuthorizer> authorizers;
  final Future<String?> Function(QuickSaleAuthorization authorization)
      onAuthorize;

  @override
  State<_TableAuthorizationDialog> createState() =>
      _TableAuthorizationDialogState();
}

class _TableAuthorizationDialogState extends State<_TableAuthorizationDialog> {
  final _pin = TextEditingController();
  int? _authorizerId;
  bool _validating = false;
  String? _error;

  Future<void> _authorize() async {
    if (_authorizerId == null || _pin.text.length != 6 || _validating) return;
    setState(() {
      _validating = true;
      _error = null;
    });
    final authorization = QuickSaleAuthorization(
      userId: _authorizerId!,
      credential: _pin.text,
    );
    final error = await widget.onAuthorize(authorization);
    _pin.clear();
    if (!mounted) return;
    if (error == null) {
      Navigator.of(context).pop(authorization);
      return;
    }
    setState(() {
      _validating = false;
      _error = error;
    });
  }

  @override
  void dispose() {
    _pin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('AUTORIZAÇÃO NECESSÁRIA'),
        content: SizedBox(
          width: 360,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            DropdownButtonFormField<int>(
              initialValue: _authorizerId,
              isExpanded: true,
              decoration: const InputDecoration(labelText: 'Autorizador'),
              items: widget.authorizers
                  .map((authorizer) => DropdownMenuItem(
                        value: authorizer.id,
                        child: Text(authorizer.displayName,
                            overflow: TextOverflow.ellipsis),
                      ))
                  .toList(growable: false),
              onChanged: (value) => setState(() {
                _authorizerId = value;
                _pin.clear();
                _error = null;
              }),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _pin,
              autofocus: true,
              obscureText: true,
              keyboardType: TextInputType.number,
              maxLength: 6,
              enableSuggestions: false,
              autocorrect: false,
              onChanged: (value) {
                if (!RegExp(r'^\d{0,6}$').hasMatch(value)) _pin.clear();
                setState(() {});
              },
              decoration: InputDecoration(
                labelText: 'PIN do autorizador',
                errorText: _error,
              ),
            ),
          ]),
        ),
        actions: [
          TextButton(
            onPressed: _validating ? null : () => Navigator.of(context).pop(),
            child: const Text('VOLTAR'),
          ),
          FilledButton(
            onPressed:
                _authorizerId == null || _pin.text.length != 6 || _validating
                    ? null
                    : _authorize,
            child: Text(_validating ? 'VALIDANDO...' : 'AUTORIZAR'),
          ),
        ],
      );
}

class _TableItemDiscountDialog extends StatefulWidget {
  const _TableItemDiscountDialog();

  @override
  State<_TableItemDiscountDialog> createState() =>
      _TableItemDiscountDialogState();
}

class _TableItemDiscountDialogState extends State<_TableItemDiscountDialog> {
  final _value = TextEditingController();
  String _type = 'amount';

  @override
  void dispose() {
    _value.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Desconto do item'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'amount', label: Text('R\$')),
              ButtonSegment(value: 'percentage', label: Text('%')),
            ],
            selected: {_type},
            onSelectionChanged: (value) => setState(() => _type = value.first),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _value,
            autofocus: true,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(
              labelText: _type == 'percentage'
                  ? 'Percentual do desconto'
                  : 'Valor do desconto',
              suffixText: _type == 'percentage' ? '%' : null,
            ),
          ),
        ]),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('CANCELAR'),
          ),
          FilledButton(
            onPressed: () {
              final value = _value.text.trim().replaceAll(',', '.');
              if (value.isEmpty) return;
              Navigator.of(context).pop({'type': _type, 'value': value});
            },
            child: const Text('APLICAR'),
          ),
        ],
      );
}

class _TableMobileSummaryBar extends StatelessWidget {
  const _TableMobileSummaryBar({
    required this.total,
    required this.updating,
    required this.onTap,
  });

  final String? total;
  final bool updating;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => SafeArea(
        top: false,
        child: Material(
          color: Theme.of(context).colorScheme.primary,
          child: InkWell(
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
              child: Row(children: [
                const Icon(Icons.receipt_long_outlined, color: Colors.white),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'VER RESUMO',
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.w700),
                  ),
                ),
                if (updating)
                  const Text('Atualizando...',
                      style: TextStyle(
                          color: Colors.white, fontWeight: FontWeight.w700))
                else
                  Text(
                    total == null ? '...' : formatMoney(total!),
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.w800),
                  ),
                const SizedBox(width: 8),
                const Icon(Icons.chevron_right, color: Colors.white),
              ]),
            ),
          ),
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

  void _select(QuickSaleModifierGroup group, QuickSaleModifierOption option,
      bool value) {
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
      _modifierQuantities[option.id] =
          (_modifierQuantities[option.id] ?? 0) + 1;
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
    if (widget.product.unit.toLowerCase() == 'un' &&
        _itemQuantity != _itemQuantity.roundToDouble()) {
      setState(() =>
          _validation = 'Produtos por unidade exigem quantidade inteira.');
      return;
    }
    if (_quantity.text.split(RegExp(r'[,.]')).last.length > 3) {
      setState(() =>
          _validation = 'A quantidade aceita no máximo três casas decimais.');
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
                            leading:
                                const Icon(Icons.table_restaurant_outlined),
                            title: Text(table.name),
                            subtitle:
                                Text('Saldo: ${formatMoney(table.balance)}'),
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

class _TableItemTransferPicker extends StatefulWidget {
  const _TableItemTransferPicker({required this.items});

  final List<TableOrderItem> items;

  @override
  State<_TableItemTransferPicker> createState() =>
      _TableItemTransferPickerState();
}

class _TableItemTransferPickerState extends State<_TableItemTransferPicker> {
  final Set<int> _selectedIds = {};

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Transferir itens'),
        content: SizedBox(
          width: 420,
          child: widget.items.isEmpty
              ? const Text('Não há itens confirmados para transferir.')
              : ListView(
                  shrinkWrap: true,
                  children: widget.items
                      .map((item) => CheckboxListTile(
                            value: _selectedIds.contains(item.id),
                            onChanged: (selected) => setState(() {
                              if (selected == true) {
                                _selectedIds.add(item.id);
                              } else {
                                _selectedIds.remove(item.id);
                              }
                            }),
                            title:
                                Text('${item.quantity}x ${item.productName}'),
                            subtitle: Text(
                                formatMoney(item.lineTotal ?? item.unitPrice)),
                          ))
                      .toList(growable: false),
                ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('CANCELAR'),
          ),
          FilledButton(
            onPressed: _selectedIds.isEmpty
                ? null
                : () => Navigator.of(context).pop(widget.items
                    .where((item) => _selectedIds.contains(item.id))
                    .toList(growable: false)),
            child: const Text('SELECIONAR'),
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
    final active =
        await widget.controller.activateQuickSaleCustomer(customer.id);
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

Future<String?> _requiredReasonDialog(
    BuildContext context, String title) async {
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
