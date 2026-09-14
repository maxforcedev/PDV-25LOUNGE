import 'dart:async';

import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../core/transient_feedback.dart';
import '../scanner/product_barcode_scanner_page.dart';
import '../sales/quick_sale_page.dart';
import '../sales/sale_models.dart';
import '../sales/shared_customer_dialog.dart';
import '../sales/shared_pos_widgets.dart';
import 'attendance_models.dart';
import 'attendance_presentation.dart';
import 'shared_tables_grid.dart';
import 'table_summary_widgets.dart';

double _tableCartNumber(Object? value) =>
    double.tryParse('$value'.replaceAll(',', '.')) ?? 0;

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
  final prefix = quantity == 1 ? '' : '${formatAttendanceQuantity(quantity)}x ';
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
            ? 'Só temos ${formatAttendanceQuantity(available)} disponíveis deste produto.'
            : 'Você tentou adicionar ${formatAttendanceQuantity(requested)}, mas há somente ${formatAttendanceQuantity(available)} disponíveis.';
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

  Map<int, double> get _draftProductQuantities =>
      _cart.fold(<int, double>{}, (quantities, item) {
        quantities[item.product.id] = (quantities[item.product.id] ?? 0) +
            _tableCartNumber(item.quantity);
        return quantities;
      });

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
        total: () => formatAttendanceMoney(
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

  Future<void> _transferItems({Set<int> initiallySelected = const {}}) async {
    if (_actionInProgress) return;
    final eligible = _attendance.orders
        .expand((order) => order.items)
        .where((item) => item.status == 'confirmed')
        .toList(growable: false);
    final items = await Navigator.of(context).push<List<TableOrderItem>>(
      MaterialPageRoute(
        builder: (_) => _TableItemTransferPage(
          items: eligible,
          initiallySelected: initiallySelected,
        ),
      ),
    );
    if (items == null || items.isEmpty || !mounted) return;
    final tables = await widget.controller.attendanceTables();
    if (!mounted || tables == null) return;
    final target = await Navigator.of(context).push<AttendanceTable>(
      MaterialPageRoute(
        builder: (_) => _TableTransferDestinationPage(
          sourceTableId: _attendance.tableId,
          tables: tables
              .where((table) =>
                  table.id == _attendance.tableId ||
                  (table.isOpen &&
                      !table.legacyOccupied &&
                      table.attendance != null &&
                      table.attendance!.id != _attendance.id))
              .toList(growable: false),
        ),
      ),
    );
    if (target?.attendance == null || !mounted) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text('Transferir para ${target!.name}?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final item in items)
              Text(
                  '${formatAttendanceQuantity(item.quantity)}x ${item.productName}'),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('CANCELAR')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('TRANSFERIR')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
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
    if (moved != null) {
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Itens transferidos para ${target.name}.')),
        );
      }
    }
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

  Future<void> _selectTableCustomer() async {
    final customer = await showDialog<QuickSaleCustomer>(
      context: context,
      builder: (_) => SharedCustomerPickerDialog(
        controller: widget.controller,
        canCreate: _can('customers.add'),
        canReactivate: _can('customers.change'),
      ),
    );
    if (customer != null && mounted) await _setCustomer(customer.id);
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

  Future<void> _showConfirmedItemActions(
      TableOrderItem item, TableOrder order) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (_) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          ListTile(
            leading: const Icon(Icons.receipt_long_outlined),
            title: const Text('Ver detalhes'),
            onTap: () => Navigator.of(context).pop('details'),
          ),
          if (item.status == 'confirmed' && _can('tables.transfer_items'))
            ListTile(
              leading: Icon(Icons.drive_file_move_outline),
              title: Text('Transferir item'),
              onTap: () => Navigator.of(context).pop('transfer'),
            ),
          if (item.status == 'confirmed' && _can('tables.cancel_items'))
            ListTile(
              leading: Icon(Icons.cancel_outlined, color: Color(0xffea4d4d)),
              title: Text('Cancelar item',
                  style: TextStyle(color: Color(0xffea4d4d))),
              onTap: () => Navigator.of(context).pop('cancel'),
            ),
        ]),
      ),
    );
    if (!mounted) return;
    switch (action) {
      case 'details':
        await showDialog<void>(
          context: context,
          builder: (_) => AlertDialog(
            title: Text(item.productName),
            content: Text([
              'Quantidade: ${formatAttendanceQuantity(item.quantity)}',
              'Pedido: #${order.id}',
              if (order.createdAt != null)
                'Pedido criado em: ${_tableHistoryTime(order.createdAt)}',
              if (order.createdByName.isNotEmpty)
                'Operador: ${order.createdByName}',
              if (item.confirmedAt != null)
                'Confirmado em: ${_tableHistoryTime(item.confirmedAt)}',
              'Status: ${localizedAttendanceStatus(item.status)}',
              if (localizedPrintStatus(item.printStatus) != null)
                'Impressão: ${localizedPrintStatus(item.printStatus)}',
              ...item.modifierSnapshot.map((modifier) =>
                  '+ ${modifier['name'] ?? modifier['option_name'] ?? 'Modificador'}'),
              if (item.notes.isNotEmpty) 'Obs: ${item.notes}',
              if (item.cancellationReason.isNotEmpty)
                'Cancelado: ${item.cancellationReason}',
            ].join('\n')),
            actions: [
              TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('FECHAR')),
            ],
          ),
        );
        break;
      case 'transfer':
        await _transferItems(initiallySelected: {item.id});
        break;
      case 'cancel':
        await _cancelItem(item);
        break;
    }
  }

  Future<void> _showDraftItemActions(int index) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (_) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          ListTile(
              leading: const Icon(Icons.edit_outlined),
              title: const Text('Editar item'),
              onTap: () => Navigator.of(context).pop('edit')),
          ListTile(
            leading: Icon(Icons.delete_outline, color: Color(0xffea4d4d)),
            title: Text('Remover item',
                style: TextStyle(color: Color(0xffea4d4d))),
            onTap: () => Navigator.of(context).pop('remove'),
          ),
        ]),
      ),
    );
    if (action == 'edit') await _edit(index);
    if (action == 'remove') await _remove(index);
  }

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
            PopupMenuButton<String>(
              enabled: !_loading && !_actionInProgress,
              onSelected: (action) {
                switch (action) {
                  case 'customer':
                    unawaited(_selectTableCustomer());
                    break;
                  case 'remove_customer':
                    unawaited(_setCustomer(null));
                    break;
                  case 'conference':
                    unawaited(_showConference());
                    break;
                  case 'bill':
                    unawaited(_toggleBill());
                    break;
                  case 'transfer':
                    unawaited(_transferItems());
                    break;
                  case 'separate':
                    unawaited(_separateFromGroup());
                    break;
                }
              },
              itemBuilder: (_) => [
                if (_can('tables.set_customer'))
                  PopupMenuItem(
                    value: 'customer',
                    child: Text(_attendance.customerId == null
                        ? 'Adicionar cliente'
                        : 'Alterar cliente'),
                  ),
                if (_attendance.customerId != null &&
                    _can('tables.set_customer'))
                  const PopupMenuItem(
                      value: 'remove_customer', child: Text('Remover cliente')),
                const PopupMenuItem(
                    value: 'conference', child: Text('Visualizar conferência')),
                if (_attendance.status == 'open' && _can('tables.close'))
                  PopupMenuItem(
                    value: 'bill',
                    child: Text(_attendance.billRequested
                        ? 'Cancelar solicitação de conta'
                        : 'Solicitar conta'),
                  ),
                if (_attendance.status == 'open' &&
                    _can('tables.transfer_items') &&
                    _attendance.orders
                        .expand((order) => order.items)
                        .any((item) => item.status == 'confirmed'))
                  const PopupMenuItem(
                      value: 'transfer', child: Text('Transferir itens')),
                if (_attendance.status == 'open' &&
                    _group != null &&
                    _can('tables.merge'))
                  const PopupMenuItem(
                      value: 'separate', child: Text('Separar mesa do grupo')),
              ],
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
                    selectedQuantities: _draftProductQuantities,
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
                                  onSave: _save,
                                  preview: _preview,
                                  previewLoading: _previewLoading,
                                  onConfirmedItemActions:
                                      _showConfirmedItemActions,
                                  onDraftItemActions: _showDraftItemActions,
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
            onSave: _save,
            preview: _preview,
            previewLoading: _previewLoading,
            onConfirmedItemActions: _showConfirmedItemActions,
            onDraftItemActions: _showDraftItemActions,
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
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => _TableConferencePage(attendance: _attendance),
    ));
  }
}

