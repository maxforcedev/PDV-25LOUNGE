import 'dart:async';

import 'package:flutter/material.dart';

import '../core/app_controller.dart';
import '../cash/cash_models.dart';
import '../sync/sync_center_page.dart';
import '../sync/sync_status_button.dart';
import 'sale_models.dart';

class QuickSalePage extends StatefulWidget {
  const QuickSalePage({required this.controller, super.key});

  final AppController controller;

  @override
  State<QuickSalePage> createState() => _QuickSalePageState();
}

class _QuickSalePageState extends State<QuickSalePage> {
  final _search = TextEditingController();
  final List<QuickSaleCartItem> _cart = [];
  List<QuickSaleProduct> _catalog = const [];
  QuickSalePreview? _preview;
  bool _loading = true;
  bool _loadingPreview = false;
  bool _serviceFeeWaived = false;
  String _discount = '0.00';
  int _previewRequest = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_loadCatalog());
  }

  @override
  void dispose() {
    _previewRequest++;
    _search.dispose();
    super.dispose();
  }

  Future<void> _loadCatalog() async {
    setState(() => _loading = true);
    final products = await widget.controller.quickSaleCatalog(search: _search.text);
    if (!mounted) return;
    setState(() {
      _catalog = products ?? const [];
      _loading = false;
    });
  }

  Future<void> _barcode() async {
    final barcode = _search.text.trim();
    if (barcode.isEmpty) return;
    final product = await widget.controller.quickSaleBarcode(barcode);
    if (product != null && mounted) await _addProduct(product);
  }

  Future<void> _addProduct(QuickSaleProduct product) async {
    var modifiers = const <Map<String, dynamic>>[];
    if (product.modifierGroups.isNotEmpty) {
      final selected = await showDialog<List<Map<String, dynamic>>>(
        context: context,
        builder: (_) => _ModifierDialog(product: product),
      );
      if (!mounted || selected == null) return;
      modifiers = selected;
    }
    setState(() {
      _cart.add(QuickSaleCartItem(
        clientItemId: createIdempotencyKey(),
        product: product,
        quantity: '1',
        modifiers: modifiers,
      ));
    });
    unawaited(_refreshPreview());
  }

  void _changeQuantity(int index, int delta) {
    final current = int.tryParse(_cart[index].quantity) ?? 1;
    final next = current + delta;
    if (next <= 0) {
      setState(() => _cart.removeAt(index));
    } else {
      setState(() => _cart[index] = _cart[index].copyWith(quantity: '$next'));
    }
    unawaited(_refreshPreview());
  }

  Future<void> _refreshPreview() async {
    final request = ++_previewRequest;
    if (_cart.isEmpty) {
      setState(() {
        _preview = null;
        _loadingPreview = false;
      });
      return;
    }
    setState(() => _loadingPreview = true);
    final preview = await widget.controller.previewQuickSale(
      items: _cart.map((item) => item.toJson()).toList(growable: false),
      discount: _discount,
      serviceFeeWaived: _serviceFeeWaived,
    );
    if (!mounted || request != _previewRequest) return;
    setState(() {
      _preview = preview;
      _loadingPreview = false;
    });
  }

  Future<void> _checkout() async {
    if (_cart.isEmpty || _preview == null) return;
    final options = await widget.controller.quickSaleCheckoutOptions();
    if (!mounted || options == null) return;
    final request = await showDialog<_CheckoutRequest>(
      context: context,
      builder: (_) => _CheckoutDialog(options: options, preview: _preview!),
    );
    if (!mounted || request == null) return;
    final result = await widget.controller.finalizeQuickSale(
      items: _cart.map((item) => item.toJson()).toList(growable: false),
      cashSessionId: request.cashSessionId,
      payments: [request.payment],
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
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Venda Rápida'),
          actions: [
            SyncStatusButton(
              status: widget.controller.syncStatus,
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => SyncCenterPage(controller: widget.controller))),
            ),
          ],
        ),
        body: SafeArea(
          child: LayoutBuilder(
            builder: (context, constraints) {
              final cart = _CartPanel(
                cart: _cart,
                preview: _preview,
                loadingPreview: _loadingPreview,
                serviceFeeWaived: _serviceFeeWaived,
                discount: _discount,
                onQuantity: _changeQuantity,
                onDiscount: (value) {
                  setState(() => _discount = value);
                  unawaited(_refreshPreview());
                },
                onServiceFeeWaived: (value) {
                  setState(() => _serviceFeeWaived = value);
                  unawaited(_refreshPreview());
                },
                onCheckout: _checkout,
              );
              final catalog = _CatalogPanel(
                search: _search,
                loading: _loading,
                products: _catalog,
                onSearch: _loadCatalog,
                onBarcode: _barcode,
                onProduct: _addProduct,
              );
              if (constraints.maxWidth >= 900) {
                return Row(children: [
                  Expanded(flex: 3, child: catalog),
                  SizedBox(width: 380, child: cart),
                ]);
              }
              return Column(children: [
                Expanded(child: catalog),
                SizedBox(height: 330, child: cart),
              ]);
            },
          ),
        ),
      );
}

