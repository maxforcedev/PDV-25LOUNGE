import 'dart:async';

import 'package:flutter/material.dart';

import '../cash/cash_page.dart';
import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../network/pos_api_error.dart';
import '../payments/shared_payment_page.dart';
import '../scanner/product_barcode_scanner_page.dart';
import '../sync/sync_center_page.dart';
import '../sync/sync_status_button.dart';
import 'sale_models.dart';
import 'sale_presentation.dart';
import 'shared_sale_item_editor_dialog.dart';
import 'shared_pos_widgets.dart';

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
  final Map<String, Map<String, dynamic>> _cartShortages = {};
  bool _catalogLocked = false;

  List<QuickSaleCartItem> get _cart => _draft.cart;

  Map<int, double> get _selectedQuantities =>
      _cart.fold(<int, double>{}, (quantities, item) {
        final quantity =
            double.tryParse(item.quantity.replaceAll(',', '.')) ?? 0;
        quantities[item.product.id] =
            (quantities[item.product.id] ?? 0) + quantity;
        return quantities;
      });
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
    await _resumeCheckout();
  }

  Future<void> _resumeCheckout() async {
    if (!mounted) return;
    final checkout = await widget.controller.recoverQuickSaleCheckout();
    if (!mounted || checkout == null) return;
    setState(() => _restoreCheckoutDraft(checkout));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Venda em andamento recuperada.')),
    );
  }

  void _restoreCheckoutDraft(QuickSaleCheckout checkout) {
    final productsById = {
      for (final product in _allCatalog) product.id: product
    };
    final items = <QuickSaleCartItem>[];
    for (final checkoutItem in checkout.items) {
      final input = checkoutItem.input;
      final product = productsById[int.tryParse('${input['product']}')] ??
          checkoutItem.recoveryProduct;
      if (product == null) {
        widget.controller.showTransientMessage(
            'Não foi possível restaurar todos os dados desta venda. Tente novamente.');
        return;
      }
      final modifiers = (input['modifiers'] as List? ?? const [])
          .whereType<Map>()
          .map((modifier) => Map<String, dynamic>.from(modifier))
          .toList(growable: false);
      final discount = input['discount'] is Map
          ? QuickSaleDiscountIntent.fromJson(
              Map<String, dynamic>.from(input['discount'] as Map))
          : const QuickSaleDiscountIntent();
      items.add(QuickSaleCartItem(
        clientItemId:
            input['client_item_id'] as String? ?? createIdempotencyKey(),
        product: product,
        quantity: input['quantity'] as String? ?? checkoutItem.quantity,
        modifiers: modifiers,
        notes: input['notes'] as String? ?? '',
        discount: discount,
      ));
    }
    _cart
      ..clear()
      ..addAll(items);
    _lastValidatedCart = List<QuickSaleCartItem>.of(items);
    _pendingCartMutations.clear();
    _cartShortages.clear();
    _preview = checkout.preview;
    _loadingPreview = false;
    _draft.customer = checkout.customer;
    _discount = checkout.discountIntent;
    _serviceFeeWaived = checkout.serviceFeeWaived;
    _catalogLocked = !checkout.canEditFinancials;
    _draft.changed();
  }

  Future<void> _openPayment(
      QuickSaleCheckout checkout, QuickSaleCheckoutOptions options) async {
    final result =
        await Navigator.of(context).push<QuickSaleResult>(MaterialPageRoute(
      builder: (_) => SharedPaymentPage(
        controller: widget.controller,
        options: options,
        checkout: checkout,
        onCompleted: (_) async {},
        onCancelled: () async {
          if (mounted) setState(_resetSaleDraftState);
          unawaited(_loadCheckoutOptions());
          unawaited(_loadCatalog());
        },
      ),
    ));
    if (!mounted) return;
    if (result != null) {
      setState(_resetSaleDraftState);
      unawaited(_loadCheckoutOptions());
      unawaited(_loadCatalog());
      await Navigator.of(context).push<void>(MaterialPageRoute(
        builder: (_) => QuickSaleCompletedPage(result: result),
      ));
      return;
    }
    final activeCheckout = await widget.controller.recoverQuickSaleCheckout();
    if (!mounted) return;
    setState(() {
      if (activeCheckout == null) {
        _catalogLocked = false;
        _resetSaleDraftState();
      } else {
        _restoreCheckoutDraft(activeCheckout);
      }
    });
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

  Future<QuickSaleCashSession?> _pickCashSession(
      QuickSaleCheckoutOptions options) async {
    if (options.cashSessions.length == 1) return options.cashSessions.single;
    return showDialog<QuickSaleCashSession>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Selecione o caixa'),
        content: SizedBox(
          width: 360,
          child: ListView(
            shrinkWrap: true,
            children: options.cashSessions
                .map((session) => ListTile(
                      title: Text(session.registerName),
                      onTap: () => Navigator.pop(context, session),
                    ))
                .toList(growable: false),
          ),
        ),
      ),
    );
  }

  Future<void> _barcode({bool showNotFound = true}) async {
    if (_catalogLocked) return;
    final barcode = _search.text.trim();
    if (barcode.isEmpty) return;
    final product = await widget.controller.quickSaleBarcode(barcode);
    if (!mounted) return;
    if (product == null) {
      if (!showNotFound) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Produto não encontrado para este código de barras.')));
      return;
    }
    await _addProduct(product);
    if (mounted) _search.clear();
  }

  Future<bool> _scanBarcode(String barcode) async {
    if (_catalogLocked) return false;
    final product = await widget.controller.quickSaleBarcode(barcode);
    if (!mounted) return false;
    if (product == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Produto não encontrado para este código de barras.')));
      return false;
    }
    final added = await _addProduct(product);
    if (added && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('${product.name} adicionado ao carrinho.')));
    }
    return added;
  }

  String _scannerItemCount() {
    final quantity = _cart.fold<double>(
        0,
        (total, item) =>
            total + (double.tryParse(item.quantity.replaceAll(',', '.')) ?? 0));
    return formatQuantity(quantity);
  }

  Future<void> _openBarcodeScanner() async {
    final showCart = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => ProductBarcodeScannerPage(
        onBarcode: _scanBarcode,
        cartListenable: _draft,
        itemCount: _scannerItemCount,
        total: () => formatMoney(_preview?.total ?? '0.00'),
      ),
    ));
    if (showCart == true && mounted && MediaQuery.sizeOf(context).width < 900) {
      await _showMobileCart();
    }
  }

  void _barcodeFromHid(String value) {
    if (RegExp(r'^\d+$').hasMatch(value.trim())) _barcode();
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
    return formatQuantity(number);
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

  Future<bool> _addProduct(QuickSaleProduct product,
      {String quantity = '1'}) async {
    if (_catalogLocked) return false;
    widget.controller.logPosAction('cart_add');
    if (!product.canSell) {
      _showCatalogStockUnavailable();
      return false;
    }
    final item = QuickSaleCartItem(
      clientItemId: createIdempotencyKey(),
      product: product,
      quantity: quantity,
    );
    if (_requiresConfiguration(product)) {
      return _editProduct(product, initial: item);
    }
    final effectiveCart =
        _replayCartMutations(_lastValidatedCart, _pendingCartMutations);
    final existing = effectiveCart
        .where((entry) =>
            entry.product.id == product.id &&
            entry.modifiers.isEmpty &&
            entry.notes.isEmpty &&
            entry.discount.isZero)
        .firstOrNull;
    if (existing == null) {
      _applyCartMutation(_CartMutation.add(item));
      return true;
    }
    final currentQuantity =
        double.tryParse(existing.quantity.replaceAll(',', '.')) ?? 0;
    final addedQuantity = double.tryParse(quantity.replaceAll(',', '.')) ?? 0;
    final mergedQuantity = currentQuantity + addedQuantity;
    _applyCartMutation(_CartMutation.replace(
      existing.clientItemId,
      existing.copyWith(quantity: formatQuantityForApi(mergedQuantity)),
    ));
    return true;
  }

  Future<void> _addProductBatch(QuickSaleProduct product) async {
    if (_catalogLocked) return;
    if (!product.canSell) {
      _showCatalogStockUnavailable();
      return;
    }
    final quantity = await showDialog<String>(
      context: context,
      builder: (_) => BatchQuantityDialog(product: product),
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

  Future<bool> _editProduct(
    QuickSaleProduct product, {
    int? index,
    QuickSaleCartItem? initial,
    bool checkBatchAvailability = false,
  }) async {
    if (_catalogLocked) return false;
    widget.controller.logPosAction('cart_edit');
    final current = initial ?? (index == null ? null : _cart[index]);
    final item = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) => SharedSaleItemEditorDialog(
        product: product,
        initial: current,
      ),
    );
    if (!mounted || item == null) return false;
    _applyCartMutation(index == null
        ? _CartMutation.add(item)
        : _CartMutation.replace(current!.clientItemId, item));
    return true;
  }

  Future<void> _editCartItem(int index) async {
    if (_catalogLocked) return;
    final result = await showDialog<_CartItemEditResult>(
      context: context,
      builder: (_) => _EditCartItemDialog(item: _cart[index]),
    );
    if (result == null || !mounted) return;
    if (result.delete) {
      _applyCartMutation(_CartMutation.remove(_cart[index].clientItemId));
    } else {
      _applyCartMutation(
          _CartMutation.replace(_cart[index].clientItemId, result.item!));
    }
  }

  void _applyCartMutation(_CartMutation mutation) {
    _cartShortages.clear();
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
    _cartShortages.clear();
    _catalogLocked = false;
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
          _cartShortages.clear();
        });
      }
    } on PosApiException catch (error) {
      if (!mounted ||
          error.code != 'stock_unavailable' ||
          intent.generation != _previewGeneration ||
          intent.availabilityGeneration != _availabilityGeneration) {
        return;
      }
      final availability = QuickSaleStockAvailability.fromJson(error.details);
      setState(() {
        if (intent.rollbackCart != null) {
          _lastValidatedCart = List<QuickSaleCartItem>.of(intent.rollbackCart!);
          _cart
            ..clear()
            ..addAll(intent.rollbackCart!);
        }
        if (intent.rollbackCart == null) {
          _cartShortages.clear();
          for (final item in _cart) {
            final shortage = availability.shortages.firstWhere(
              (row) => row['product'] == item.product.id,
              orElse: () => const <String, dynamic>{},
            );
            if (shortage.isNotEmpty) {
              _cartShortages[item.clientItemId] = shortage;
            }
          }
        }
        _preview = null;
        _loadingPreview = false;
      });
      if (intent.rollbackCart != null) _draft.changed();
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
    final cashSession = await _pickCashSession(options);
    if (!mounted || cashSession == null) return;
    final checkout = await widget.controller.createQuickSaleCheckout(
      items: _cart.map((item) => item.toJson()).toList(growable: false),
      cashSessionId: cashSession.id,
      discount: _discount.toJson(),
      serviceFeeWaived: _serviceFeeWaived,
      customer: _draft.customer,
      discountAuthorization: _draft.discountAuthorization,
      itemDiscountAuthorization: _draft.itemDiscountAuthorization,
      serviceFeeAuthorization: _draft.serviceFeeAuthorization,
    );
    if (!mounted || checkout == null) return;
    await _openPayment(checkout, options);
  }

  Future<bool> _clearCart() async {
    if (_catalogLocked) return false;
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
    if (confirmed != true || !mounted) return false;
    final discarded = await widget.controller.discardQuickSaleCheckout();
    if (!mounted || !discarded) return false;
    setState(_resetSaleDraftState);
    return true;
  }

  Future<void> _showMobileCart() async {
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => _CartPage(
        draft: _draft,
        canClear: !_catalogLocked,
        onClear: _clearCart,
        panel: () => _CartPanel(
          cart: _cart,
          shortages: _cartShortages,
          preview: _preview,
          loadingPreview: _loadingPreview,
          cashReady: _checkoutReady,
          editable: !_catalogLocked,
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
                ? MobileCartBar(
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
                  final catalog = ProductCatalogPanel(
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
                    onBarcode: _openBarcodeScanner,
                    onSearchSubmitted: _barcodeFromHid,
                    onProduct: _addProduct,
                    onProductLongPress: _addProductBatch,
                    selectedQuantities: _selectedQuantities,
                    editable: !_catalogLocked,
                  );
                  if (constraints.maxWidth < 900) return catalog;
                  return Row(children: [
                    Expanded(flex: 3, child: catalog),
                    SizedBox(
                      width: 420,
                      child: _CartPanel(
                        cart: _cart,
                        shortages: _cartShortages,
                        preview: _preview,
                        loadingPreview: _loadingPreview,
                        cashReady: _checkoutReady,
                        editable: !_catalogLocked,
                        onEdit: _editCartItem,
                        onCheckout: _checkout,
                        onClear: _clearCart,
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
    required this.canClear,
    required this.onClear,
  });
  final QuickSaleDraft draft;
  final Widget Function() panel;
  final bool canClear;
  final Future<bool> Function() onClear;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Carrinho'),
          actions: [
            if (canClear && draft.cart.isNotEmpty)
              PopupMenuButton<String>(
                onSelected: (action) async {
                  if (action == 'clear' && await onClear() && context.mounted) {
                    Navigator.of(context).pop();
                  }
                },
                itemBuilder: (_) => const [
                  PopupMenuItem(
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

class QuickSaleCompletedPage extends StatelessWidget {
  const QuickSaleCompletedPage({required this.result, super.key});

  final QuickSaleResult result;

  @override
  Widget build(BuildContext context) => PopScope(
        onPopInvokedWithResult: (_, __) {},
        child: Scaffold(
          appBar: AppBar(title: const Text('Venda concluída')),
          body: SafeArea(
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 440),
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Icon(Icons.check_circle_rounded,
                          size: 72, color: Color(0xff16803c)),
                      const SizedBox(height: 20),
                      Text('VENDA CONCLUÍDA',
                          textAlign: TextAlign.center,
                          style: Theme.of(context)
                              .textTheme
                              .headlineSmall
                              ?.copyWith(fontWeight: FontWeight.w900)),
                      const SizedBox(height: 12),
                      Text('Venda #${result.saleNumber}',
                          textAlign: TextAlign.center,
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 6),
                      Text(formatMoney(result.total),
                          textAlign: TextAlign.center,
                          style: Theme.of(context)
                              .textTheme
                              .displaySmall
                              ?.copyWith(fontWeight: FontWeight.w900)),
                      if (result.productionJobCount > 0) ...[
                        const SizedBox(height: 16),
                        const Text('Pedido enviado para produção.',
                            textAlign: TextAlign.center),
                      ],
                      if (result.ticketNumbers.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        Text('Tickets: ${result.ticketNumbers.join(', ')}',
                            textAlign: TextAlign.center),
                      ],
                      const SizedBox(height: 28),
                      FilledButton(
                        onPressed: () => Navigator.of(context).pop(),
                        child: const Padding(
                          padding: EdgeInsets.symmetric(vertical: 12),
                          child: Text('NOVA VENDA'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
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

class MobileCartBar extends StatelessWidget {
  const MobileCartBar({
    required this.itemCount,
    required this.preview,
    required this.updating,
    required this.onTap,
    this.actionLabel = 'VER CARRINHO',
    this.showTotal = true,
    super.key,
  });

  final int itemCount;
  final QuickSalePreview? preview;
  final bool updating;
  final VoidCallback onTap;
  final String actionLabel;
  final bool showTotal;

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
                if (showTotal)
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
                Text(
                  actionLabel,
                  style: TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w900),
                ),
              ]),
            ),
          ),
        ),
      );
}

class ProductCatalogPanel extends StatelessWidget {
  const ProductCatalogPanel({
    required this.search,
    required this.loading,
    required this.products,
    required this.categories,
    required this.categoryId,
    required this.favoritesOnly,
    required this.onCategory,
    required this.onFavorites,
    required this.onBarcode,
    required this.onSearchSubmitted,
    required this.onProduct,
    required this.onProductLongPress,
    this.editable = true,
    this.selectedQuantities = const {},
    super.key,
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
  final ValueChanged<String> onSearchSubmitted;
  final ValueChanged<QuickSaleProduct> onProduct;
  final ValueChanged<QuickSaleProduct> onProductLongPress;
  final bool editable;
  final Map<int, double> selectedQuantities;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.all(16),
        child: Column(children: [
          Row(children: [
            Expanded(
                child: TextField(
              controller: search,
              onSubmitted: editable ? onSearchSubmitted : null,
              decoration: const InputDecoration(
                labelText: 'Produto, código ou código de barras',
                prefixIcon: Icon(Icons.search_rounded),
              ),
            )),
            IconButton(
                onPressed: editable ? onBarcode : null,
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
                            itemBuilder: (context, index) => ProductCard(
                              product: products[index],
                              selectedQuantity:
                                  selectedQuantities[products[index].id] ?? 0,
                              onTap: () => onProduct(products[index]),
                              onLongPress: () =>
                                  onProductLongPress(products[index]),
                              editable: editable,
                            ),
                          );
                        })),
        ]),
      );
}

class ProductCard extends StatefulWidget {
  const ProductCard({
    required this.product,
    required this.onTap,
    required this.onLongPress,
    this.editable = true,
    this.selectedQuantity = 0,
    super.key,
  });
  final QuickSaleProduct product;
  final VoidCallback onTap;
  final VoidCallback onLongPress;
  final bool editable;
  final double selectedQuantity;

  @override
  State<ProductCard> createState() => _ProductCardState();
}

class _ProductCardState extends State<ProductCard>
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
    if (!widget.editable) return;
    _feedback.forward(from: 0);
    widget.onTap();
  }

  @override
  Widget build(BuildContext context) => ScaleTransition(
        scale: _scale,
        child: InkWell(
          borderRadius: BorderRadius.circular(18),
          onTap: widget.editable ? _add : null,
          onLongPress: widget.editable ? widget.onLongPress : null,
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
                  if (widget.selectedQuantity > 0)
                    Positioned(
                      top: 4,
                      right: 4,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: const Color(0xff3454d1),
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 7, vertical: 3),
                          child: Text(
                            _selectedQuantityText(widget.selectedQuantity),
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 11,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                      ),
                    ),
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

String _selectedQuantityText(double quantity) => formatQuantity(quantity);

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
    required this.shortages,
    required this.preview,
    required this.loadingPreview,
    required this.cashReady,
    required this.editable,
    required this.onEdit,
    required this.onCheckout,
    this.onClear,
  });
  final List<QuickSaleCartItem> cart;
  final Map<String, Map<String, dynamic>> shortages;
  final QuickSalePreview? preview;
  final bool loadingPreview;
  final bool cashReady;
  final bool editable;
  final ValueChanged<int> onEdit;
  final VoidCallback onCheckout;
  final Future<bool> Function()? onClear;

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
        modifiers.add(
            '${formatQuantity(selected['quantity'] ?? '1')}x ${option.name}');
      }
    }
    return [
      if (modifiers.isNotEmpty) modifiers.join(' • '),
      if (item.notes.isNotEmpty) 'Obs: ${item.notes}',
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
                  if (onClear != null && editable && cart.isNotEmpty)
                    Align(
                      alignment: Alignment.centerRight,
                      child: TextButton.icon(
                        onPressed: () => onClear!(),
                        icon: const Icon(Icons.delete_outline),
                        label: const Text('APAGAR CARRINHO'),
                      ),
                    ),
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
                                final shortage = shortages[item.clientItemId];
                                final officialLine =
                                    preview?.itemFor(item.clientItemId);
                                return SharedCartItemTile(
                                  name: item.product.name,
                                  quantity: item.quantity,
                                  amount: officialLine == null
                                      ? _provisionalLineTotal(item)
                                      : officialLine.lineTotal,
                                  details: details,
                                  warning: shortage == null
                                      ? null
                                      : 'Estoque disponível: ${formatQuantity(shortage['available_quantity'])} | No carrinho: ${formatQuantity(item.quantity)}',
                                  onTap: editable && !item.product.recoveryOnly
                                      ? () => onEdit(index)
                                      : null,
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
                    SharedTotalsPanel(lines: [
                      SharedTotalsLine(
                          label: 'Total oficial',
                          value: preview!.total,
                          strong: true),
                    ]),
                  ],
                  const SizedBox(height: 12),
                  if (!editable)
                    const Padding(
                      padding: EdgeInsets.only(bottom: 8),
                      child: Text(
                        'Itens bloqueados após o primeiro pagamento.',
                        textAlign: TextAlign.center,
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

class BatchQuantityDialog extends StatefulWidget {
  const BatchQuantityDialog({
    this.product,
    this.productName,
    super.key,
  }) : assert(product != null || productName != null);

  final QuickSaleProduct? product;
  final String? productName;

  String get name => product?.name ?? productName!;
  String get unit => product?.unit ?? 'un';

  @override
  State<BatchQuantityDialog> createState() => _BatchQuantityDialogState();
}

class _BatchQuantityDialogState extends State<BatchQuantityDialog> {
  final _quantity = TextEditingController(text: '1');

  double get _parsed =>
      double.tryParse(_quantity.text.trim().replaceAll(',', '.')) ?? 0;
  bool get _valid =>
      _parsed > 0 &&
      (widget.unit.toLowerCase() != 'un' ||
          _parsed == _parsed.roundToDouble()) &&
      _hasAtMostThreeDecimals(_quantity.text);

  bool _hasAtMostThreeDecimals(String value) {
    final separator = RegExp(r'[,.]').firstMatch(value);
    return separator == null || value.length - separator.end <= 3;
  }

  void _adjust(int delta) {
    final current = _parsed == 0 ? 1 : _parsed;
    final next = current + delta;
    if (next > 0) {
      setState(() => _quantity.text = formatQuantityForApi(next.toDouble()));
    }
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
              child: Text(widget.name,
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
                        ? widget.unit.toLowerCase() == 'un' &&
                                _parsed != _parsed.roundToDouble()
                            ? 'Produtos por unidade exigem quantidade inteira.'
                            : 'Informe uma quantidade válida.'
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
                : () =>
                    Navigator.of(context).pop(formatQuantityForApi(_parsed)),
            child: Text('ADICIONAR ${formatQuantity(_quantity.text)}'),
          ),
        ],
      );
}

class _ItemNotesDialog extends StatefulWidget {
  const _ItemNotesDialog({required this.initial});

  final String initial;

  @override
  State<_ItemNotesDialog> createState() => _ItemNotesDialogState();
}

class _ItemNotesDialogState extends State<_ItemNotesDialog> {
  late final _notes = TextEditingController(text: widget.initial);

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Observação do item'),
        content: TextField(
          controller: _notes,
          maxLines: 3,
          maxLength: 1000,
          autofocus: true,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('CANCELAR'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(_notes.text.trim()),
            child: const Text('SALVAR'),
          ),
        ],
      );
}

class _CartItemEditResult {
  const _CartItemEditResult.item(this.item) : delete = false;
  const _CartItemEditResult.delete()
      : item = null,
        delete = true;
  final QuickSaleCartItem? item;
  final bool delete;
}

class _EditCartItemDialog extends StatefulWidget {
  const _EditCartItemDialog({required this.item});
  final QuickSaleCartItem item;

  @override
  State<_EditCartItemDialog> createState() => _EditCartItemDialogState();
}

class _EditCartItemDialogState extends State<_EditCartItemDialog> {
  late QuickSaleCartItem _item = widget.item;

  Future<void> _editModifiers() async {
    final updated = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) =>
          SharedSaleItemEditorDialog(product: _item.product, initial: _item),
    );
    if (updated != null && mounted) setState(() => _item = updated);
  }

  Future<void> _editNotes() async {
    final value = await showDialog<String>(
      context: context,
      builder: (_) => _ItemNotesDialog(initial: _item.notes),
    );
    if (value != null && mounted) {
      setState(() => _item = _item.copyWith(notes: value));
    }
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
                final value =
                    (double.tryParse(_item.quantity.replaceAll(',', '.')) ??
                            1) -
                        1;
                if (value > 0) {
                  setState(() => _item =
                      _item.copyWith(quantity: formatQuantityForApi(value)));
                }
              },
              icon: const Icon(Icons.remove_circle_outline),
            ),
            Text(formatQuantity(_item.quantity),
                style:
                    const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
            IconButton(
              onPressed: () => setState(() {
                final value =
                    (double.tryParse(_item.quantity.replaceAll(',', '.')) ??
                            1) +
                        1;
                _item = _item.copyWith(quantity: formatQuantityForApi(value));
              }),
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
            onPressed: () =>
                Navigator.of(context).pop(_CartItemEditResult.item(_item)),
            child: const Text('SALVAR'),
          ),
        ],
      );
}