class _TableConferencePage extends StatelessWidget {
  const _TableConferencePage({required this.attendance});

  final TableAttendance attendance;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Conferência'),
          actions: [
            IconButton(
              tooltip: 'Imprimir',
              icon: const Icon(Icons.print_outlined),
              onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                    content: Text('Impressão estará disponível em breve.')),
              ),
            ),
          ],
        ),
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Card(
              color: const Color(0xfffff9dc),
              margin: const EdgeInsets.all(16),
              child: ListView(
                padding: const EdgeInsets.all(24),
                children: [
                  const Text('CONFERÊNCIA SEM VALOR FISCAL',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 12),
                  Text(attendance.tableName,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.titleLarge),
                  if (attendance.openedAt != null)
                    Text(_tableHistoryTime(attendance.openedAt),
                        textAlign: TextAlign.center),
                  if (attendance.responsibleName.isNotEmpty)
                    Text('Atendente: ${attendance.responsibleName}',
                        textAlign: TextAlign.center),
                  const Divider(height: 32),
                  for (final order in attendance.orders)
                    for (final item in order.items)
                      if (item.status == 'confirmed')
                        Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: Column(children: [
                            Row(children: [
                              Expanded(
                                  child: Text(
                                      '${formatAttendanceQuantity(item.quantity)}x ${item.productName}')),
                              Text(formatAttendanceMoney(
                                  item.lineTotal ?? item.unitPrice)),
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
                  const Divider(height: 32),
                  TableSummaryWidgets(attendance.summary),
                  if (attendance.customerName.isNotEmpty)
                    Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text('Cliente: ${attendance.customerName}')),
                ],
              ),
            ),
          ),
        ),
      );
}

