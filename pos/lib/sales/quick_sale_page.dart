import 'dart:async';

import 'package:flutter/material.dart';

import '../cash/cash_page.dart';
import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../sync/sync_center_page.dart';
import '../sync/sync_status_button.dart';
import 'sale_models.dart';

class _PreviewIntent {
  const _PreviewIntent({
    required this.generation,
    required this.items,
    required this.discount,
    required this.serviceFeeWaived,
  });

  final int generation;
  final List<Map<String, dynamic>> items;
  final String discount;
  final bool serviceFeeWaived;
}

class QuickSalePage extends StatefulWidget {
  const QuickSalePage({required this.controller, super.key});

  final AppController controller;

  @override
  State<QuickSalePage> createState() => _QuickSalePageState();
}

class _QuickSalePageState extends State<QuickSalePage> {
  final _search = TextEditingController();
  final List<QuickSaleCartItem> _cart = [];
  List<QuickSaleProduct> _allCatalog = const [];
  List<QuickSaleProduct> _catalog = const [];
  List<QuickSaleCategory> _categories = const [];
  QuickSaleCheckoutOptions? _checkoutOptions;
  QuickSalePreview? _preview;
  bool _loading = true;
  bool _loadingPreview = false;
  bool _favoritesOnly = false;
  bool _serviceFeeWaived = false;
  int? _categoryId;
  String _discount = '0.00';
  int _previewGeneration = 0;
  Timer? _previewDebounce;
  Timer? _searchDebounce;
  bool _previewInFlight = false;
  _PreviewIntent? _pendingPreview;

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
    _previewDebounce?.cancel();
    _searchDebounce?.cancel();
    _search.dispose();
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

  Future<void> _addProduct(QuickSaleProduct product) async {
    widget.controller.logPosAction('cart_add');
    if (_requiresConfiguration(product)) {
      await _editProduct(product);
      return;
    }
    setState(() {
      _cart.add(QuickSaleCartItem(
        clientItemId: createIdempotencyKey(),
        product: product,
        quantity: '1',
      ));
    });
    _schedulePreview();
  }

  Future<void> _editProduct(
    QuickSaleProduct product, {
    int? index,
    QuickSaleCartItem? initial,
  }) async {
    widget.controller.logPosAction('cart_edit');
    final current = initial ?? (index == null ? null : _cart[index]);
    final item = await showDialog<QuickSaleCartItem>(
      context: context,
      builder: (_) => _ItemEditorDialog(
        product: product,
        initial: current,
        allowItemDiscount: _canItemDiscount,
      ),
    );
    if (!mounted || item == null) return;
    setState(() {
      if (index == null) {
        _cart.add(item);
      } else {
        _cart[index] = item;
      }
    });
    _schedulePreview();
  }

  void _changeQuantity(int index, int delta) {
    widget.controller.logPosAction('cart_quantity');
    final current = int.tryParse(_cart[index].quantity) ?? 1;
    final next = current + delta;
    if (next > 0 &&
        _cart[index]
            .product
            .modifierGroups
            .any((group) => group.requiredQuantity != null)) {
      unawaited(_editProduct(
        _cart[index].product,
        index: index,
        initial: _cart[index].copyWith(quantity: '$next'),
      ));
      return;
    }
    setState(() {
      if (next <= 0) {
        _cart.removeAt(index);
      } else {
        _cart[index] = _cart[index].copyWith(quantity: '$next');
      }
    });
    _schedulePreview();
  }

  void _removeItem(int index) {
    widget.controller.logPosAction('cart_remove');
    setState(() => _cart.removeAt(index));
    _schedulePreview();
  }

  void _schedulePreview() {
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
        items: items,
        discount: discount,
        serviceFeeWaived: serviceFeeWaived,
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
    final preview = await widget.controller.previewQuickSale(
      items: intent.items,
      discount: intent.discount,
      serviceFeeWaived: intent.serviceFeeWaived,
    );
    _previewInFlight = false;
    if (!mounted) return;
    if (intent.generation == _previewGeneration) {
      setState(() {
        _preview = preview;
        _loadingPreview = false;
      });
    }
    final pending = _pendingPreview;
    _pendingPreview = null;
    if (pending != null) _enqueuePreview(pending);
  }

