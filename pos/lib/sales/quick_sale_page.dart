import 'dart:async';

import 'package:flutter/material.dart';

import '../cash/cash_page.dart';
import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../network/pos_api_error.dart';
import '../sync/sync_center_page.dart';
import '../sync/sync_status_button.dart';
import 'sale_models.dart';

class _PreviewIntent {
  const _PreviewIntent({
    required this.generation,
    required this.availabilityGeneration,
    required this.items,
    required this.discount,
    required this.serviceFeeWaived,
    this.rollbackCart,
    this.stockMutation,
  });

  final int generation;
  final int availabilityGeneration;
  final List<Map<String, dynamic>> items;
  final QuickSaleDiscountIntent discount;
  final bool serviceFeeWaived;
  final List<QuickSaleCartItem>? rollbackCart;
  final _CartMutation? stockMutation;
}

class _CartMutation {
  const _CartMutation._(this.clientItemId, this.item, this.removeItem);

  factory _CartMutation.add(QuickSaleCartItem item) =>
      _CartMutation._(item.clientItemId, item, false);
  factory _CartMutation.replace(String clientItemId, QuickSaleCartItem item) =>
      _CartMutation._(clientItemId, item, false);
  factory _CartMutation.remove(String clientItemId) =>
      _CartMutation._(clientItemId, null, true);

  final String clientItemId;
  final QuickSaleCartItem? item;
  final bool removeItem;

  List<QuickSaleCartItem> apply(List<QuickSaleCartItem> cart) {
    final result = List<QuickSaleCartItem>.of(cart);
    final index =
        result.indexWhere((entry) => entry.clientItemId == clientItemId);
    if (removeItem) {
      if (index >= 0) result.removeAt(index);
    } else if (index >= 0) {
      result[index] = item!;
    } else {
      result.add(item!);
    }
    return result;
  }
}

class QuickSalePage extends StatefulWidget {
  const QuickSalePage({required this.controller, super.key});

  final AppController controller;

  @override
  State<QuickSalePage> createState() => _QuickSalePageState();
}

class _QuickSalePageState extends State<QuickSalePage> {
  final _search = TextEditingController();
  final _draft = QuickSaleDraft();
  List<QuickSaleProduct> _allCatalog = const [];
  List<QuickSaleProduct> _catalog = const [];
  List<QuickSaleCategory> _categories = const [];
  QuickSaleCheckoutOptions? _checkoutOptions;
  bool _loading = true;
  bool _favoritesOnly = false;
  int? _categoryId;
  int _previewGeneration = 0;
  Timer? _previewDebounce;
  Timer? _searchDebounce;
  Timer? _availabilityDebounce;
  bool _previewInFlight = false;
  bool _availabilityInFlight = false;
  _PreviewIntent? _pendingPreview;
  int _availabilityGeneration = 0;
  int? _pendingAvailabilityGeneration;
  List<QuickSaleCartItem> _lastValidatedCart = const [];
  final List<_CartMutation> _pendingCartMutations = [];

  List<QuickSaleCartItem> get _cart => _draft.cart;
  QuickSalePreview? get _preview => _draft.preview;
  set _preview(QuickSalePreview? value) {
    _draft.preview = value;
    _draft.changed();
  }

  bool get _loadingPreview => _draft.loadingPreview;
  set _loadingPreview(bool value) {
    _draft.loadingPreview = value;
    _draft.changed();
  }

  bool get _serviceFeeWaived => _draft.serviceFeeWaived;
  set _serviceFeeWaived(bool value) {
    _draft.serviceFeeWaived = value;
    _draft.changed();
  }

  QuickSaleDiscountIntent get _discount => _draft.discount;
  set _discount(QuickSaleDiscountIntent value) {
    _draft.discount = value;
    _draft.changed();
  }

  bool get _canDiscount =>
      widget.controller.bootstrapSnapshot?.permissions
          .contains('sales.apply_discount') ??
      false;
  bool get _canItemDiscount =>
      widget.controller.bootstrapSnapshot?.permissions
          .contains('sales.apply_item_discount') ??
      false;
  bool get _canWaiveFee =>
      widget.controller.bootstrapSnapshot?.permissions
          .contains('sales.waive_service_fee') ??
      false;
  bool get _canViewCustomers =>
      widget.controller.bootstrapSnapshot?.permissions
          .contains('customers.view') ??
      false;
  bool get _canAddCustomers =>
      widget.controller.bootstrapSnapshot?.permissions
          .contains('customers.add') ??
      false;
  bool get _cashReady =>
      _checkoutOptions != null && _checkoutOptions!.cashSessions.isNotEmpty;
  bool get _checkoutReady =>
      _cashReady && _checkoutOptions!.paymentMethods.isNotEmpty;
  bool get _canOpenCash =>
      widget.controller.bootstrapSnapshot?.permissions
          .contains('cash_registers.open') ??
      false;

  @override
  void initState() {
    super.initState();
    _search.addListener(_onSearchChanged);
    unawaited(_loadInitial());
  }

  @override
  void dispose() {
    _previewGeneration++;
    _availabilityGeneration++;
    _previewDebounce?.cancel();
    _searchDebounce?.cancel();
    _availabilityDebounce?.cancel();
    _search.dispose();
    _draft.dispose();
    super.dispose();
  }

  Future<void> _loadInitial() async {
    await Future.wait([_loadCatalog(), _loadCheckoutOptions()]);
  }

  Future<void> _loadCatalog() async {
    if (mounted) setState(() => _loading = true);
    final products = await widget.controller.quickSaleCatalog();
    if (!mounted) return;
    setState(() {
      _allCatalog = products ?? const [];
      _categories = _categoriesFromCatalog(_allCatalog);
      _loading = false;
      _applyCatalogFilter();
    });
  }

  List<QuickSaleCategory> _categoriesFromCatalog(
      List<QuickSaleProduct> products) {
    final categories = <int, QuickSaleCategory>{};
    for (final product in products) {
      final id = product.categoryId;
      final name = product.categoryName;
      if (id != null && name != null && name.isNotEmpty) {
        categories[id] = QuickSaleCategory(id: id, name: name);
      }
    }
    final result = categories.values.toList()
      ..sort((left, right) => left.name.compareTo(right.name));
    return result;
  }