class _CatalogPanel extends StatelessWidget {
  const _CatalogPanel({
    required this.search,
    required this.loading,
    required this.products,
    required this.onSearch,
    required this.onBarcode,
    required this.onProduct,
  });

  final TextEditingController search;
  final bool loading;
  final List<QuickSaleProduct> products;
  final VoidCallback onSearch;
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
                onSubmitted: (_) => onSearch(),
                decoration: const InputDecoration(
                  labelText: 'Buscar produto ou código de barras',
                  prefixIcon: Icon(Icons.search_rounded),
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton(onPressed: onSearch, icon: const Icon(Icons.search_rounded)),
            IconButton(onPressed: onBarcode, icon: const Icon(Icons.qr_code_scanner)),
          ]),
          const SizedBox(height: 16),
          Expanded(
            child: loading
                ? const Center(child: CircularProgressIndicator())
                : products.isEmpty
                    ? const Center(child: Text('Nenhum produto disponível.'))
                    : GridView.builder(
                        gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                          maxCrossAxisExtent: 210,
                          mainAxisSpacing: 12,
                          crossAxisSpacing: 12,
                          childAspectRatio: 1.15,
                        ),
                        itemCount: products.length,
                        itemBuilder: (context, index) {
                          final product = products[index];
                          return InkWell(
                            borderRadius: BorderRadius.circular(18),
                            onTap: () => onProduct(product),
                            child: Ink(
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(18),
                                border: Border.all(color: const Color(0xffe2e8f0)),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  if (product.favorite)
                                    const Icon(Icons.star_rounded, color: Color(0xffffb020)),
                                  const Spacer(),
                                  Text(product.name,
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(fontWeight: FontWeight.w700)),
                                  const SizedBox(height: 6),
                                  Text(formatMoney(product.price),
                                      style: const TextStyle(
                                          color: Color(0xff3454d1), fontWeight: FontWeight.w800)),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
          ),
        ]),
      );
}

class _CartPanel extends StatelessWidget {
  const _CartPanel({
    required this.cart,
    required this.preview,
    required this.loadingPreview,
    required this.serviceFeeWaived,
    required this.discount,
    required this.onQuantity,
    required this.onDiscount,
    required this.onServiceFeeWaived,
    required this.onCheckout,
  });

  final List<QuickSaleCartItem> cart;
  final QuickSalePreview? preview;
  final bool loadingPreview;
  final bool serviceFeeWaived;
  final String discount;
  final void Function(int, int) onQuantity;
  final ValueChanged<String> onDiscount;
  final ValueChanged<bool> onServiceFeeWaived;
  final VoidCallback onCheckout;

  @override
  Widget build(BuildContext context) => Material(
        color: Colors.white,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text('Carrinho', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            Expanded(
              child: cart.isEmpty
                  ? const Center(child: Text('Adicione produtos para iniciar a venda.'))
                  : ListView.separated(
                      itemCount: cart.length,
                      separatorBuilder: (_, __) => const Divider(),
                      itemBuilder: (context, index) {
                        final item = cart[index];
                        return Row(children: [
                          Expanded(child: Text(item.product.name, maxLines: 2, overflow: TextOverflow.ellipsis)),
                          IconButton(onPressed: () => onQuantity(index, -1), icon: const Icon(Icons.remove_circle_outline)),
                          Text(item.quantity),
                          IconButton(onPressed: () => onQuantity(index, 1), icon: const Icon(Icons.add_circle_outline)),
                        ]);
                      },
                    ),
            ),
            TextField(
              controller: TextEditingController(text: discount),
              key: ValueKey(discount),
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              onSubmitted: onDiscount,
              decoration: const InputDecoration(labelText: 'Desconto solicitado', prefixText: 'R\$ '),
            ),
            SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              value: serviceFeeWaived,
              onChanged: onServiceFeeWaived,
              title: const Text('Isentar taxa de serviço'),
            ),
            if (loadingPreview) const LinearProgressIndicator(),
            if (preview != null) ...[
              const SizedBox(height: 8),
              _AmountRow(label: 'Subtotal', value: preview!.subtotal),
              _AmountRow(label: 'Promoções', value: preview!.promotionDiscountTotal, negative: true),
              _AmountRow(label: 'Taxa de serviço', value: preview!.serviceFeeAmount),
              _AmountRow(label: 'Total oficial', value: preview!.total, strong: true),
            ],
            const SizedBox(height: 12),
            FilledButton(
              onPressed: cart.isEmpty || preview == null || loadingPreview ? null : onCheckout,
              child: const Text('FINALIZAR VENDA'),
            ),
          ]),
        ),
      );
}