class _TableOrderSummaryPanel extends StatelessWidget {
  const _TableOrderSummaryPanel(
      {required this.cart,
      required this.attendance,
      required this.saving,
      required this.onSave,
      required this.preview,
      required this.previewLoading,
      required this.onConfirmedItemActions,
      required this.onDraftItemActions});
  final List<QuickSaleCartItem> cart;
  final TableAttendance attendance;
  final bool saving;
  final Future<void> Function() onSave;
  final Map<String, dynamic>? preview;
  final bool previewLoading;
  final Future<void> Function(TableOrderItem, TableOrder)
      onConfirmedItemActions;
  final Future<void> Function(int) onDraftItemActions;

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.white,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text('RESUMO DA MESA',
                style: Theme.of(context)
                    .textTheme
                    .titleMedium
                    ?.copyWith(fontWeight: FontWeight.w800)),
            if (attendance.customerName.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text('Cliente: ${attendance.customerName}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: Color(0xff64748b), fontSize: 12)),
              ),
            const SizedBox(height: 8),
            Expanded(
                child: cart.isEmpty && attendance.orders.isEmpty
                    ? const Center(
                        child: Text('Adicione produtos para iniciar o pedido.'))
                    : ListView(children: [
                        for (final order in attendance.orders)
                          for (final item in order.items)
                            _ConfirmedOrderItemRow(
                              item: item,
                              onTap: () => unawaited(
                                  onConfirmedItemActions(item, order)),
                            ),
                        if (cart.isNotEmpty) ...[
                          const Padding(
                            padding: EdgeInsets.only(top: 12, bottom: 4),
                            child: Text('NOVOS ITENS',
                                style: TextStyle(fontWeight: FontWeight.w800)),
                          ),
                          for (var draftIndex = 0;
                              draftIndex < cart.length;
                              draftIndex++)
                            SharedCartItemTile(
                              name: cart[draftIndex].product.name,
                              quantity: formatAttendanceQuantity(
                                  cart[draftIndex].quantity),
                              amount: normalizedAttendanceMoney(
                                  _tableLineTotal(cart[draftIndex])),
                              details: [
                                for (final modifier
                                    in cart[draftIndex].modifiers)
                                  _tableModifierText(
                                      cart[draftIndex].product, modifier),
                                if (cart[draftIndex].notes.isNotEmpty)
                                  'Obs: ${cart[draftIndex].notes}',
                              ].join('\n'),
                              onTap: saving
                                  ? null
                                  : () =>
                                      unawaited(onDraftItemActions(draftIndex)),
                              onLongPress: saving
                                  ? null
                                  : () =>
                                      unawaited(onDraftItemActions(draftIndex)),
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
                'Total projetado: ${formatAttendanceMoney(preview!['total'])}',
                textAlign: TextAlign.end,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
            const SizedBox(height: 4),
            if (attendance.billRequested)
              const Padding(
                padding: EdgeInsets.only(bottom: 8),
                child: Text('CONTA SOLICITADA',
                    style: TextStyle(
                        color: Color(0xffffa21d),
                        fontSize: 12,
                        fontWeight: FontWeight.w800)),
              ),
            SharedTotalsPanel(lines: [
              SharedTotalsLine(
                  label: 'Subtotal',
                  value: '${attendance.summary['subtotal'] ?? '0.00'}',
                  formattedValue:
                      formatAttendanceMoney(attendance.summary['subtotal'])),
              if (_tableCartNumber(
                      attendance.summary['promotion_discount_total']) >
                  0)
                SharedTotalsLine(
                    label: 'Promoções',
                    value:
                        '${attendance.summary['promotion_discount_total'] ?? '0.00'}',
                    formattedValue: formatAttendanceMoney(
                        attendance.summary['promotion_discount_total']),
                    negative: true),
              if (_tableCartNumber(attendance.summary['item_discount_total']) >
                  0)
                SharedTotalsLine(
                    label: 'Descontos por item',
                    value:
                        '${attendance.summary['item_discount_total'] ?? '0.00'}',
                    formattedValue: formatAttendanceMoney(
                        attendance.summary['item_discount_total']),
                    negative: true),
              if (_tableCartNumber(
                      attendance.summary['checkout_discount_total']) >
                  0)
                SharedTotalsLine(
                    label: 'Desconto da mesa',
                    value:
                        '${attendance.summary['checkout_discount_total'] ?? '0.00'}',
                    formattedValue: formatAttendanceMoney(
                        attendance.summary['checkout_discount_total']),
                    negative: true),
              SharedTotalsLine(
                  label: 'Taxa de serviço',
                  value: '${attendance.summary['service_fee_total'] ?? '0.00'}',
                  formattedValue: formatAttendanceMoney(
                      attendance.summary['service_fee_total'])),
              SharedTotalsLine(
                  label: 'Total oficial',
                  value: '${attendance.summary['total_due'] ?? '0.00'}',
                  formattedValue:
                      formatAttendanceMoney(attendance.summary['total_due']),
                  strong: true),
            ]),
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

class _ConfirmedOrderItemRow extends StatelessWidget {
  const _ConfirmedOrderItemRow({required this.item, this.onTap});

  final TableOrderItem item;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final cancelled = item.status == 'cancelled' || item.status == 'canceled';
    final printStatus = localizedPrintStatus(item.printStatus);
    return Material(
      color: cancelled ? const Color(0x1aea4d4d) : Colors.transparent,
      child: InkWell(
        onTap: onTap,
        onLongPress: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 9),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Expanded(
                child: Text(
                    '${formatAttendanceQuantity(item.quantity)}x ${item.productName}',
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              ),
              const SizedBox(width: 8),
              Text(formatAttendanceMoney(item.lineTotal ?? item.unitPrice),
                  style: const TextStyle(
                      color: Color(0xff3454d1), fontWeight: FontWeight.w800)),
            ]),
            if (cancelled)
              const Padding(
                padding: EdgeInsets.only(top: 3),
                child: Text('CANCELADO',
                    style: TextStyle(
                        color: Color(0xffb42318),
                        fontSize: 11,
                        fontWeight: FontWeight.w800)),
              )
            else if (printStatus != null)
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Text(
                    item.printStatus == 'printed'
                        ? '✓ $printStatus'
                        : printStatus,
                    style: TextStyle(
                        color: item.printStatus == 'printed'
                            ? const Color(0xff17c666)
                            : const Color(0xff64748b),
                        fontSize: 11,
                        fontWeight: FontWeight.w700)),
              ),
          ]),
        ),
      ),
    );
  }
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
                    total == null ? '...' : formatAttendanceMoney(total!),
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
    _quantity = TextEditingController(
        text: formatAttendanceQuantity(widget.initial.quantity));
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
      _quantity.text = formatAttendanceQuantity(quantity);
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
          ? 'Selecione mais ${formatAttendanceQuantity(required - total)} unidade(s) em ${group.name}.'
          : 'Remova ${formatAttendanceQuantity(total - required)} unidade(s) em ${group.name}.';
    }
    final minimum = _tableCartNumber(group.minTotalQuantity);
    if (minimum > 0 && total < minimum) {
      return 'Selecione mais ${formatAttendanceQuantity(minimum - total)} unidade(s) em ${group.name}.';
    }
    final maximum = group.maxTotalQuantity == null
        ? null
        : _tableCartNumber(group.maxTotalQuantity);
    if (maximum != null && total > maximum) {
      return 'Remova ${formatAttendanceQuantity(total - maximum)} unidade(s) em ${group.name}.';
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
      quantity: formatAttendanceQuantity(_itemQuantity),
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
                                  '+ ${formatAttendanceMoney(option.additionalPrice)}'),
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
                                  '+ ${formatAttendanceMoney(option.additionalPrice)}'),
                            ),
                    ),
                    if (group.allowOptionQuantity &&
                        _modifierQuantities.containsKey(option.id)) ...[
                      IconButton(
                        onPressed: () => _decrease(option),
                        icon: const Icon(Icons.remove),
                        tooltip: 'Diminuir ${option.name}',
                      ),
                      Text(formatAttendanceQuantity(
                          _modifierQuantities[option.id])),
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

class _TableTransferDestinationPage extends StatelessWidget {
  const _TableTransferDestinationPage({
    required this.sourceTableId,
    required this.tables,
  });

  final int sourceTableId;
  final List<AttendanceTable> tables;

  @override
  Widget build(BuildContext context) {
    final destinations = tables.where((table) =>
        table.id != sourceTableId &&
        table.isOpen &&
        !table.legacyOccupied &&
        table.attendance != null);
    return Scaffold(
      appBar: AppBar(title: const Text('Destino dos itens')),
      body: Column(children: [
        if (destinations.isEmpty)
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 16, 16, 0),
            child: Text('Não há outra mesa aberta disponível.'),
          ),
        Expanded(
          child: SharedTablesGrid(
            tables: tables,
            isDisabled: (table) =>
                table.id == sourceTableId ||
                !table.isOpen ||
                table.legacyOccupied ||
                table.attendance == null,
            statusLabel: (table) =>
                table.id == sourceTableId ? 'MESA ATUAL' : null,
            onTap: (table) => Navigator.of(context).pop(table),
          ),
        ),
      ]),
    );
  }
}