  void _onSearchChanged() {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 300), () {
      if (!mounted) return;
      widget.controller.logPosAction('catalog_search');
      setState(_applyCatalogFilter);
    });
  }

  void _applyCatalogFilter() {
    final search = _search.text.trim().toLowerCase();
    _catalog = _allCatalog.where((product) {
      final matchesCategory =
          _categoryId == null || product.categoryId == _categoryId;
      final matchesFavorite = !_favoritesOnly || product.favorite;
      final matchesSearch = search.isEmpty ||
          product.name.toLowerCase().contains(search) ||
          product.internalCode.toLowerCase().contains(search) ||
          (product.barcode?.toLowerCase().contains(search) ?? false);
      return matchesCategory && matchesFavorite && matchesSearch;
    }).toList(growable: false);
  }

  Future<void> _loadCheckoutOptions() async {
    final options = await widget.controller.quickSaleCheckoutOptions();
    if (mounted && options != null) setState(() => _checkoutOptions = options);
  }

  Future<void> _openCash() async {
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => CashPage(controller: widget.controller),
    ));
    if (mounted) await _loadCheckoutOptions();
  }

  Future<void> _barcode() async {
    final barcode = _search.text.trim();
    if (barcode.isEmpty) return;
    final product = await widget.controller.quickSaleBarcode(barcode);
    if (product != null && mounted) await _addProduct(product);
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

  double? _stockNumber(Object? value) =>
      double.tryParse('$value'.replaceAll(',', '.'));

  String _formatStockNumber(Object? value) {
    final number = _stockNumber(value);
    if (number == null) return '$value';
    var formatted = number.toStringAsFixed(3).replaceFirst(RegExp(r'0+$'), '');
    if (formatted.endsWith('.')) {
      formatted = formatted.substring(0, formatted.length - 1);
    }
    return formatted.replaceAll('.', ',');
  }

  String _formatStockQuantity(Object? quantity, String unit) {
    final number = _stockNumber(quantity) ?? 0;
    final value = _formatStockNumber(quantity);
    return switch (unit.toLowerCase()) {
      'un' => '$value ${number == 1 ? 'unidade' : 'unidades'}',
      'kg' => '$value kilos',
      'g' => '$value gramas',
      'l' => '$value Litros',
      'ml' => '$value mls',
      _ => value,
    };
  }

  void _showStockUnavailable(
      [QuickSaleStockAvailability? availability, _CartMutation? mutation]) {
    final item = mutation?.item;
    final Map<String, dynamic>? shortage = item == null
        ? null
        : availability?.shortages.cast<Map<String, dynamic>>().firstWhere(
              (row) =>
                  row['product'] == item.product.id &&
                  row['basis'] == 'quantity',
              orElse: () => const <String, dynamic>{},
            );
    final available =
        shortage == null ? null : _stockNumber(shortage['available_quantity']);
    final requested = item == null ? null : _stockNumber(item.quantity);
    final unit = item?.product.unit ?? 'un';
    final message = available == null
        ? 'Este produto não possui estoque suficiente para essa quantidade.'
        : available <= 0
            ? 'Este produto está sem estoque no momento.'
            : requested != null && requested > available
                ? 'Você tentou adicionar ${_formatStockQuantity(item!.quantity, unit)}, '
                    'mas há somente ${_formatStockQuantity(shortage!['available_quantity'], unit)} disponíveis.'
                : 'Só temos ${_formatStockQuantity(shortage!['available_quantity'], unit)} disponíveis deste produto.';
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(message),
    ));
  }

  void _showCatalogStockUnavailable() {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
      content: Text('Este produto está sem estoque no momento.'),
    ));
  }

  Future<void> _addProduct(QuickSaleProduct product,
      {String quantity = '1'}) async {
    widget.controller.logPosAction('cart_add');
    if (!product.canSell) {
      _showCatalogStockUnavailable();
      return;
    }
    final item = QuickSaleCartItem(
      clientItemId: createIdempotencyKey(),
      product: product,
      quantity: quantity,
    );
    if (_requiresConfiguration(product)) {
      await _editProduct(product, initial: item);
      return;
    }
    _applyCartMutation(_CartMutation.add(item));
  }

  Future<void> _addProductBatch(QuickSaleProduct product) async {
    if (!product.canSell) {
      _showCatalogStockUnavailable();
      return;
    }
    final quantity = await showDialog<String>(
      context: context,
      builder: (_) => _BatchQuantityDialog(productName: product.name),
    );
    if (quantity == null || !mounted) return;
    final item = QuickSaleCartItem(
      clientItemId: createIdempotencyKey(),
      product: product,
      quantity: quantity,
    );
    if (product.modifierGroups.isNotEmpty) {
      await _editProduct(product, initial: item, checkBatchAvailability: true);
      return;
    }
    widget.controller.logPosAction('cart_add_batch');
    _applyCartMutation(_CartMutation.add(item));
  }

  Future<void> _editProduct(
    QuickSaleProduct product, {
    int? index,
    QuickSaleCartItem? initial,
    bool checkBatchAvailability = false,
  }) async {
    widget.controller.logPosAction('cart_edit');
    final current = initial ?? (index == null ? null : _cart[index]);
    final item = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) => _ItemEditorDialog(
        product: product,
        initial: current,
      ),
    );
    if (!mounted || item == null) return;
    _applyCartMutation(index == null
        ? _CartMutation.add(item)
        : _CartMutation.replace(current!.clientItemId, item));
  }

  Future<void> _editCartItem(int index) async {
    final result = await showDialog<_CartItemEditResult>(
      context: context,
      builder: (_) => _EditCartItemDialog(
        item: _cart[index],
        requiresItemAuthorization: !_canItemDiscount,
        requestItemAuthorization: _requestItemDiscountAuthorization,
      ),
    );
    if (result == null || !mounted) return;
    if (result.delete) {
      _applyCartMutation(_CartMutation.remove(_cart[index].clientItemId));
    } else {
      _applyCartMutation(
          _CartMutation.replace(_cart[index].clientItemId, result.item!));
    }
    setState(() {
      if (result.itemDiscountAuthorization != null) {
        _draft.itemDiscountAuthorization = result.itemDiscountAuthorization;
      }
      if (_canItemDiscount) {
        _draft.itemDiscountAuthorization = null;
      }
      if (!_cart.any((item) => !item.discount.isZero)) {
        _draft.itemDiscountAuthorization = null;
      }
    });
  }

  void _applyCartMutation(_CartMutation mutation) {
    _pendingCartMutations.add(mutation);
    _scheduleCartAvailability();
  }

  List<QuickSaleCartItem> _replayCartMutations(
      List<QuickSaleCartItem> base, Iterable<_CartMutation> mutations) {
    var result = List<QuickSaleCartItem>.of(base);
    for (final mutation in mutations) {
      result = mutation.apply(result);
    }
    return result;
  }

  void _invalidateCartAvailability() {
    _availabilityGeneration++;
    _availabilityDebounce?.cancel();
    _pendingAvailabilityGeneration = null;
  }

  void _resetSaleDraftState() {
    _availabilityGeneration++;
    _previewGeneration++;
    _availabilityDebounce?.cancel();
    _previewDebounce?.cancel();
    _pendingAvailabilityGeneration = null;
    _pendingPreview = null;
    _lastValidatedCart = const [];
    _pendingCartMutations.clear();
    _draft.clearAfterSale();
  }

  void _scheduleCartAvailability() {
    _invalidateCartAvailability();
    if (_cart.isEmpty && _pendingCartMutations.isEmpty) return;
    final generation = _availabilityGeneration;
    _availabilityDebounce = Timer(
      const Duration(milliseconds: 100),
      () => _enqueueCartAvailability(generation),
    );
  }

  void _enqueueCartAvailability(int generation) {
    if (_availabilityInFlight) {
      _pendingAvailabilityGeneration = generation;
      return;
    }
    unawaited(_validateCartAvailability(generation));
  }

  Future<QuickSaleStockAvailability?> _availabilityFor(
          List<QuickSaleCartItem> items) =>
      widget.controller.quickSaleStockAvailability(
        items: items.map((item) => item.toJson()).toList(growable: false),
      );

  Future<List<_CartMutation>?> _acceptedCartMutations(
    List<QuickSaleCartItem> base,
    List<_CartMutation> mutations,
    int generation,
  ) async {
    final accepted = <_CartMutation>[];
    for (final mutation in mutations) {
      final result = await _availabilityFor(
        _replayCartMutations(base, [...accepted, mutation]),
      );
      if (!mounted || generation != _availabilityGeneration || result == null) {
        return null;
      }
      if (result.available || !result.enforced) accepted.add(mutation);
    }
    return accepted;
  }

  Future<void> _validateCartAvailability(int generation) async {
    _availabilityInFlight = true;
    var previewRequested = false;
    List<QuickSaleCartItem>? previewRollbackCart;
    _CartMutation? previewStockMutation;
    try {
      final mutations = List<_CartMutation>.of(_pendingCartMutations);
      if (mutations.isEmpty) return;
      final previousCart = List<QuickSaleCartItem>.of(_lastValidatedCart);
      final candidates = _replayCartMutations(previousCart, mutations);
      if (!mounted || generation != _availabilityGeneration) return;
      if (candidates.isEmpty) {
        setState(_resetSaleDraftState);
        return;
      }
      final availability = await _availabilityFor(candidates);
      if (!mounted ||
          generation != _availabilityGeneration ||
          availability == null) {
        return;
      }

      final acceptedMutations = (availability.available ||
              !availability.enforced)
          ? mutations
          : await _acceptedCartMutations(previousCart, mutations, generation);
      if (!mounted ||
          generation != _availabilityGeneration ||
          acceptedMutations == null) {
        return;
      }
      final committedCart =
          _replayCartMutations(previousCart, acceptedMutations);
      final rejected = acceptedMutations.length != mutations.length;
      _pendingCartMutations
        ..clear()
        ..addAll(acceptedMutations);
      if (acceptedMutations.isEmpty) {
        if (rejected) _showStockUnavailable(availability, mutations.last);
        return;
      }

      // The cart changes only after the complete candidate passes preflight.
      _previewGeneration++;
      _previewDebounce?.cancel();
      _pendingPreview = null;
      setState(() {
        _cart
          ..clear()
          ..addAll(committedCart);
        _preview = null;
        _loadingPreview = false;
      });
      _draft.changed();
      if (rejected) _showStockUnavailable(availability, mutations.last);
      _lastValidatedCart = List<QuickSaleCartItem>.of(committedCart);
      _pendingCartMutations.clear();
      previewRequested = true;
      previewRollbackCart = previousCart;
      previewStockMutation = acceptedMutations.last;
    } finally {
      _availabilityInFlight = false;
      if (previewRequested &&
          mounted &&
          generation == _availabilityGeneration &&
          _pendingCartMutations.isEmpty) {
        _schedulePreview(
          rollbackCart: previewRollbackCart,
          stockMutation: previewStockMutation,
        );
      }
      final pending = _pendingAvailabilityGeneration;
      _pendingAvailabilityGeneration = null;
      if (pending != null && mounted) _enqueueCartAvailability(pending);
    }
  }

  void _schedulePreview({
    List<QuickSaleCartItem>? rollbackCart,
    _CartMutation? stockMutation,
  }) {
    if (_pendingCartMutations.isNotEmpty || _availabilityInFlight) return;
    _draft.changed();
    final generation = ++_previewGeneration;
    _previewDebounce?.cancel();
    if (_cart.isEmpty) {
      _pendingPreview = null;
      setState(() {
        _preview = null;
        _loadingPreview = false;
      });
      return;
    }
    setState(() => _loadingPreview = true);
    final items = _cart.map((item) => item.toJson()).toList(growable: false);
    final discount = _discount;
    final serviceFeeWaived = _serviceFeeWaived;
    _previewDebounce = Timer(
      const Duration(milliseconds: 120),
      () => _enqueuePreview(_PreviewIntent(
        generation: generation,
        availabilityGeneration: _availabilityGeneration,
        items: items,
        discount: discount,
        serviceFeeWaived: serviceFeeWaived,
        rollbackCart: rollbackCart,
        stockMutation: stockMutation,
      )),
    );
  }

  void _enqueuePreview(_PreviewIntent intent) {
    if (_previewInFlight) {
      _pendingPreview = intent;
      return;
    }
    unawaited(_requestPreview(intent));
  }

  Future<void> _requestPreview(_PreviewIntent intent) async {
    _previewInFlight = true;
    widget.controller.logPosAction('preview_dispatch');
    try {
      final preview = await widget.controller.previewQuickSale(
        items: intent.items,
        discount: intent.discount.toJson(),
        serviceFeeWaived: intent.serviceFeeWaived,
      );
      if (!mounted) return;
      if (intent.generation == _previewGeneration) {
        setState(() {
          _preview = preview;
          _loadingPreview = false;
        });
      }
    } on PosApiException catch (error) {
      if (!mounted ||
          error.code != 'stock_unavailable' ||
          intent.rollbackCart == null ||
          intent.generation != _previewGeneration ||
          intent.availabilityGeneration != _availabilityGeneration) {
        return;
      }
      final availability = QuickSaleStockAvailability.fromJson(error.details);
      _lastValidatedCart = List<QuickSaleCartItem>.of(intent.rollbackCart!);
      setState(() {
        _cart
          ..clear()
          ..addAll(intent.rollbackCart!);
        _preview = null;
        _loadingPreview = false;
      });
      _draft.changed();
      _showStockUnavailable(availability, intent.stockMutation);
    } finally {
      _previewInFlight = false;
      if (mounted) {
        final pending = _pendingPreview;
        _pendingPreview = null;
        if (pending != null) _enqueuePreview(pending);
      }
    }
  }

  Future<void> _checkout() async {
    if (!_checkoutReady || _cart.isEmpty || _preview == null) return;
    widget.controller.logPosAction('checkout_open');
    final options = _checkoutOptions!;
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => _CheckoutPage(
          controller: widget.controller,
          draft: _draft,
          options: options,
          preview: _preview!,
          onSaleCompleted: () async {
            if (mounted) setState(_resetSaleDraftState);
            unawaited(_loadCheckoutOptions());
            unawaited(_loadCatalog());
          },
        ),
      ),
    );
  }

  Future<void> _selectCustomer() async {
    final customer = await showDialog<QuickSaleCustomer>(
      context: context,
      builder: (_) => _CustomerPickerDialog(
        controller: widget.controller,
        canCreate: _canAddCustomers,
      ),
    );
    if (customer == null || !mounted) return;
    setState(() => _draft.customer = customer);
    _draft.changed();
  }

  void _removeCustomer() {
    setState(() => _draft.customer = null);
    _draft.changed();
  }

  Future<void> _editSaleDiscount() async {
    final discount = await showDialog<QuickSaleDiscountIntent>(
      context: context,
      builder: (_) => _DiscountDialog(initial: _discount),
    );
    if (discount == null || !mounted) return;
    QuickSaleAuthorization? authorization;
    if (!_canDiscount) {
      authorization = await _requestDiscountAuthorization();
      if (authorization == null || !mounted) return;
    }
    setState(() {
      _discount = discount;
      _draft.discountAuthorization = authorization;
    });
    _schedulePreview();
  }

  void _removeSaleDiscount() {
    setState(() {
      _discount = const QuickSaleDiscountIntent();
      _draft.discountAuthorization = null;
    });
    _schedulePreview();
  }

  Future<QuickSaleAuthorization?> _requestDiscountAuthorization() =>
      _requestDiscountAuthorizationFor(type: 'sale');

  Future<QuickSaleAuthorization?> _requestItemDiscountAuthorization() =>
      _requestDiscountAuthorizationFor(type: 'item');

  Future<QuickSaleAuthorization?> _requestDiscountAuthorizationFor(
      {required String type}) async {
    // A new approval attempt must not retain a prior approver PIN.
    if (type == 'item') {
      _draft.itemDiscountAuthorization = null;
    } else if (type == 'service_fee') {
      _draft.serviceFeeAuthorization = null;
    } else {
      _draft.discountAuthorization = null;
    }
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
      builder: (_) => _DiscountAuthorizationDialog(
        authorizers: authorizers,
        onAuthorize: (authorization) =>
            widget.controller.validateQuickSaleDiscountAuthorization(
          type: type,
          authorization: authorization,
        ),
      ),
    );
  }

  Future<void> _toggleServiceFee() async {
    if (!_serviceFeeWaived && !_canWaiveFee) {
      final authorization =
          await _requestDiscountAuthorizationFor(type: 'service_fee');
      if (authorization == null || !mounted) return;
      _draft.serviceFeeAuthorization = authorization;
    } else if (_serviceFeeWaived) {
      _draft.serviceFeeAuthorization = null;
    }
    setState(() => _serviceFeeWaived = !_serviceFeeWaived);
    _schedulePreview();
  }

  Future<void> _clearCart() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Apagar carrinho?'),
        content: const Text(
            'Todos os produtos e alterações desta venda serão removidos.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('CANCELAR')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('APAGAR'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(_resetSaleDraftState);
  }

  Future<void> _showMobileCart() async {
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => _CartPage(
        draft: _draft,
        allowDiscount: true,
        allowCustomer: _canViewCustomers,
        allowWaiveFee: _serviceFeeWaived ||
            (_preview != null && _preview!.serviceFeeRate != '0.00'),
        onCustomer: _selectCustomer,
        onRemoveCustomer: _removeCustomer,
        onDiscount: _editSaleDiscount,
        onRemoveDiscount: _removeSaleDiscount,
        onServiceFee: _toggleServiceFee,
        onClear: _clearCart,
        panel: () => _CartPanel(
          cart: _cart,
          preview: _preview,
          loadingPreview: _loadingPreview,
          discount: _discount,
          cashReady: _checkoutReady,
          customer: _draft.customer,
          allowCustomer: _canViewCustomers,
          onCustomer: _selectCustomer,
          onRemoveCustomer: _removeCustomer,
          allowWaiveFee: _serviceFeeWaived ||
              (_preview != null && _preview!.serviceFeeRate != '0.00'),
          serviceFeeWaived: _serviceFeeWaived,
          onServiceFee: _toggleServiceFee,
          showServiceFeeMenu: false,
          onEdit: _editCartItem,
          onCheckout: _checkout,
        ),
      ),
    ));
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Venda Rápida'),
          actions: [
            SyncStatusButton(
              status: widget.controller.syncStatus,
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => SyncCenterPage(controller: widget.controller),
              )),
            ),
          ],
        ),
        bottomNavigationBar:
            MediaQuery.sizeOf(context).width < 900 && _cashReady
                ? _MobileCartBar(
                    itemCount: _cart.length,
                    preview: _preview,
                    updating: _loadingPreview,
                    onTap: _showMobileCart,
                  )
                : null,
        body: SafeArea(
          child: _checkoutOptions != null && !_checkoutReady
              ? _CashRequiredPanel(
                  options: _checkoutOptions!,
                  canOpenCash: _canOpenCash,
                  onOpenCash: _openCash,
                )
              : LayoutBuilder(builder: (context, constraints) {
                  final catalog = _CatalogPanel(
                    search: _search,
                    loading: _loading,
                    products: _catalog,
                    categories: _categories,
                    categoryId: _categoryId,
                    favoritesOnly: _favoritesOnly,
                    onCategory: (value) {
                      widget.controller.logPosAction('catalog_category');
                      setState(() {
                        _categoryId = value;
                        if (value != null) _favoritesOnly = false;
                        _applyCatalogFilter();
                      });
                    },
                    onFavorites: () {
                      widget.controller.logPosAction('catalog_favorites');
                      setState(() {
                        _favoritesOnly = !_favoritesOnly;
                        if (_favoritesOnly) _categoryId = null;
                        _applyCatalogFilter();
                      });
                    },
                    onBarcode: _barcode,
                    onProduct: _addProduct,
                    onProductLongPress: _addProductBatch,
                  );
                  if (constraints.maxWidth < 900) return catalog;
                  return Row(children: [
                    Expanded(flex: 3, child: catalog),
                    SizedBox(
                      width: 420,
                      child: _CartPanel(
                        cart: _cart,
                        preview: _preview,
                        loadingPreview: _loadingPreview,
                        discount: _discount,
                        cashReady: _checkoutReady,
                        customer: _draft.customer,
                        allowCustomer: _canViewCustomers,
                        onCustomer: _selectCustomer,
                        onRemoveCustomer: _removeCustomer,
                        allowWaiveFee: _serviceFeeWaived ||
                            (_preview != null &&
                                _preview!.serviceFeeRate != '0.00'),
                        serviceFeeWaived: _serviceFeeWaived,
                        onServiceFee: _toggleServiceFee,
                        showServiceFeeMenu: true,
                        onEdit: _editCartItem,
                        onCheckout: _checkout,
                      ),
                    ),
                  ]);
                }),
        ),
      );
}