class _AmountRow extends StatelessWidget {
  const _AmountRow({required this.label, required this.value, this.negative = false, this.strong = false});
  final String label;
  final String value;
  final bool negative;
  final bool strong;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Text(label, style: TextStyle(fontWeight: strong ? FontWeight.w800 : FontWeight.w400)),
          Text('${negative ? '- ' : ''}${formatMoney(value)}', style: TextStyle(fontWeight: strong ? FontWeight.w800 : FontWeight.w500)),
        ]),
      );
}

class _ModifierDialog extends StatefulWidget {
  const _ModifierDialog({required this.product});
  final QuickSaleProduct product;
  @override
  State<_ModifierDialog> createState() => _ModifierDialogState();
}

class _ModifierDialogState extends State<_ModifierDialog> {
  final Set<int> _selected = {};
  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.product.name),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            for (final group in widget.product.modifierGroups) ...[
              Align(alignment: Alignment.centerLeft, child: Text(group.name, style: const TextStyle(fontWeight: FontWeight.w700))),
              for (final option in group.options)
                CheckboxListTile(
                  value: _selected.contains(option.id),
                  onChanged: (value) => setState(() => value == true ? _selected.add(option.id) : _selected.remove(option.id)),
                  title: Text(option.name),
                  subtitle: Text(formatMoney(option.additionalPrice)),
                ),
            ],
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('CANCELAR')),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(
              _selected.map((id) => {'option': id, 'quantity': '1'}).toList(growable: false),
            ),
            child: const Text('ADICIONAR'),
          ),
        ],
      );
}

class _CheckoutRequest {
  const _CheckoutRequest({required this.cashSessionId, required this.payment});
  final int cashSessionId;
  final Map<String, dynamic> payment;
}

class _CheckoutDialog extends StatefulWidget {
  const _CheckoutDialog({required this.options, required this.preview});
  final QuickSaleCheckoutOptions options;
  final QuickSalePreview preview;
  @override
  State<_CheckoutDialog> createState() => _CheckoutDialogState();
}

class _CheckoutDialogState extends State<_CheckoutDialog> {
  late int? _sessionId = widget.options.cashSessions.isEmpty
      ? null
      : widget.options.cashSessions.first.id;
  late QuickSalePaymentMethod? _method = widget.options.paymentMethods.isEmpty
      ? null
      : widget.options.paymentMethods.first;
  final _received = TextEditingController();
  @override
  void dispose() { _received.dispose(); super.dispose(); }
  void _submit() {
    if (_sessionId == null || _method == null) return;
    final payment = <String, dynamic>{'payment_method': _method!.id, 'amount': _method!.code == 'cash' ? 'remaining' : widget.preview.total};
    if (_method!.code == 'cash') payment['received_amount'] = _received.text.trim();
    Navigator.of(context).pop(_CheckoutRequest(cashSessionId: _sessionId!, payment: payment));
  }
  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Finalizar venda'),
        content: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
          DropdownButtonFormField<int>(
            initialValue: _sessionId,
            decoration: const InputDecoration(labelText: 'Sessão de caixa'),
            items: widget.options.cashSessions.map((item) => DropdownMenuItem(value: item.id, child: Text(item.registerName))).toList(growable: false),
            onChanged: (value) => setState(() => _sessionId = value),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<QuickSalePaymentMethod>(
            initialValue: _method,
            decoration: const InputDecoration(labelText: 'Forma de pagamento'),
            items: widget.options.paymentMethods.map((item) => DropdownMenuItem(value: item, child: Text(item.name))).toList(growable: false),
            onChanged: (value) => setState(() => _method = value),
          ),
          if (_method?.code == 'cash') ...[
            const SizedBox(height: 12),
            TextField(controller: _received, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'Valor recebido', prefixText: 'R\$ ')),
          ],
          const SizedBox(height: 16),
          _AmountRow(label: 'Total oficial', value: widget.preview.total, strong: true),
        ])),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('CANCELAR')),
          FilledButton(onPressed: _submit, child: const Text('CONFIRMAR')),
        ],
      );
}