  Future<void> _checkout() async {
    if (!_checkoutReady || _cart.isEmpty || _preview == null) return;
    widget.controller.logPosAction('checkout_open');
    final options = _checkoutOptions!;
    final request = await showModalBottomSheet<_CheckoutRequest>(
      context: context,
      isScrollControlled: true,
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: .9,
        builder: (_, scrollController) => _CheckoutDialog(
          options: options,
          preview: _preview!,
          scrollController: scrollController,
        ),
      ),
    );
    if (!mounted || request == null) return;
    final result = await widget.controller.finalizeQuickSale(
      items: _cart.map((item) => item.toJson()).toList(growable: false),
      cashSessionId: request.cashSessionId,
      payments: request.payments,
      discount: _discount,
      serviceFeeWaived: _serviceFeeWaived,
    );
    if (!mounted || result == null) return;
    setState(() {
      _cart.clear();
      _preview = null;
      _discount = '0.00';
      _serviceFeeWaived = false;
    });
    await _loadCheckoutOptions();
  }

  Future<void> _showMobileCart() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: .88,
        builder: (context, scrollController) => _CartPanel(
          scrollController: scrollController,
          cart: _cart,
          preview: _preview,
          loadingPreview: _loadingPreview,
          serviceFeeWaived: _serviceFeeWaived,
          discount: _discount,
          allowDiscount: _canDiscount,
          allowWaiveFee: _canWaiveFee,
          cashReady: _checkoutReady,
          onQuantity: _changeQuantity,
          onEdit: (index) => _editProduct(_cart[index].product, index: index),
          onRemove: _removeItem,
          onDiscount: (value) {
            setState(() => _discount = value);
            _schedulePreview();
          },
          onServiceFeeWaived: (value) {
            setState(() => _serviceFeeWaived = value);
            _schedulePreview();
          },
          onCheckout: _checkout,
        ),
      ),
    );
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
                        _applyCatalogFilter();
                      });
                    },
                    onFavorites: () {
                      widget.controller.logPosAction('catalog_favorites');
                      setState(() {
                        _favoritesOnly = !_favoritesOnly;
                        _applyCatalogFilter();
                      });
                    },
                    onBarcode: _barcode,
                    onProduct: _addProduct,
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
                        serviceFeeWaived: _serviceFeeWaived,
                        discount: _discount,
                        allowDiscount: _canDiscount,
                        allowWaiveFee: _canWaiveFee,
                        cashReady: _checkoutReady,
                        onQuantity: _changeQuantity,
                        onEdit: (index) =>
                            _editProduct(_cart[index].product, index: index),
                        onRemove: _removeItem,
                        onDiscount: (value) {
                          setState(() => _discount = value);
                          _schedulePreview();
                        },
                        onServiceFeeWaived: (value) {
                          setState(() => _serviceFeeWaived = value);
                          _schedulePreview();
                        },
                        onCheckout: _checkout,
                      ),
                    ),
                  ]);
                }),
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
                      : GridView.builder(
                          gridDelegate:
                              const SliverGridDelegateWithMaxCrossAxisExtent(
                            maxCrossAxisExtent: 220,
                            mainAxisSpacing: 12,
                            crossAxisSpacing: 12,
                            childAspectRatio: .88,
                          ),
                          itemCount: products.length,
                          itemBuilder: (context, index) => _ProductCard(
                              product: products[index],
                              onTap: () => onProduct(products[index])),
                        )),
        ]),
      );
}

class _ProductCard extends StatefulWidget {
  const _ProductCard({required this.product, required this.onTap});
  final QuickSaleProduct product;
  final VoidCallback onTap;

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
          child: Ink(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: const Color(0xffe2e8f0))),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(child: _ProductImage(url: widget.product.imageUrl)),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(
                    child: Text(widget.product.name,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w700))),
                if (widget.product.favorite)
                  const Icon(Icons.star_rounded,
                      color: Color(0xffffb020), size: 19),
              ]),
              const SizedBox(height: 4),
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
                      color: Color(0xff3454d1), size: 38)
                  : Image.network(url!,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => const Icon(
                          Icons.inventory_2_outlined,
                          color: Color(0xff3454d1),
                          size: 38))),
        ),
      );
}