class _CartPage extends StatelessWidget {
  const _CartPage({
    required this.draft,
    required this.panel,
    required this.allowDiscount,
    required this.allowCustomer,
    required this.allowWaiveFee,
    required this.onCustomer,
    required this.onRemoveCustomer,
    required this.onDiscount,
    required this.onRemoveDiscount,
    required this.onServiceFee,
    required this.onClear,
  });
  final QuickSaleDraft draft;
  final Widget Function() panel;
  final bool allowDiscount;
  final bool allowCustomer;
  final bool allowWaiveFee;
  final Future<void> Function() onCustomer;
  final VoidCallback onRemoveCustomer;
  final Future<void> Function() onDiscount;
  final VoidCallback onRemoveDiscount;
  final Future<void> Function() onServiceFee;
  final Future<void> Function() onClear;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Carrinho'),
          actions: [
            PopupMenuButton<String>(
              onSelected: (action) {
                switch (action) {
                  case 'customer':
                    onCustomer();
                    break;
                  case 'remove_customer':
                    onRemoveCustomer();
                    break;
                  case 'discount':
                    onDiscount();
                    break;
                  case 'remove_discount':
                    onRemoveDiscount();
                    break;
                  case 'fee':
                    unawaited(onServiceFee());
                    break;
                  case 'clear':
                    onClear();
                    break;
                }
              },
              itemBuilder: (_) => [
                if (allowCustomer)
                  PopupMenuItem(
                    value: 'customer',
                    child: Text(draft.customer == null
                        ? 'Adicionar cliente'
                        : 'Alterar cliente'),
                  ),
                if (draft.customer != null)
                  const PopupMenuItem(
                    value: 'remove_customer',
                    child: Text('Remover cliente'),
                  ),
                if (allowDiscount)
                  PopupMenuItem(
                    value: 'discount',
                    child: Text(draft.discount.isZero
                        ? 'Aplicar desconto na venda'
                        : 'Alterar desconto'),
                  ),
                if (allowDiscount && !draft.discount.isZero)
                  const PopupMenuItem(
                    value: 'remove_discount',
                    child: Text('Remover desconto'),
                  ),
                if (allowWaiveFee)
                  PopupMenuItem(
                    value: 'fee',
                    child: Text(draft.serviceFeeWaived
                        ? 'Restaurar taxa de serviço'
                        : 'Isentar taxa de serviço'),
                  ),
                if (draft.cart.isNotEmpty)
                  const PopupMenuItem(
                    value: 'clear',
                    child: Text('Apagar carrinho'),
                  ),
              ],
            ),
          ],
        ),
        body: AnimatedBuilder(animation: draft, builder: (_, __) => panel()),
      );
}