class _TableItemTransferPage extends StatefulWidget {
  const _TableItemTransferPage({
    required this.items,
    required this.initiallySelected,
  });

  final List<TableOrderItem> items;
  final Set<int> initiallySelected;

  @override
  State<_TableItemTransferPage> createState() => _TableItemTransferPageState();
}

class _TableItemTransferPageState extends State<_TableItemTransferPage> {
  final Set<int> _selected = {};

  @override
  void initState() {
    super.initState();
    for (final item in widget.items) {
      if (widget.initiallySelected.contains(item.id)) _selected.add(item.id);
    }
  }

  void _toggle(TableOrderItem item, bool selected) => setState(() {
        selected ? _selected.add(item.id) : _selected.remove(item.id);
      });

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('TRANSFERIR ITENS')),
        body: widget.items.isEmpty
            ? const Center(
                child: Text('Não há itens confirmados para transferir.'))
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Wrap(spacing: 8, children: [
                    TextButton(
                      onPressed: () => setState(() => _selected
                          .addAll(widget.items.map((item) => item.id))),
                      child: const Text('SELECIONAR TODOS'),
                    ),
                    TextButton(
                      onPressed: () => setState(_selected.clear),
                      child: const Text('DESMARCAR TODOS'),
                    ),
                  ]),
                  const SizedBox(height: 8),
                  for (final item in widget.items)
                    CheckboxListTile(
                      value: _selected.contains(item.id),
                      onChanged: (selected) => _toggle(item, selected == true),
                      controlAffinity: ListTileControlAffinity.leading,
                      title: Text(item.productName),
                      subtitle: Text(
                        'Disponível: ${formatAttendanceQuantity(item.quantity)}'
                        '${_selected.contains(item.id) ? ' · Transferir: ${formatAttendanceQuantity(item.quantity)}' : ''}',
                      ),
                    ),
                ],
              ),
        bottomNavigationBar: SafeArea(
          minimum: const EdgeInsets.all(16),
          child: FilledButton(
            onPressed: _selected.isEmpty
                ? null
                : () => Navigator.of(context).pop(widget.items
                    .where((item) => _selected.contains(item.id))
                    .toList(growable: false)),
            child: const Text('CONTINUAR'),
          ),
        ),
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