class _CartPanel extends StatelessWidget {
  const _CartPanel({
    this.scrollController,
    required this.cart,
    required this.preview,
    required this.loadingPreview,
    required this.serviceFeeWaived,
    required this.discount,
    required this.allowDiscount,
    required this.allowWaiveFee,
    required this.cashReady,
    required this.onQuantity,
    required this.onEdit,
    required this.onRemove,
    required this.onDiscount,
    required this.onServiceFeeWaived,
    required this.onCheckout,
  });
  final ScrollController? scrollController;
  final List<QuickSaleCartItem> cart;
  final QuickSalePreview? preview;
  final bool loadingPreview;
  final bool serviceFeeWaived;
  final String discount;
  final bool allowDiscount;
  final bool allowWaiveFee;
  final bool cashReady;
  final void Function(int, int) onQuantity;
  final ValueChanged<int> onEdit;
  final ValueChanged<int> onRemove;
  final ValueChanged<String> onDiscount;
  final ValueChanged<bool> onServiceFeeWaived;
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
      if (item.discount != '0.00') 'Desconto: ${formatMoney(item.discount)}',
    ].join('\n');
  }

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.white,
        child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('Carrinho',
                      style: Theme.of(context)
                          .textTheme
                          .titleLarge
                          ?.copyWith(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 8),
                  Expanded(
                      child: cart.isEmpty
                          ? const Center(
                              child: Text(
                                  'Adicione produtos para iniciar a venda.'))
                          : ListView.separated(
                              controller: scrollController,
                              itemCount: cart.length,
                              separatorBuilder: (_, __) => const Divider(),
                              itemBuilder: (context, index) {
                                final item = cart[index];
                                final details = _itemDetails(item);
                                return InkWell(
                                  onTap: () => onEdit(index),
                                  child: Padding(
                                    padding:
                                        const EdgeInsets.symmetric(vertical: 8),
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
                                          Text(formatMoney(item.product.price),
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
                                        Align(
                                          alignment: Alignment.centerRight,
                                          child: Wrap(
                                            crossAxisAlignment:
                                                WrapCrossAlignment.center,
                                            children: [
                                              IconButton(
                                                  visualDensity:
                                                      VisualDensity.compact,
                                                  onPressed: () =>
                                                      onQuantity(index, -1),
                                                  icon: const Icon(Icons
                                                      .remove_circle_outline)),
                                              Text(item.quantity),
                                              IconButton(
                                                  visualDensity:
                                                      VisualDensity.compact,
                                                  onPressed: () =>
                                                      onQuantity(index, 1),
                                                  icon: const Icon(Icons
                                                      .add_circle_outline)),
                                              IconButton(
                                                  visualDensity:
                                                      VisualDensity.compact,
                                                  onPressed: () =>
                                                      onRemove(index),
                                                  icon: const Icon(
                                                      Icons.delete_outline)),
                                            ],
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                );
                              },
                            )),
                  if (allowDiscount)
                    _MoneyField(
                        label: 'Desconto na venda',
                        value: discount,
                        onSubmitted: onDiscount),
                  if (allowWaiveFee)
                    SwitchListTile.adaptive(
                        contentPadding: EdgeInsets.zero,
                        value: serviceFeeWaived,
                        onChanged: onServiceFeeWaived,
                        title: const Text('Isentar taxa de serviço')),
                  if (loadingPreview) const LinearProgressIndicator(),
                  if (preview != null) ...[
                    const SizedBox(height: 8),
                    _AmountRow(label: 'Subtotal', value: preview!.subtotal),
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

class _MoneyField extends StatefulWidget {
  const _MoneyField(
      {required this.label, required this.value, required this.onSubmitted});
  final String label;
  final String value;
  final ValueChanged<String> onSubmitted;
  @override
  State<_MoneyField> createState() => _MoneyFieldState();
}

class _MoneyFieldState extends State<_MoneyField> {
  late final TextEditingController _controller =
      TextEditingController(text: widget.value);
  @override
  void didUpdateWidget(covariant _MoneyField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.value != widget.value && _controller.text != widget.value) {
      _controller.text = widget.value;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => TextField(
        controller: _controller,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        onSubmitted: widget.onSubmitted,
        decoration:
            InputDecoration(labelText: widget.label, prefixText: 'R\$ '),
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

class _ItemEditorDialog extends StatefulWidget {
  const _ItemEditorDialog(
      {required this.product, this.initial, required this.allowItemDiscount});
  final QuickSaleProduct product;
  final QuickSaleCartItem? initial;
  final bool allowItemDiscount;
  @override
  State<_ItemEditorDialog> createState() => _ItemEditorDialogState();
}

class _ItemEditorDialogState extends State<_ItemEditorDialog> {
  late final TextEditingController _notes =
      TextEditingController(text: widget.initial?.notes ?? '');
  late final TextEditingController _discount =
      TextEditingController(text: widget.initial?.discount ?? '0.00');
  final Map<int, int> _quantities = {};
  String? _validation;

  @override
  void initState() {
    super.initState();
    for (final modifier
        in widget.initial?.modifiers ?? const <Map<String, dynamic>>[]) {
      final option = modifier['option'] as int?;
      if (option != null)
        _quantities[option] = int.tryParse('${modifier['quantity']}') ?? 1;
    }
  }

  @override
  void dispose() {
    _notes.dispose();
    _discount.dispose();
    super.dispose();
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
      notes: _notes.text.trim(),
      discount: widget.allowItemDiscount
          ? _discount.text.trim().isEmpty
              ? '0.00'
              : _discount.text.trim()
          : '0.00',
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
              TextField(
                  controller: _notes,
                  maxLines: 2,
                  maxLength: 1000,
                  decoration:
                      const InputDecoration(labelText: 'Observação do item')),
              if (widget.allowItemDiscount)
                TextField(
                    controller: _discount,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                        labelText: 'Desconto no item', prefixText: 'R\$ ')),
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

class _CheckoutRequest {
  const _CheckoutRequest({required this.cashSessionId, required this.payments});
  final int cashSessionId;
  final List<Map<String, dynamic>> payments;
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

class _CheckoutDialog extends StatefulWidget {
  const _CheckoutDialog({
    required this.options,
    required this.preview,
    required this.scrollController,
  });
  final QuickSaleCheckoutOptions options;
  final QuickSalePreview preview;
  final ScrollController scrollController;
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
    if (!_payments.first.useRemaining)
      _payments.first.amount.text = widget.preview.total;
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

  void _submit() {
    if (!_validPayments) return;
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
    Navigator.of(context)
        .pop(_CheckoutRequest(cashSessionId: _sessionId, payments: payload));
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
                        onPressed: () => Navigator.of(context).pop(),
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
                              onSelected: (_) =>
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
                      controller: widget.scrollController,
                      children: [
                        for (var index = 0; index < _payments.length; index++)
                          _paymentRow(index),
                        OutlinedButton.icon(
                          onPressed: () => setState(() => _payments.add(
                              _PaymentDraft(
                                  widget.options.paymentMethods.first))),
                          icon: const Icon(Icons.add),
                          label: const Text('ADICIONAR PAGAMENTO'),
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
                  FilledButton(
                    onPressed: _validPayments ? _submit : null,
                    child: const Text('CONFIRMAR VENDA'),
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
                      onPressed: () => setState(() {
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
                      label: Text(method.name.toUpperCase()),
                      selected: payment.method.id == method.id,
                      selectedColor: const Color(0xff3454d1),
                      labelStyle: TextStyle(
                          color: payment.method.id == method.id
                              ? Colors.white
                              : const Color(0xff1e293b),
                          fontWeight: FontWeight.w800),
                      onSelected: (_) => _selectPaymentMethod(index, method),
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
                            onChanged: (_) => setState(() {}),
                            keyboardType: const TextInputType.numberWithOptions(
                                decimal: true),
                            decoration: const InputDecoration(
                                labelText: 'Valor', prefixText: 'R\$ '))),
                if (payment.method.code == 'cash')
                  TextButton(
                      onPressed: () => setState(
                          () => payment.useRemaining = !payment.useRemaining),
                      child: Text(payment.useRemaining
                          ? 'INFORMAR VALOR'
                          : 'USAR RESTANTE')),
              ]),
              if (payment.method.code == 'cash')
                TextField(
                    controller: payment.received,
                    onChanged: (_) => setState(() {}),
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                        labelText: 'Valor recebido', prefixText: 'R\$ ')),
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