class _CheckoutPage extends StatefulWidget {
  const _CheckoutPage({
    required this.controller,
    required this.draft,
    required this.options,
    required this.preview,
    required this.onSaleCompleted,
  });
  final AppController controller;
  final QuickSaleDraft draft;
  final QuickSaleCheckoutOptions options;
  final QuickSalePreview preview;
  final Future<void> Function() onSaleCompleted;

  @override
  State<_CheckoutPage> createState() => _CheckoutPageState();
}

class _CheckoutPageState extends State<_CheckoutPage> {
  QuickSaleResult? _result;

  Future<void> _finalize(
      int sessionId, List<Map<String, dynamic>> payments) async {
    final result = await widget.controller.finalizeQuickSale(
      items: widget.draft.cart
          .map((item) => item.toJson())
          .toList(growable: false),
      cashSessionId: sessionId,
      payments: payments,
      discount: widget.draft.discount.toJson(),
      serviceFeeWaived: widget.draft.serviceFeeWaived,
      customer: widget.draft.customer,
      discountAuthorization: widget.draft.discountAuthorization,
      itemDiscountAuthorization: widget.draft.itemDiscountAuthorization,
      serviceFeeAuthorization: widget.draft.serviceFeeAuthorization,
    );
    if (!mounted || result == null) return;
    await widget.onSaleCompleted();
    if (mounted) setState(() => _result = result);
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: widget.controller,
        builder: (_, __) => PopScope(
          canPop: !widget.controller.finalizingSale,
          child: Scaffold(
            body: _result == null
                ? _CheckoutDialog(
                    options: widget.options,
                    preview: widget.preview,
                    finalizing: widget.controller.finalizingSale,
                    error: widget.controller.saleFinalizationError,
                    onConfirm: _finalize,
                  )
                : _SaleSuccessPage(
                    result: _result!,
                    onNewSale: () => Navigator.of(context)
                        .popUntil((route) => route.isFirst),
                  ),
          ),
        ),
      );
}

class _CashRequiredPanel extends StatelessWidget {
  const _CashRequiredPanel({
    required this.options,
    required this.canOpenCash,
    required this.onOpenCash,
  });
  final QuickSaleCheckoutOptions options;
  final bool canOpenCash;
  final Future<void> Function() onOpenCash;

  @override
  Widget build(BuildContext context) => Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 440),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.point_of_sale_rounded,
                  size: 52, color: Color(0xff3454d1)),
              const SizedBox(height: 16),
              Text('Abra um caixa para vender',
                  style: Theme.of(context)
                      .textTheme
                      .headlineSmall
                      ?.copyWith(fontWeight: FontWeight.w800),
                  textAlign: TextAlign.center),
              const SizedBox(height: 8),
              Text(
                options.paymentMethods.isEmpty
                    ? 'Não há forma de pagamento ativa para esta filial.'
                    : !canOpenCash
                        ? 'Não há caixa aberto e seu usuário não possui permissão para abrir um caixa.'
                        : options.cashBindingMode == 'FIXED' &&
                                !options.fixedCashAvailable
                            ? 'O caixa fixo deste dispositivo não está configurado ou não está ativo.'
                            : options.cashBindingMode == 'FIXED'
                                ? 'Abra uma sessão no caixa ${options.fixedRegisterName ?? 'fixo'} para continuar.'
                                : 'Não há sessão de caixa aberta disponível para este dispositivo.',
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              if (options.paymentMethods.isNotEmpty && canOpenCash)
                FilledButton.icon(
                  onPressed: () => unawaited(onOpenCash()),
                  icon: const Icon(Icons.lock_open_rounded),
                  label: const Text('ABRIR CAIXA'),
                ),
            ]),
          ),
        ),
      );
}

class _MobileCartBar extends StatelessWidget {
  const _MobileCartBar({
    required this.itemCount,
    required this.preview,
    required this.updating,
    required this.onTap,
  });

  final int itemCount;
  final QuickSalePreview? preview;
  final bool updating;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => SafeArea(
        top: false,
        child: Material(
          color: const Color(0xff3454d1),
          child: InkWell(
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
              child: Row(children: [
                const Icon(Icons.shopping_cart_rounded, color: Colors.white),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '$itemCount ${itemCount == 1 ? 'item' : 'itens'}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.w700),
                  ),
                ),
                Flexible(
                  child: Text(
                    updating
                        ? 'Atualizando...'
                        : formatMoney(preview?.total ?? '0.00'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: Colors.white, fontWeight: FontWeight.w800),
                  ),
                ),
                const SizedBox(width: 8),
                const Text(
                  'VER CARRINHO',
                  style: TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w900),
                ),
              ]),
            ),
          ),
        ),
      );
}

class _CatalogPanel extends StatelessWidget {
  const _CatalogPanel({
    required this.search,
    required this.loading,
    required this.products,
    required this.categories,
    required this.categoryId,
    required this.favoritesOnly,
    required this.onCategory,
    required this.onFavorites,
    required this.onBarcode,
    required this.onProduct,
    required this.onProductLongPress,
  });
  final TextEditingController search;
  final bool loading;
  final List<QuickSaleProduct> products;
  final List<QuickSaleCategory> categories;
  final int? categoryId;
  final bool favoritesOnly;
  final ValueChanged<int?> onCategory;
  final VoidCallback onFavorites;
  final VoidCallback onBarcode;
  final ValueChanged<QuickSaleProduct> onProduct;
  final ValueChanged<QuickSaleProduct> onProductLongPress;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.all(16),
        child: Column(children: [
          Row(children: [
            Expanded(
                child: TextField(
              controller: search,
              decoration: const InputDecoration(
                labelText: 'Buscar produto ou código',
                prefixIcon: Icon(Icons.search_rounded),
              ),
            )),
            IconButton(
                onPressed: onBarcode,
                icon: const Icon(Icons.qr_code_scanner_rounded),
                tooltip: 'Código de barras'),
          ]),
          const SizedBox(height: 12),
          SizedBox(
              height: 42,
              child: ListView(scrollDirection: Axis.horizontal, children: [
                Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                        label: const Text('TODOS'),
                        selected: categoryId == null,
                        selectedColor: const Color(0xff3454d1),
                        labelStyle: TextStyle(
                            color: categoryId == null
                                ? Colors.white
                                : const Color(0xff1e293b),
                            fontWeight: FontWeight.w700),
                        onSelected: (_) => onCategory(null))),
                Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: FilterChip(
                      label: const Text('FAVORITOS'),
                      selected: favoritesOnly,
                      selectedColor: const Color(0xff3454d1),
                      labelStyle: TextStyle(
                          color: favoritesOnly
                              ? Colors.white
                              : const Color(0xff1e293b),
                          fontWeight: FontWeight.w700),
                      onSelected: (_) => onFavorites(),
                      avatar: const Icon(Icons.star_rounded, size: 18),
                    )),
                for (final category in categories)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                        label: Text(category.name.toUpperCase()),
                        selected: categoryId == category.id,
                        selectedColor: const Color(0xff3454d1),
                        labelStyle: TextStyle(
                            color: categoryId == category.id
                                ? Colors.white
                                : const Color(0xff1e293b),
                            fontWeight: FontWeight.w700),
                        onSelected: (_) => onCategory(category.id)),
                  ),
              ])),
          const SizedBox(height: 12),
          Expanded(
              child: loading
                  ? const Center(child: CircularProgressIndicator())
                  : products.isEmpty
                      ? const Center(child: Text('Nenhum produto disponível.'))
                      : LayoutBuilder(builder: (context, constraints) {
                          final columns = constraints.maxWidth >= 1100
                              ? 5
                              : constraints.maxWidth >= 780
                                  ? 4
                                  : 3;
                          return GridView.builder(
                            gridDelegate:
                                SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: columns,
                              mainAxisSpacing: 8,
                              crossAxisSpacing: 8,
                              childAspectRatio: .76,
                            ),
                            itemCount: products.length,
                            itemBuilder: (context, index) => _ProductCard(
                              product: products[index],
                              onTap: () => onProduct(products[index]),
                              onLongPress: () =>
                                  onProductLongPress(products[index]),
                            ),
                          );
                        })),
        ]),
      );
}

class _ProductCard extends StatefulWidget {
  const _ProductCard({
    required this.product,
    required this.onTap,
    required this.onLongPress,
  });
  final QuickSaleProduct product;
  final VoidCallback onTap;
  final VoidCallback onLongPress;

  @override
  State<_ProductCard> createState() => _ProductCardState();
}

class _ProductCardState extends State<_ProductCard>
    with SingleTickerProviderStateMixin {
  late final AnimationController _feedback = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 200),
  );
  late final Animation<double> _scale = TweenSequence<double>([
    TweenSequenceItem(tween: Tween(begin: 1, end: 1.035), weight: 45),
    TweenSequenceItem(tween: Tween(begin: 1.035, end: 1), weight: 55),
  ]).animate(_feedback);

  @override
  void dispose() {
    _feedback.dispose();
    super.dispose();
  }

  void _add() {
    _feedback.forward(from: 0);
    widget.onTap();
  }

  @override
  Widget build(BuildContext context) => ScaleTransition(
        scale: _scale,
        child: InkWell(
          borderRadius: BorderRadius.circular(18),
          onTap: _add,
          onLongPress: widget.onLongPress,
          child: Ink(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: const Color(0xffe2e8f0))),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(
                child: Stack(children: [
                  Positioned.fill(
                      child: _ProductImage(url: widget.product.imageUrl)),
                  if (widget.product.stockApplicable &&
                      !widget.product.stockAvailable)
                    Positioned(
                      right: 4,
                      bottom: 4,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: widget.product.canSell
                              ? const Color(0xff9a6700)
                              : const Color(0xffb42318),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: const Padding(
                          padding:
                              EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                          child: Text(
                            'SEM ESTOQUE',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 9,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                      ),
                    ),
                ]),
              ),
              const SizedBox(height: 6),
              Text(widget.product.name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 2),
              Text(formatMoney(widget.product.price),
                  style: const TextStyle(
                      color: Color(0xff3454d1), fontWeight: FontWeight.w800)),
            ]),
          ),
        ),
      );
}

class _ProductImage extends StatelessWidget {
  const _ProductImage({this.url});
  final String? url;
  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: ColoredBox(
          color: const Color(0xffeff3ff),
          child: SizedBox.expand(
              child: url == null || url!.isEmpty
                  ? const Icon(Icons.inventory_2_outlined,
                      color: Color(0xff3454d1), size: 32)
                  : Image.network(url!,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => const Icon(
                          Icons.inventory_2_outlined,
                          color: Color(0xff3454d1),
                          size: 32))),
        ),
      );
}

class _CartPanel extends StatelessWidget {
  const _CartPanel({
    required this.cart,
    required this.preview,
    required this.loadingPreview,
    required this.discount,
    required this.cashReady,
    required this.customer,
    required this.allowCustomer,
    required this.onCustomer,
    required this.onRemoveCustomer,
    required this.allowWaiveFee,
    required this.serviceFeeWaived,
    required this.onServiceFee,
    required this.showServiceFeeMenu,
    required this.onEdit,
    required this.onCheckout,
  });
  final List<QuickSaleCartItem> cart;
  final QuickSalePreview? preview;
  final bool loadingPreview;
  final QuickSaleDiscountIntent discount;
  final bool cashReady;
  final QuickSaleCustomer? customer;
  final bool allowCustomer;
  final Future<void> Function() onCustomer;
  final VoidCallback onRemoveCustomer;
  final bool allowWaiveFee;
  final bool serviceFeeWaived;
  final Future<void> Function() onServiceFee;
  final bool showServiceFeeMenu;
  final ValueChanged<int> onEdit;
  final VoidCallback onCheckout;

  String _itemDetails(QuickSaleCartItem item) {
    final modifiers = <String>[];
    for (final selected in item.modifiers) {
      final optionId = int.tryParse('${selected['option']}');
      if (optionId == null) continue;
      QuickSaleModifierOption? option;
      for (final group in item.product.modifierGroups) {
        for (final candidate in group.options) {
          if (candidate.id == optionId) option = candidate;
        }
      }
      if (option != null) {
        modifiers.add('${selected['quantity'] ?? '1'}x ${option.name}');
      }
    }
    return [
      if (modifiers.isNotEmpty) modifiers.join(' • '),
      if (item.notes.isNotEmpty) 'Obs: ${item.notes}',
      if (!item.discount.isZero)
        'Desconto ${item.discount.isPercentage ? "(%)" : "(R\$)"}: ${item.discount.value}',
    ].join('\n');
  }

  String _provisionalLineTotal(QuickSaleCartItem item) {
    var unitPrice =
        double.tryParse(item.product.price.replaceAll(',', '.')) ?? 0;
    for (final selected in item.modifiers) {
      final optionId = int.tryParse('${selected['option']}');
      if (optionId == null) continue;
      QuickSaleModifierOption? option;
      for (final group in item.product.modifierGroups) {
        for (final candidate in group.options) {
          if (candidate.id == optionId) option = candidate;
        }
      }
      if (option != null) {
        final optionQuantity = double.tryParse(
                '${selected['quantity'] ?? '1'}'.replaceAll(',', '.')) ??
            1;
        unitPrice +=
            (double.tryParse(option.additionalPrice.replaceAll(',', '.')) ??
                    0) *
                optionQuantity;
      }
    }
    final quantity = double.tryParse(item.quantity.replaceAll(',', '.')) ?? 0;
    return (unitPrice * quantity).toStringAsFixed(2);
  }

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.white,
        child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 4),
                  Expanded(
                      child: cart.isEmpty
                          ? const Center(
                              child: Text(
                                  'Adicione produtos para iniciar a venda.'))
                          : ListView.separated(
                              itemCount: cart.length,
                              separatorBuilder: (_, __) =>
                                  const Divider(height: 1),
                              itemBuilder: (context, index) {
                                final item = cart[index];
                                final details = _itemDetails(item);
                                final officialLine =
                                    preview?.itemFor(item.clientItemId);
                                return InkWell(
                                  onTap: () => onEdit(index),
                                  child: Padding(
                                    padding:
                                        const EdgeInsets.symmetric(vertical: 5),
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Row(children: [
                                          Expanded(
                                            child: Text(item.product.name,
                                                maxLines: 2,
                                                overflow: TextOverflow.ellipsis,
                                                style: const TextStyle(
                                                    fontWeight:
                                                        FontWeight.w700)),
                                          ),
                                          const SizedBox(width: 8),
                                          Text(
                                              officialLine == null
                                                  ? formatMoney(
                                                      _provisionalLineTotal(
                                                          item))
                                                  : formatMoney(
                                                      officialLine.lineTotal),
                                              style: const TextStyle(
                                                  color: Color(0xff3454d1),
                                                  fontWeight: FontWeight.w800)),
                                        ]),
                                        if (details.isNotEmpty)
                                          Padding(
                                            padding:
                                                const EdgeInsets.only(top: 3),
                                            child: Text(details,
                                                maxLines: 3,
                                                overflow:
                                                    TextOverflow.ellipsis),
                                          ),
                                        Text('Qtd. ${item.quantity}',
                                            style:
                                                const TextStyle(fontSize: 12)),
                                      ],
                                    ),
                                  ),
                                );
                              },
                            )),
                  if (loadingPreview)
                    const Padding(
                      padding: EdgeInsets.only(top: 6),
                      child: Row(children: [
                        SizedBox(
                          height: 12,
                          width: 12,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                        SizedBox(width: 6),
                        Text('Atualizando...', style: TextStyle(fontSize: 12)),
                      ]),
                    ),
                  if (preview != null) ...[
                    const SizedBox(height: 8),
                    _AmountRow(label: 'Subtotal', value: preview!.subtotal),
                    if (!discount.isZero)
                      _AmountRow(
                        label: discount.isPercentage
                            ? 'Desconto (${discount.value}%)'
                            : 'Desconto (R\$)',
                        value: preview!.discount,
                        negative: true,
                      ),
                    _AmountRow(
                        label: 'Promoções',
                        value: preview!.promotionDiscountTotal,
                        negative: true),
                    _AmountRow(
                        label: 'Descontos por item',
                        value: preview!.itemDiscountTotal,
                        negative: true),
                    _AmountRow(
                        label: 'Taxa de serviço',
                        value: preview!.serviceFeeAmount),
                    _AmountRow(
                        label: 'Total oficial',
                        value: preview!.total,
                        strong: true),
                  ],
                  const SizedBox(height: 12),
                  if (allowCustomer) ...[
                    if (customer == null)
                      OutlinedButton.icon(
                        onPressed: () => unawaited(onCustomer()),
                        icon: const Icon(Icons.person_add_alt_1_outlined),
                        label: const Text('ADICIONAR CLIENTE'),
                      )
                    else
                      Row(children: [
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: () => unawaited(onCustomer()),
                            icon: const Icon(Icons.person_outline),
                            label: Text(customer!.name,
                                maxLines: 1, overflow: TextOverflow.ellipsis),
                          ),
                        ),
                        IconButton(
                          tooltip: 'Remover cliente',
                          onPressed: onRemoveCustomer,
                          icon: const Icon(Icons.close),
                        ),
                      ]),
                    const SizedBox(height: 8),
                  ],
                  if (showServiceFeeMenu && allowWaiveFee)
                    Align(
                      alignment: Alignment.centerRight,
                      child: PopupMenuButton<String>(
                        tooltip: 'Mais opções',
                        onSelected: (_) => unawaited(onServiceFee()),
                        itemBuilder: (_) => [
                          PopupMenuItem(
                            value: 'fee',
                            child: Text(serviceFeeWaived
                                ? 'Restaurar taxa de serviço'
                                : 'Isentar taxa de serviço'),
                          ),
                        ],
                      ),
                    ),
                  FilledButton(
                      onPressed: cart.isEmpty ||
                              preview == null ||
                              loadingPreview ||
                              !cashReady
                          ? null
                          : onCheckout,
                      child: const Text('IR PARA PAGAMENTO')),
                ])),
      );
}

class _AmountRow extends StatelessWidget {
  const _AmountRow(
      {required this.label,
      required this.value,
      this.negative = false,
      this.strong = false});
  final String label;
  final String value;
  final bool negative;
  final bool strong;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
        Text(label,
            style: TextStyle(
                fontWeight: strong ? FontWeight.w800 : FontWeight.w400)),
        Text('${negative ? '- ' : ''}${formatMoney(value)}',
            style: TextStyle(
                fontWeight: strong ? FontWeight.w800 : FontWeight.w500)),
      ]));
}

class _CustomerPickerDialog extends StatefulWidget {
  const _CustomerPickerDialog(
      {required this.controller, required this.canCreate});
  final AppController controller;
  final bool canCreate;

  @override
  State<_CustomerPickerDialog> createState() => _CustomerPickerDialogState();
}

class _CustomerPickerDialogState extends State<_CustomerPickerDialog> {
  final _search = TextEditingController();
  List<QuickSaleCustomer> _customers = const [];
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
    final customers = await widget.controller.quickSaleCustomers(_search.text);
    if (!mounted) return;
    setState(() {
      _customers = customers ?? const [];
      _loading = false;
    });
  }

  Future<void> _create() async {
    final customer = await showDialog<QuickSaleCustomer>(
      context: context,
      builder: (_) => _CustomerCreateDialog(controller: widget.controller),
    );
    if (customer != null && mounted) Navigator.of(context).pop(customer);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Cliente'),
        content: SizedBox(
          width: 460,
          height: 420,
          child: Column(children: [
            TextField(
              controller: _search,
              onChanged: (_) => unawaited(_load()),
              decoration: const InputDecoration(
                labelText: 'Nome, telefone, documento ou e-mail',
                prefixIcon: Icon(Icons.search),
              ),
            ),
            const SizedBox(height: 8),
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
                          ].join(' • ')),
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
              label: const Text('CADASTRAR'),
            ),
        ],
      );
}

class _CustomerCreateDialog extends StatefulWidget {
  const _CustomerCreateDialog({required this.controller});
  final AppController controller;

  @override
  State<_CustomerCreateDialog> createState() => _CustomerCreateDialogState();
}

class _CustomerCreateDialogState extends State<_CustomerCreateDialog> {
  final _name = TextEditingController();
  final _phone = TextEditingController();
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_name.text.trim().isEmpty || _saving) return;
    setState(() => _saving = true);
    final customer = await widget.controller.createQuickSaleCustomer(
      name: _name.text.trim(),
      phone: _phone.text.trim(),
    );
    if (!mounted) return;
    setState(() => _saving = false);
    if (customer != null) Navigator.of(context).pop(customer);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Cadastrar cliente'),
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
            decoration: const InputDecoration(labelText: 'Telefone'),
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

class _DiscountDialog extends StatefulWidget {
  const _DiscountDialog({required this.initial});
  final QuickSaleDiscountIntent initial;

  @override
  State<_DiscountDialog> createState() => _DiscountDialogState();
}

class _DiscountDialogState extends State<_DiscountDialog> {
  late String _type = widget.initial.type;
  final _value = TextEditingController();

  @override
  void dispose() {
    _value.dispose();
    super.dispose();
  }

  bool get _valid {
    final value = double.tryParse(_value.text.trim().replaceAll(',', '.'));
    return value != null &&
        value > 0 &&
        (_type == 'amount' ? value <= 999999999999.99 : value <= 100);
  }

  void _setType(String type) {
    if (_type == type) return;
    setState(() {
      _type = type;
      _value.clear();
    });
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('APLICAR DESCONTO'),
        content: SizedBox(
          width: 340,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Align(
              alignment: Alignment.centerLeft,
              child: Text('Tipo de desconto'),
            ),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(
                child: _DiscountTypeButton(
                  label: 'R\$',
                  selected: _type == 'amount',
                  onTap: () => _setType('amount'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _DiscountTypeButton(
                  label: '%',
                  selected: _type == 'percentage',
                  onTap: () => _setType('percentage'),
                ),
              ),
            ]),
            const SizedBox(height: 16),
            TextField(
              controller: _value,
              autofocus: true,
              onChanged: (_) => setState(() {}),
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(
                labelText: 'Valor',
                hintText: _type == 'percentage' ? 'Ex.: 10' : 'Ex.: 10,00',
                suffixText: _type == 'percentage' ? '%' : null,
                errorText: _value.text.isNotEmpty && !_valid
                    ? 'Informe um valor válido.'
                    : null,
              ),
            ),
          ]),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('CANCELAR')),
          FilledButton(
            onPressed: !_valid
                ? null
                : () => Navigator.of(context).pop(QuickSaleDiscountIntent(
                      type: _type,
                      value: _value.text.trim().replaceAll(',', '.'),
                    )),
            child: const Text('APLICAR'),
          ),
        ],
      );
}

class _DiscountTypeButton extends StatelessWidget {
  const _DiscountTypeButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Material(
        color: selected ? const Color(0xff3454d1) : const Color(0xfff1f5f9),
        borderRadius: BorderRadius.circular(10),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(10),
          child: Container(
            height: 48,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(10),
              border: Border.all(
                color: selected
                    ? const Color(0xff3454d1)
                    : const Color(0xffcbd5e1),
              ),
            ),
            child: Text(
              label,
              style: TextStyle(
                color: selected ? Colors.white : const Color(0xff1e293b),
                fontSize: 16,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ),
      );
}

class _BatchQuantityDialog extends StatefulWidget {
  const _BatchQuantityDialog({required this.productName});

  final String productName;

  @override
  State<_BatchQuantityDialog> createState() => _BatchQuantityDialogState();
}

class _BatchQuantityDialogState extends State<_BatchQuantityDialog> {
  final _quantity = TextEditingController(text: '1');

  bool get _valid =>
      (double.tryParse(_quantity.text.trim().replaceAll(',', '.')) ?? 0) > 0;

  void _adjust(int delta) {
    final current = int.tryParse(_quantity.text.trim()) ?? 1;
    final next = current + delta;
    if (next > 0) setState(() => _quantity.text = '$next');
  }

  @override
  void dispose() {
    _quantity.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('ADICIONAR EM LOTE'),
        content: SizedBox(
          width: 320,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Text(widget.productName,
                  style: const TextStyle(fontWeight: FontWeight.w800)),
            ),
            const SizedBox(height: 16),
            const Align(
              alignment: Alignment.centerLeft,
              child: Text('Quantidade'),
            ),
            const SizedBox(height: 6),
            Row(children: [
              IconButton(
                onPressed: () => _adjust(-1),
                icon: const Icon(Icons.remove_circle_outline),
                tooltip: 'Diminuir quantidade',
              ),
              Expanded(
                child: TextField(
                  controller: _quantity,
                  autofocus: true,
                  textAlign: TextAlign.center,
                  onChanged: (_) => setState(() {}),
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: InputDecoration(
                    errorText: _quantity.text.isNotEmpty && !_valid
                        ? 'Informe uma quantidade válida.'
                        : null,
                  ),
                ),
              ),
              IconButton(
                onPressed: () => _adjust(1),
                icon: const Icon(Icons.add_circle_outline),
                tooltip: 'Aumentar quantidade',
              ),
            ]),
          ]),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('CANCELAR'),
          ),
          FilledButton(
            onPressed: !_valid
                ? null
                : () => Navigator.of(context)
                    .pop(_quantity.text.trim().replaceAll(',', '.')),
            child: Text('ADICIONAR ${_quantity.text.trim()}'),
          ),
        ],
      );
}

class _DiscountAuthorizationDialog extends StatefulWidget {
  const _DiscountAuthorizationDialog({
    required this.authorizers,
    required this.onAuthorize,
  });

  final List<QuickSaleAuthorizer> authorizers;
  final Future<String?> Function(QuickSaleAuthorization authorization)
      onAuthorize;

  @override
  State<_DiscountAuthorizationDialog> createState() =>
      _DiscountAuthorizationDialogState();
}

class _DiscountAuthorizationDialogState
    extends State<_DiscountAuthorizationDialog> {
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
    String? error;
    try {
      error = await widget.onAuthorize(authorization);
    } finally {
      _pin.clear();
    }
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
                  labelText: 'PIN do autorizador', errorText: _error),
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

class _CartItemEditResult {
  const _CartItemEditResult.item(this.item, {this.itemDiscountAuthorization})
      : delete = false;
  const _CartItemEditResult.delete()
      : item = null,
        itemDiscountAuthorization = null,
        delete = true;
  final QuickSaleCartItem? item;
  final QuickSaleAuthorization? itemDiscountAuthorization;
  final bool delete;
}

class _EditCartItemDialog extends StatefulWidget {
  const _EditCartItemDialog({
    required this.item,
    required this.requiresItemAuthorization,
    required this.requestItemAuthorization,
  });
  final QuickSaleCartItem item;
  final bool requiresItemAuthorization;
  final Future<QuickSaleAuthorization?> Function() requestItemAuthorization;

  @override
  State<_EditCartItemDialog> createState() => _EditCartItemDialogState();
}

class _EditCartItemDialogState extends State<_EditCartItemDialog> {
  late QuickSaleCartItem _item = widget.item;
  QuickSaleAuthorization? _itemDiscountAuthorization;

  Future<void> _editModifiers() async {
    final updated = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) => _ItemEditorDialog(product: _item.product, initial: _item),
    );
    if (updated != null && mounted) setState(() => _item = updated);
  }

  Future<void> _editNotes() async {
    final notes = TextEditingController(text: _item.notes);
    final value = await showDialog<String>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Observação do item'),
        content: TextField(
            controller: notes, maxLines: 3, maxLength: 1000, autofocus: true),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('CANCELAR')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(notes.text.trim()),
              child: const Text('SALVAR')),
        ],
      ),
    );
    notes.dispose();
    if (value != null && mounted) {
      setState(() => _item = _item.copyWith(notes: value));
    }
  }

  Future<void> _editDiscount() async {
    final discount = await showDialog<QuickSaleDiscountIntent>(
      context: context,
      builder: (_) => _DiscountDialog(initial: _item.discount),
    );
    if (discount == null || !mounted) return;
    QuickSaleAuthorization? authorization;
    if (widget.requiresItemAuthorization) {
      authorization = await widget.requestItemAuthorization();
      if (authorization == null || !mounted) return;
    }
    setState(() {
      _item = _item.copyWith(discount: discount);
      _itemDiscountAuthorization = authorization;
    });
  }

  Future<void> _delete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Excluir produto?'),
        content: const Text('Este produto será removido do carrinho.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('CANCELAR')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('EXCLUIR'),
          ),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      Navigator.of(context).pop(const _CartItemEditResult.delete());
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('EDITAR PRODUTO'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          Align(
            alignment: Alignment.centerLeft,
            child: Text(_item.product.name,
                style: const TextStyle(fontWeight: FontWeight.w800)),
          ),
          Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            IconButton(
              onPressed: () {
                final value = (int.tryParse(_item.quantity) ?? 1) - 1;
                if (value > 0) {
                  setState(() => _item = _item.copyWith(quantity: '$value'));
                }
              },
              icon: const Icon(Icons.remove_circle_outline),
            ),
            Text(_item.quantity,
                style:
                    const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
            IconButton(
              onPressed: () => setState(() => _item = _item.copyWith(
                    quantity: '${(int.tryParse(_item.quantity) ?? 1) + 1}',
                  )),
              icon: const Icon(Icons.add_circle_outline),
            ),
          ]),
          if (_item.product.modifierGroups.isNotEmpty)
            ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.tune),
                title: const Text('Editar modificadores'),
                onTap: _editModifiers),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.edit_note),
            title: Text(_item.notes.isEmpty
                ? 'Adicionar observação'
                : 'Editar observação'),
            onTap: _editNotes,
          ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.sell_outlined),
            title: Text(_item.discount.isZero
                ? 'Aplicar desconto no item'
                : 'Alterar desconto no item'),
            onTap: _editDiscount,
          ),
          if (!_item.discount.isZero)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.remove_circle_outline),
              title: const Text('Remover desconto do item'),
              onTap: () => setState(() {
                _item =
                    _item.copyWith(discount: const QuickSaleDiscountIntent());
                _itemDiscountAuthorization = null;
              }),
            ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.delete_outline, color: Colors.red),
            title: const Text('Excluir produto',
                style: TextStyle(color: Colors.red)),
            onTap: _delete,
          ),
        ]),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('CANCELAR')),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(
              _CartItemEditResult.item(
                _item,
                itemDiscountAuthorization: _itemDiscountAuthorization,
              ),
            ),
            child: const Text('SALVAR'),
          ),
        ],
      );
}

class _ItemEditorDialog extends StatefulWidget {
  const _ItemEditorDialog({required this.product, this.initial});
  final QuickSaleProduct product;
  final QuickSaleCartItem? initial;
  @override
  State<_ItemEditorDialog> createState() => _ItemEditorDialogState();
}

class _ItemEditorDialogState extends State<_ItemEditorDialog> {
  final Map<int, int> _quantities = {};
  String? _validation;

  @override
  void initState() {
    super.initState();
    for (final modifier
        in widget.initial?.modifiers ?? const <Map<String, dynamic>>[]) {
      final option = modifier['option'] as int?;
      if (option != null) {
        _quantities[option] = int.tryParse('${modifier['quantity']}') ?? 1;
      }
    }
  }

  void _toggle(QuickSaleModifierGroup group, QuickSaleModifierOption option,
      bool selected) {
    setState(() {
      if (selected) {
        if (group.maxSelections == 1) {
          for (final candidate in group.options) {
            _quantities.remove(candidate.id);
          }
        }
        _quantities[option.id] = 1;
      } else {
        _quantities.remove(option.id);
      }
      _validation = null;
    });
  }

  void _increase(QuickSaleModifierGroup group, QuickSaleModifierOption option) {
    setState(() {
      if (group.maxSelections == 1) {
        for (final candidate in group.options) {
          _quantities.remove(candidate.id);
        }
      }
      _quantities[option.id] = (_quantities[option.id] ?? 0) + 1;
      _validation = null;
    });
  }

  void _decrease(QuickSaleModifierOption option) {
    setState(() {
      final current = _quantities[option.id] ?? 0;
      if (current <= 1) {
        _quantities.remove(option.id);
      } else {
        _quantities[option.id] = current - 1;
      }
      _validation = null;
    });
  }

  int? _selectedOptionFor(QuickSaleModifierGroup group) {
    for (final option in group.options) {
      if (_quantities.containsKey(option.id)) return option.id;
    }
    return null;
  }

  double _number(String? value) =>
      double.tryParse((value ?? '0').replaceAll(',', '.')) ?? 0;

  String _formatQuantity(double value) =>
      value == value.roundToDouble() ? '${value.toInt()}' : value.toString();

  String? _groupValidation(QuickSaleModifierGroup group) {
    final selected =
        group.options.where((option) => _quantities.containsKey(option.id));
    final selectionCount = selected.length;
    final totalQuantity = selected.fold<double>(
      0,
      (total, option) => total + (_quantities[option.id] ?? 0),
    );
    if (selectionCount < group.minSelections ||
        (group.required && selectionCount == 0)) {
      final missing = (group.minSelections - selectionCount).clamp(1, 999);
      return 'Selecione mais $missing ${missing == 1 ? 'opção' : 'opções'} em ${group.name}.';
    }
    if (group.maxSelections != null && selectionCount > group.maxSelections!) {
      return 'Remova ${selectionCount - group.maxSelections!} ${selectionCount - group.maxSelections! == 1 ? 'opção' : 'opções'} em ${group.name}.';
    }
    final required = _number(group.requiredQuantity) *
        (int.tryParse(widget.initial?.quantity ?? '1') ?? 1);
    if (group.requiredQuantity != null && totalQuantity != required) {
      final difference = (required - totalQuantity).abs();
      return totalQuantity < required
          ? 'Selecione mais ${_formatQuantity(difference)} unidade(s) em ${group.name}.'
          : 'Remova ${_formatQuantity(difference)} unidade(s) em ${group.name}.';
    }
    final minimum = _number(group.minTotalQuantity);
    if (minimum > 0 && totalQuantity < minimum) {
      return 'Selecione mais ${_formatQuantity(minimum - totalQuantity)} unidade(s) em ${group.name}.';
    }
    final maximum =
        group.maxTotalQuantity == null ? null : _number(group.maxTotalQuantity);
    if (maximum != null && totalQuantity > maximum) {
      return 'Remova ${_formatQuantity(totalQuantity - maximum)} unidade(s) em ${group.name}.';
    }
    return null;
  }

  void _save() {
    for (final group in widget.product.modifierGroups) {
      final validation = _groupValidation(group);
      if (validation != null) {
        setState(() => _validation = validation);
        return;
      }
    }
    Navigator.of(context).pop(QuickSaleCartItem(
      clientItemId: widget.initial?.clientItemId ?? createIdempotencyKey(),
      product: widget.product,
      quantity: widget.initial?.quantity ?? '1',
      notes: widget.initial?.notes ?? '',
      discount: widget.initial?.discount ?? const QuickSaleDiscountIntent(),
      modifiers: _quantities.entries
          .map((entry) => {'option': entry.key, 'quantity': '${entry.value}'})
          .toList(growable: false),
    ));
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.initial == null
            ? 'Adicionar ${widget.product.name}'
            : 'Editar ${widget.product.name}'),
        content: SizedBox(
            width: 460,
            child: SingleChildScrollView(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
              for (final group in widget.product.modifierGroups) ...[
                Align(
                    alignment: Alignment.centerLeft,
                    child: Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Text(
                          '${group.name}${group.required ? ' *' : ''}',
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ))),
                for (final option in group.options)
                  Row(children: [
                    Expanded(
                        child: group.allowOptionQuantity
                            ? ListTile(
                                contentPadding: EdgeInsets.zero,
                                onTap: () => _increase(group, option),
                                leading: Icon(
                                  _quantities.containsKey(option.id)
                                      ? Icons.add_circle
                                      : Icons.add_circle_outline,
                                  color: const Color(0xff3454d1),
                                ),
                                title: Text(option.name),
                                subtitle:
                                    Text(formatMoney(option.additionalPrice)),
                              )
                            : group.maxSelections == 1
                                ? RadioListTile<int>(
                                    contentPadding: EdgeInsets.zero,
                                    value: option.id,
                                    groupValue: _selectedOptionFor(group),
                                    onChanged: (value) =>
                                        _toggle(group, option, value != null),
                                    title: Text(option.name),
                                    subtitle: Text(
                                        formatMoney(option.additionalPrice)),
                                  )
                                : CheckboxListTile(
                                    contentPadding: EdgeInsets.zero,
                                    value: _quantities.containsKey(option.id),
                                    onChanged: (value) =>
                                        _toggle(group, option, value ?? false),
                                    title: Text(option.name),
                                    subtitle: Text(
                                        formatMoney(option.additionalPrice)),
                                  )),
                    if (group.allowOptionQuantity &&
                        _quantities.containsKey(option.id)) ...[
                      IconButton(
                          onPressed: () => _decrease(option),
                          icon: const Icon(Icons.remove)),
                      Text('${_quantities[option.id]}'),
                      IconButton(
                          onPressed: () => _increase(group, option),
                          icon: const Icon(Icons.add)),
                    ],
                  ]),
              ],
              if (_validation != null)
                Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(_validation!,
                        style: const TextStyle(color: Colors.red))),
            ]))),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('CANCELAR')),
          FilledButton(
              onPressed: _save,
              child: Text(widget.initial == null ? 'ADICIONAR' : 'SALVAR')),
        ],
      );
}

class _PaymentDraft {
  _PaymentDraft(this.method, {this.useRemaining = false})
      : amount = TextEditingController(),
        received = TextEditingController();
  final QuickSalePaymentMethod method;
  bool useRemaining;
  final TextEditingController amount;
  final TextEditingController received;
  void dispose() {
    amount.dispose();
    received.dispose();
  }
}

String _paymentMethodName(QuickSalePaymentMethod method) =>
    switch (method.code) {
      'cash' => 'Dinheiro',
      'pix' => 'PIX',
      'debit_card' => 'Cartão de débito',
      'credit_card' => 'Cartão de crédito',
      _ => method.name,
    };

class _CheckoutDialog extends StatefulWidget {
  const _CheckoutDialog({
    required this.options,
    required this.preview,
    required this.finalizing,
    required this.error,
    required this.onConfirm,
  });
  final QuickSaleCheckoutOptions options;
  final QuickSalePreview preview;
  final bool finalizing;
  final String? error;
  final Future<void> Function(
      int sessionId, List<Map<String, dynamic>> payments) onConfirm;
  @override
  State<_CheckoutDialog> createState() => _CheckoutDialogState();
}

class _CheckoutDialogState extends State<_CheckoutDialog> {
  late int _sessionId = widget.options.cashSessions.first.id;
  late final List<_PaymentDraft> _payments = [
    _PaymentDraft(
      widget.options.paymentMethods.first,
      useRemaining: widget.options.paymentMethods.first.code == 'cash',
    ),
  ];

  @override
  void initState() {
    super.initState();
    if (!_payments.first.useRemaining) {
      _payments.first.amount.text = widget.preview.total;
    }
  }

  @override
  void dispose() {
    for (final payment in _payments) {
      payment.dispose();
    }
    super.dispose();
  }

  double get _total =>
      double.tryParse(widget.preview.total.replaceAll(',', '.')) ?? 0;
  double get _entered => _payments
      .where((item) => !item.useRemaining)
      .fold<double>(
        0,
        (sum, item) =>
            sum + (double.tryParse(item.amount.text.replaceAll(',', '.')) ?? 0),
      );
  double get _remaining =>
      (_total - _entered).clamp(0, double.infinity).toDouble();
  bool get _hasRemainingCash =>
      _payments.where((item) => item.useRemaining).length == 1;

  double _paymentAmount(_PaymentDraft payment) => payment.useRemaining
      ? _remaining
      : double.tryParse(payment.amount.text.replaceAll(',', '.')) ?? 0;

  List<int> _cashSuggestions(_PaymentDraft payment) {
    final due = _paymentAmount(payment);
    final suggestions = <int>[20, 50, 100, 200];
    if (due > 100 && due <= 150) suggestions.insert(3, 150);
    return suggestions.where((value) => value >= due).take(3).toList();
  }

  void _setCashReceived(_PaymentDraft payment, double value) {
    setState(() => payment.received.text = value.toStringAsFixed(2));
  }

  bool get _validPayments {
    if (_payments.any((item) =>
        item.method.code == 'cash' && item.received.text.trim().isEmpty)) {
      return false;
    }
    if (_payments.any((item) =>
        !item.useRemaining &&
        (double.tryParse(item.amount.text.replaceAll(',', '.')) ?? 0) <= 0)) {
      return false;
    }
    if (_hasRemainingCash) {
      final remainingCash = _payments.firstWhere((item) => item.useRemaining);
      return _remaining > 0 &&
          (double.tryParse(remainingCash.received.text.replaceAll(',', '.')) ??
                  0) >=
              _remaining;
    }
    return (_entered - _total).abs() < .005;
  }

  Future<void> _submit() async {
    if (!_validPayments || widget.finalizing) return;
    final payload = _payments
        .map((item) => <String, dynamic>{
              'payment_method': item.method.id,
              'amount': item.useRemaining
                  ? 'remaining'
                  : item.amount.text.trim().replaceAll(',', '.'),
              if (item.method.code == 'cash' &&
                  item.received.text.trim().isNotEmpty)
                'received_amount':
                    item.received.text.trim().replaceAll(',', '.'),
            })
        .toList(growable: false);
    await widget.onConfirm(_sessionId, payload);
  }

  void _selectPaymentMethod(int index, QuickSalePaymentMethod method) {
    final previous = _payments[index];
    final next = _PaymentDraft(
      method,
      useRemaining: method.code == 'cash' && previous.useRemaining,
    );
    next.amount.text = previous.amount.text;
    next.received.text = previous.received.text;
    if (_payments.length == 1 &&
        !next.useRemaining &&
        next.amount.text.isEmpty) {
      next.amount.text = widget.preview.total;
    }
    setState(() {
      _payments[index] = next;
      previous.dispose();
    });
  }

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.white,
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(children: [
                    Text('Pagamento',
                        style: Theme.of(context)
                            .textTheme
                            .headlineSmall
                            ?.copyWith(fontWeight: FontWeight.w900)),
                    const Spacer(),
                    IconButton(
                        onPressed: widget.finalizing
                            ? null
                            : () => Navigator.of(context).pop(),
                        icon: const Icon(Icons.close)),
                  ]),
                  Text(formatMoney(widget.preview.total),
                      style: const TextStyle(
                          color: Color(0xff3454d1),
                          fontSize: 30,
                          fontWeight: FontWeight.w900)),
                  const SizedBox(height: 12),
                  if (widget.options.cashBindingMode == 'FLEXIBLE')
                    SizedBox(
                      height: 42,
                      child:
                          ListView(scrollDirection: Axis.horizontal, children: [
                        for (final session in widget.options.cashSessions)
                          Padding(
                            padding: const EdgeInsets.only(right: 8),
                            child: ChoiceChip(
                              label: Text(session.registerName),
                              selected: session.id == _sessionId,
                              selectedColor: const Color(0xff3454d1),
                              labelStyle: TextStyle(
                                  color: session.id == _sessionId
                                      ? Colors.white
                                      : const Color(0xff1e293b)),
                              onSelected: widget.finalizing
                                  ? null
                                  : (_) =>
                                      setState(() => _sessionId = session.id),
                            ),
                          ),
                      ]),
                    )
                  else
                    Text(
                        'Caixa fixo: ${widget.options.fixedRegisterName ?? widget.options.cashSessions.first.registerName}'),
                  const SizedBox(height: 12),
                  Expanded(
                    child: ListView(
                      children: [
                        for (var index = 0; index < _payments.length; index++)
                          _paymentRow(index),
                        OutlinedButton.icon(
                          onPressed: widget.finalizing
                              ? null
                              : () => setState(() => _payments.add(
                                  _PaymentDraft(
                                      widget.options.paymentMethods.first))),
                          icon: const Icon(Icons.add),
                          label: const Text('DIVIDIR PAGAMENTO'),
                        ),
                      ],
                    ),
                  ),
                  const Divider(),
                  _AmountRow(label: 'Pago', value: _entered.toStringAsFixed(2)),
                  _AmountRow(
                      label: 'Restante',
                      value: _remaining.toStringAsFixed(2),
                      strong: true),
                  const SizedBox(height: 8),
                  if (widget.error != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(widget.error!,
                          textAlign: TextAlign.center,
                          style: const TextStyle(color: Colors.red)),
                    ),
                  FilledButton(
                    onPressed:
                        _validPayments && !widget.finalizing ? _submit : null,
                    child: widget.finalizing
                        ? const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              SizedBox(
                                height: 18,
                                width: 18,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2),
                              ),
                              SizedBox(width: 10),
                              Text('FINALIZANDO VENDA...'),
                            ],
                          )
                        : Text(widget.error == null
                            ? 'CONFIRMAR VENDA'
                            : 'TENTAR NOVAMENTE'),
                  ),
                ]),
          ),
        ),
      );

  Widget _paymentRow(int index) {
    final payment = _payments[index];
    return Card(
        child: Padding(
            padding: const EdgeInsets.all(8),
            child: Column(children: [
              Row(children: [
                Text('Pagamento ${index + 1}',
                    style: const TextStyle(fontWeight: FontWeight.w800)),
                const Spacer(),
                if (_payments.length > 1)
                  IconButton(
                      onPressed: widget.finalizing
                          ? null
                          : () => setState(() {
                                _payments.removeAt(index).dispose();
                              }),
                      icon: const Icon(Icons.remove_circle_outline)),
              ]),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final method in widget.options.paymentMethods)
                    ChoiceChip(
                      label: Text(_paymentMethodName(method)),
                      selected: payment.method.id == method.id,
                      selectedColor: const Color(0xff3454d1),
                      labelStyle: TextStyle(
                          color: payment.method.id == method.id
                              ? Colors.white
                              : const Color(0xff1e293b),
                          fontWeight: FontWeight.w800),
                      onSelected: widget.finalizing
                          ? null
                          : (_) => _selectPaymentMethod(index, method),
                    ),
                ],
              ),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(
                    child: payment.useRemaining
                        ? Text(
                            'Usará o restante: ${formatMoney(_remaining.toStringAsFixed(2))}')
                        : TextField(
                            controller: payment.amount,
                            enabled: !widget.finalizing,
                            onChanged: (_) => setState(() {}),
                            keyboardType: const TextInputType.numberWithOptions(
                                decimal: true),
                            decoration: const InputDecoration(
                                labelText: 'Valor', prefixText: 'R\$ '))),
                if (payment.method.code == 'cash')
                  TextButton(
                      onPressed: widget.finalizing
                          ? null
                          : () => setState(() =>
                              payment.useRemaining = !payment.useRemaining),
                      child: Text(payment.useRemaining
                          ? 'INFORMAR VALOR'
                          : 'USAR RESTANTE')),
              ]),
              if (payment.method.code == 'cash')
                TextField(
                    controller: payment.received,
                    enabled: !widget.finalizing,
                    onChanged: (_) => setState(() {}),
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                        labelText: 'Valor recebido', prefixText: 'R\$ ')),
              if (payment.method.code == 'cash') ...[
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    ActionChip(
                      label: const Text('VALOR EXATO'),
                      onPressed:
                          widget.finalizing || _paymentAmount(payment) <= 0
                              ? null
                              : () => _setCashReceived(
                                  payment, _paymentAmount(payment)),
                    ),
                    for (final value in _cashSuggestions(payment))
                      ActionChip(
                        label: Text('R\$ $value'),
                        onPressed: widget.finalizing
                            ? null
                            : () => _setCashReceived(payment, value.toDouble()),
                      ),
                  ],
                ),
              ],
              if (payment.method.code == 'cash' &&
                  payment.received.text.trim().isNotEmpty)
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'Troco previsto: ${formatMoney(((double.tryParse(payment.received.text.replaceAll(',', '.')) ?? 0) - (payment.useRemaining ? _remaining : (double.tryParse(payment.amount.text.replaceAll(',', '.')) ?? 0))).clamp(0, double.infinity).toDouble().toStringAsFixed(2))}',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
            ])));
  }
}

class _SaleSuccessPage extends StatelessWidget {
  const _SaleSuccessPage({required this.result, required this.onNewSale});
  final QuickSaleResult result;
  final VoidCallback onNewSale;

  @override
  Widget build(BuildContext context) => SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.check_circle_rounded,
                  color: Color(0xff16803c), size: 68),
              const SizedBox(height: 16),
              Text('VENDA CONCLUÍDA',
                  style: Theme.of(context)
                      .textTheme
                      .headlineSmall
                      ?.copyWith(fontWeight: FontWeight.w900)),
              const SizedBox(height: 8),
              Text('Venda ${result.saleNumber}',
                  style: const TextStyle(fontWeight: FontWeight.w700)),
              Text(formatMoney(result.total),
                  style: const TextStyle(
                      color: Color(0xff3454d1),
                      fontSize: 30,
                      fontWeight: FontWeight.w900)),
              if (result.ticketNumbers.isNotEmpty) ...[
                const SizedBox(height: 12),
                Text('Tickets: ${result.ticketNumbers.join(', ')}'),
              ],
              const SizedBox(height: 24),
              FilledButton(
                onPressed: onNewSale,
                child: const Text('NOVA VENDA'),
              ),
            ]),
          ),
        ),
      );
}
