import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../sales/sale_models.dart';
import '../sales/shared_authorization_dialog.dart';
import '../sales/shared_customer_dialog.dart';
import '../sales/shared_discount_dialog.dart';
import '../sales/shared_pos_widgets.dart';

/// Reusable persistent-checkout UI. Hosts provide a checkout snapshot and POS API controller.
class SharedPaymentPage extends StatefulWidget {
  const SharedPaymentPage({
    required this.controller,
    required this.options,
    required this.checkout,
    required this.onCompleted,
    super.key,
  });

  final AppController controller;
  final QuickSaleCheckout checkout;
  final QuickSaleCheckoutOptions options;
  final Future<void> Function(QuickSaleResult result) onCompleted;

  @override
  State<SharedPaymentPage> createState() => _SharedPaymentPageState();
}

class _SharedPaymentPageState extends State<SharedPaymentPage> {
  late QuickSaleCheckout _checkout = widget.checkout;
  bool _working = false;

  List<QuickSalePaymentMethod> get _methods => widget.options.paymentMethods;
  List<QuickSalePaymentMethod> get _direct => _methods
      .where((method) => method.visualGroup != 'card')
      .toList(growable: false);
  List<QuickSalePaymentMethod> get _cards => _methods
      .where((method) => method.visualGroup == 'card')
      .toList(growable: false);
  bool get _canDiscount => widget.controller.bootstrapSnapshot?.permissions
          .contains('sales.apply_discount') ??
      false;
  bool get _canWaiveFee => widget.controller.bootstrapSnapshot?.permissions
          .contains('sales.waive_service_fee') ??
      false;
  bool get _canAddCustomers => widget.controller.bootstrapSnapshot?.permissions
          .contains('customers.add') ??
      false;

  Future<void> _updateFinancials({
    QuickSaleCustomer? customer,
    bool clearCustomer = false,
    QuickSaleDiscountIntent? discount,
    bool? serviceFeeWaived,
    QuickSaleAuthorization? discountAuthorization,
    QuickSaleAuthorization? serviceFeeAuthorization,
  }) async {
    if (!_checkout.canEditFinancials || _working) return;
    setState(() => _working = true);
    final updated = await widget.controller.updateQuickSaleCheckout(
      checkoutId: _checkout.id,
      items: _checkout.items.map((item) => item.input).toList(growable: false),
      cashSessionId: _checkout.cashSessionId,
      customerId: clearCustomer ? null : (customer ?? _checkout.customer)?.id,
      discount: (discount ?? _checkout.discountIntent).toJson(),
      serviceFeeWaived: serviceFeeWaived ?? _checkout.serviceFeeWaived,
      discountAuthorization: discountAuthorization,
      serviceFeeAuthorization: serviceFeeAuthorization,
    );
    if (mounted) setState(() => _working = false);
    if (updated != null && mounted) setState(() => _checkout = updated);
  }

  Future<QuickSaleAuthorization?> _requestAuthorization(String type) async {
    final authorizers = switch (type) {
      'service_fee' => await widget.controller.quickSaleServiceFeeAuthorizers(),
      _ => await widget.controller.quickSaleDiscountAuthorizers(),
    };
    if (!mounted || authorizers == null) return null;
    if (authorizers.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Nenhum autorizador elegível está disponível nesta filial.'),
      ));
      return null;
    }
    return showDialog<QuickSaleAuthorization>(
      context: context,
      builder: (_) => SharedAuthorizationDialog(
        authorizers: authorizers,
        onAuthorize: (authorization) =>
            widget.controller.validateQuickSaleDiscountAuthorization(
          type: type,
          authorization: authorization,
        ),
      ),
    );
  }

  Future<void> _editFinancials(_FinancialEdit action) async {
    if (!_checkout.canEditFinancials || _working) return;
    switch (action) {
      case _FinancialEdit.customer:
        final customer = await showDialog<QuickSaleCustomer>(
          context: context,
          builder: (_) => SharedCustomerPickerDialog(
            controller: widget.controller,
            canCreate: _canAddCustomers,
          ),
        );
        if (customer != null && mounted) await _updateFinancials(customer: customer);
        return;
      case _FinancialEdit.removeCustomer:
        await _updateFinancials(clearCustomer: true);
        return;
      case _FinancialEdit.discount:
        final maximumAmount = [
          double.tryParse(_checkout.preview.subtotal.replaceAll(',', '.')) ?? 0,
          -(double.tryParse(_checkout.preview.promotionDiscountTotal.replaceAll(',', '.')) ?? 0),
          -(double.tryParse(_checkout.preview.itemDiscountTotal.replaceAll(',', '.')) ?? 0),
        ].reduce((total, value) => total + value);
        final discount = await showDialog<QuickSaleDiscountIntent>(
          context: context,
          builder: (_) => SharedDiscountDialog(
            initial: _checkout.discountIntent,
            maximumAmount: maximumAmount < 0 ? 0 : maximumAmount,
            prefillInitialValue: true,
          ),
        );
        if (discount == null || !mounted) return;
        final authorization = _canDiscount
            ? null
            : await _requestAuthorization('sale');
        if (!_canDiscount && authorization == null) return;
        await _updateFinancials(
          discount: discount,
          discountAuthorization: authorization,
        );
        return;
      case _FinancialEdit.removeDiscount:
        await _updateFinancials(discount: const QuickSaleDiscountIntent());
        return;
      case _FinancialEdit.serviceFee:
        final waiving = !_checkout.serviceFeeWaived;
        final authorization = waiving && !_canWaiveFee
            ? await _requestAuthorization('service_fee')
            : null;
        if (waiving && !_canWaiveFee && authorization == null) return;
        await _updateFinancials(
          serviceFeeWaived: waiving,
          serviceFeeAuthorization: authorization,
        );
        return;
    }
  }

  Future<void> _choose(QuickSalePaymentMethod method, {List<Map<String, dynamic>> allocations = const [], String? initialAmount}) async {
    final payment = await Navigator.of(context).push<_PaymentIntent>(
      MaterialPageRoute(
        builder: (_) => _PaymentEntryPage(
          method: method,
          remaining: _checkout.remainingAmount,
          controller: widget.controller,
          checkout: _checkout,
          allocations: allocations,
          initialAmount: initialAmount,
        ),
      ),
    );
    if (payment == null || !mounted || !_checkout.canRecordPayment) return;
    setState(() => _working = true);
    final updated = await widget.controller.recordQuickSalePayment(
      checkoutId: _checkout.id,
      paymentMethodId: method.id,
      mode: payment.allocations.isEmpty ? 'value' : 'items',
      amount: payment.amount,
      receivedAmount: payment.receivedAmount,
      allocations: payment.allocations,
    );
    if (mounted) setState(() => _working = false);
    if (updated != null && mounted) setState(() => _checkout = updated);
  }

  Future<void> _selectItems() async {
    final allocations = await Navigator.of(context).push<List<Map<String, dynamic>>>(
      MaterialPageRoute(builder: (_) => _ItemAllocationPage(checkout: _checkout, controller: widget.controller)),
    );
    if (allocations == null || !mounted) return;
    final method = await _pickMethod('Forma para os itens');
    if (method != null && mounted) await _choose(method, allocations: allocations);
  }

  Future<QuickSalePaymentMethod?> _pickMethod(String title, {List<QuickSalePaymentMethod>? methods}) =>
      showModalBottomSheet<QuickSalePaymentMethod>(
        context: context,
        builder: (context) => SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Text(title, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w900)),
              const SizedBox(height: 12),
              for (final method in methods ?? _methods)
                ListTile(
                  leading: Icon(_icon(method)),
                  title: Text(method.name),
                  onTap: () => Navigator.pop(context, method),
                ),
            ]),
          ),
        ),
      );

  Future<void> _reverse(QuickSaleCheckoutPayment payment) async {
    setState(() => _working = true);
    final updated = await widget.controller.reverseQuickSalePayment(
        checkoutId: _checkout.id, paymentId: payment.id);
    if (mounted) setState(() => _working = false);
    if (updated != null && mounted) setState(() => _checkout = updated);
  }

  Future<void> _finish() async {
    setState(() => _working = true);
    final result = await widget.controller.finalizeQuickSaleCheckout(_checkout.id);
    if (mounted) setState(() => _working = false);
    if (result != null && mounted) await widget.onCompleted(result);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Pagamento'),
          actions: [
            if (_checkout.canEditFinancials)
              PopupMenuButton<_FinancialEdit>(
                enabled: !_working,
                tooltip: 'Editar financeiro',
                icon: const Icon(Icons.more_vert),
                onSelected: _editFinancials,
                itemBuilder: (_) => [
                  const PopupMenuItem(
                    value: _FinancialEdit.customer,
                    child: Text('ALTERAR CLIENTE'),
                  ),
                  if (_checkout.customer != null)
                    const PopupMenuItem(
                      value: _FinancialEdit.removeCustomer,
                      child: Text('REMOVER CLIENTE'),
                    ),
                  const PopupMenuItem(
                    value: _FinancialEdit.discount,
                    child: Text('ALTERAR DESCONTO'),
                  ),
                  if (!_checkout.discountIntent.isZero)
                    const PopupMenuItem(
                      value: _FinancialEdit.removeDiscount,
                      child: Text('REMOVER DESCONTO'),
                    ),
                  PopupMenuItem(
                    value: _FinancialEdit.serviceFee,
                    child: Text(_checkout.serviceFeeWaived
                        ? 'RESTAURAR TAXA DE SERVIÇO'
                        : 'RETIRAR TAXA DE SERVIÇO'),
                  ),
                ],
              ),
          ],
        ),
        body: SafeArea(
          child: LayoutBuilder(builder: (context, constraints) {
            final content = _content(context);
            return constraints.maxWidth >= 960
                ? Row(children: [Expanded(child: content), SizedBox(width: 350, child: _summary(context))])
                : Column(children: [Expanded(child: content), _summary(context)]);
          }),
        ),
      );

  Widget _content(BuildContext context) => ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text('FALTA', style: Theme.of(context).textTheme.labelLarge),
          Text(formatMoney(_checkout.remainingAmount), style: Theme.of(context).textTheme.displaySmall?.copyWith(fontWeight: FontWeight.w900, color: const Color(0xff3454d1))),
          if (!_checkout.canEditFinancials) ...[
            const SizedBox(height: 8),
            const Text('Edição financeira bloqueada após o primeiro pagamento.'),
          ],
          const SizedBox(height: 20),
          const Text('FORMAS DE PAGAMENTO', style: TextStyle(fontWeight: FontWeight.w900)),
          const SizedBox(height: 10),
          _methodGrid(),
          const SizedBox(height: 12),
          Wrap(spacing: 8, children: [
            OutlinedButton.icon(onPressed: _working || !_checkout.canRecordPayment ? null : _selectItems, icon: const Icon(Icons.format_list_bulleted), label: const Text('PAGAR POR ITENS')),
            OutlinedButton.icon(onPressed: _working || !_checkout.canRecordPayment ? null : () async {
              final part = await Navigator.of(context).push<String>(MaterialPageRoute(builder: (_) => _EqualSplitPage(remaining: _checkout.remainingAmount)));
              if (part == null || !mounted) return;
              final method = await _pickMethod('Forma para esta parte');
              if (method != null && mounted) await _choose(method, initialAmount: part);
            }, icon: const Icon(Icons.call_split), label: const Text('DIVIDIR IGUAL')),
          ]),
          const SizedBox(height: 24),
          const Text('PAGAMENTOS REALIZADOS', style: TextStyle(fontWeight: FontWeight.w900)),
          const SizedBox(height: 8),
          if (_checkout.payments.isEmpty) const Text('Nenhum pagamento registrado.'),
          for (final payment in _checkout.payments) _history(payment),
        ],
      );

  Widget _methodGrid() {
    final top = <_MethodTile>[];
    for (final method in _direct) {
      if (top.length == 3 && (_cards.isNotEmpty || _direct.length > 3)) break;
      top.add(_MethodTile(method.name, _icon(method), () => _choose(method)));
    }
    if (_cards.isNotEmpty && top.length < 4) {
      top.add(_MethodTile('Cartão', Icons.credit_card, () async {
        final method = await _pickMethod('Modalidades de cartão', methods: _cards);
        if (method != null && mounted) await _choose(method);
      }));
    }
    final shown = top.where((tile) => tile.label != 'Cartão').length + _cards.length;
    if (_methods.length > shown && top.length < 4) {
      final topNames = top.map((tile) => tile.label).toSet();
      top.add(_MethodTile('Outros', Icons.more_horiz, () async {
        final method = await _pickMethod('Outras formas', methods: _methods.where((m) => !topNames.contains(m.name) && m.visualGroup != 'card').toList());
        if (method != null && mounted) await _choose(method);
      }));
    }
    return GridView.count(
      crossAxisCount: MediaQuery.sizeOf(context).width < 520 ? 2 : 4,
      shrinkWrap: true, physics: const NeverScrollableScrollPhysics(),
      childAspectRatio: 1.7,
        children: top.map((tile) => Card(child: InkWell(onTap: _working || !_checkout.canRecordPayment ? null : tile.onTap, child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [Icon(tile.icon), const SizedBox(height: 5), Text(tile.label, style: const TextStyle(fontWeight: FontWeight.w800))])))).toList(),
    );
  }

  Widget _history(QuickSaleCheckoutPayment payment) => Card(
        child: ListTile(
          leading: Icon(payment.isReversal ? Icons.undo : Icons.check_circle_outline, color: payment.isReversal ? Colors.red : const Color(0xff16803c)),
          title: Text(payment.methodName),
          subtitle: Text(payment.isReversal ? 'Estornado' : payment.receivedAmount == null ? 'Confirmado' : 'Recebido ${formatMoney(payment.receivedAmount!)}  Troco ${formatMoney(payment.changeAmount ?? '0.00')}'),
          trailing: payment.isReversal || !_checkout.canReversePayment ? Text(formatMoney(payment.amount)) : Row(mainAxisSize: MainAxisSize.min, children: [Text(formatMoney(payment.amount)), IconButton(onPressed: _working ? null : () => _reverse(payment), tooltip: 'Estornar', icon: const Icon(Icons.undo))]),
        ),
      );

  Widget _summary(BuildContext context) => Material(
        color: Colors.white,
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const Text('RESUMO', style: TextStyle(fontWeight: FontWeight.w900)),
            const SizedBox(height: 12),
            SharedTotalsPanel(lines: [
              SharedTotalsLine(label: 'Subtotal', value: _checkout.preview.subtotal),
              SharedTotalsLine(label: 'Descontos', value: _checkout.preview.discount),
              SharedTotalsLine(label: 'Taxa de serviço', value: _checkout.preview.serviceFeeAmount),
              SharedTotalsLine(label: 'Total', value: _checkout.preview.total, strong: true),
              SharedTotalsLine(label: 'Pago', value: _checkout.paidAmount),
              SharedTotalsLine(label: 'Falta', value: _checkout.remainingAmount, strong: true),
            ]),
            const SizedBox(height: 16),
            if (_checkout.canFinalize) FilledButton(onPressed: _working ? null : _finish, child: _working ? const CircularProgressIndicator() : const Text('FINALIZAR VENDA')),
          ]),
        ),
      );

  IconData _icon(QuickSalePaymentMethod method) => switch (method.kind) { 'cash' => Icons.payments_outlined, 'pix' => Icons.qr_code_2, 'card' || 'credit' || 'debit' || 'benefit' => Icons.credit_card, _ => Icons.account_balance_wallet_outlined };
}

class _MethodTile { const _MethodTile(this.label, this.icon, this.onTap); final String label; final IconData icon; final VoidCallback onTap; }
enum _FinancialEdit { customer, removeCustomer, discount, removeDiscount, serviceFee }
class _PaymentIntent { const _PaymentIntent(this.amount, this.receivedAmount, this.allocations); final String amount; final String? receivedAmount; final List<Map<String, dynamic>> allocations; }

class _PaymentEntryPage extends StatefulWidget {
  const _PaymentEntryPage({required this.method, required this.remaining, required this.controller, required this.checkout, required this.allocations, this.initialAmount});
  final QuickSalePaymentMethod method; final String remaining; final AppController controller; final QuickSaleCheckout checkout; final List<Map<String, dynamic>> allocations;
  final String? initialAmount;
  @override State<_PaymentEntryPage> createState() => _PaymentEntryPageState();
}
class _PaymentEntryPageState extends State<_PaymentEntryPage> {
  late final _MoneyEntry _amount = _MoneyEntry(widget.initialAmount ?? widget.remaining);
  late final _MoneyEntry _received = _MoneyEntry(widget.remaining);
  bool _receiving = false;
  @override Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: Text(widget.method.name)), body: SafeArea(child: Padding(padding: const EdgeInsets.all(20), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
    Text('FALTA ${formatMoney(widget.remaining)}', style: const TextStyle(fontWeight: FontWeight.w800)), const SizedBox(height: 14),
    Text(_receiving ? 'VALOR RECEBIDO' : 'VALOR APLICADO', textAlign: TextAlign.center),
    Text(formatMoney((_receiving ? _received : _amount).value), textAlign: TextAlign.center, style: Theme.of(context).textTheme.displaySmall?.copyWith(fontWeight: FontWeight.w900)),
    if (widget.method.isCash) ...[SwitchListTile(title: const Text('Informar valor recebido'), value: _receiving, onChanged: (value) => setState(() => _receiving = value)), if (_receiving) Text('Troco: ${formatMoney(_received.subtract(_amount))}', textAlign: TextAlign.center)],
    const SizedBox(height: 10), Wrap(alignment: WrapAlignment.center, spacing: 8, children: [for (final value in ['5.00', '10.00', '20.00', '50.00']) OutlinedButton(onPressed: () => setState(() => (_receiving ? _received : _amount).set(value)), child: Text('R\$ ${value.split('.').first}')), OutlinedButton(onPressed: () => setState(() => (_receiving ? _received : _amount).set(widget.remaining)), child: const Text('PAGAR SALDO'))]),
    const Spacer(), _keypad(), const SizedBox(height: 14),
    FilledButton(onPressed: _valid ? () => Navigator.pop(context, _PaymentIntent(_amount.value, widget.method.isCash ? _received.value : null, widget.allocations)) : null, child: Text(widget.method.isCash ? 'CONFIRMAR PAGAMENTO MANUAL' : 'CONFIRMAR PAGAMENTO MANUAL')),
  ]))));
  bool get _valid => _amount.cents > 0 && _amount.cents <= _MoneyEntry.centsFor(widget.remaining) && (!widget.method.isCash || _received.cents >= _amount.cents);
  Widget _keypad() => GridView.count(crossAxisCount: 3, shrinkWrap: true, childAspectRatio: 1.6, children: [
    for (final digit in ['1','2','3','4','5','6','7','8','9','00','0'])
      OutlinedButton(onPressed: () => setState(() => (_receiving ? _received : _amount).append(digit)), child: Text(digit, style: const TextStyle(fontSize: 22))),
    OutlinedButton(onPressed: () => setState(() => (_receiving ? _received : _amount).backspace()), child: const Icon(Icons.backspace_outlined)),
  ]);
}

class _MoneyEntry { _MoneyEntry(String value) : cents = centsFor(value); int cents; static int centsFor(String value) { final bits = value.replaceAll(',', '.').split('.'); return (int.tryParse(bits.first) ?? 0) * 100 + int.parse((bits.length > 1 ? '${bits[1]}00' : '00').substring(0, 2)); } String get value => '${(cents ~/ 100)}.${(cents % 100).toString().padLeft(2, '0')}'; void set(String value) => cents = centsFor(value); void append(String digits) => cents = int.parse('$cents$digits'); void backspace() => cents ~/= 10; String subtract(_MoneyEntry other) => cents >= other.cents ? '${((cents - other.cents) ~/ 100)}.${((cents - other.cents) % 100).toString().padLeft(2, '0')}' : '0.00'; }

class _ItemAllocationPage extends StatefulWidget { const _ItemAllocationPage({required this.checkout, required this.controller}); final QuickSaleCheckout checkout; final AppController controller; @override State<_ItemAllocationPage> createState() => _ItemAllocationPageState(); }
class _ItemAllocationPageState extends State<_ItemAllocationPage> { final Map<int, int> _quantities = {}; QuickSalePaymentPreview? _preview; bool _loading = false;
  Future<void> _update() async { final rows = _quantities.entries.where((entry) => entry.value > 0).map((entry) => {'item': entry.key, 'allocated_quantity': entry.value.toString()}).toList(); if (rows.isEmpty) { setState(() => _preview = null); return; } setState(() => _loading = true); final preview = await widget.controller.previewQuickSalePayment(checkoutId: widget.checkout.id, allocations: rows); if (mounted) setState(() { _loading = false; _preview = preview; }); }
  @override Widget build(BuildContext context) => Scaffold(appBar: AppBar(title: const Text('Pagar por itens')), body: ListView(padding: const EdgeInsets.all(20), children: [for (final item in widget.checkout.items) _item(item), if (_preview != null) Padding(padding: const EdgeInsets.all(12), child: Text('TOTAL OFICIAL ${formatMoney(_preview!.total)}', style: const TextStyle(fontWeight: FontWeight.w900))), FilledButton(onPressed: _preview == null || _loading ? null : () => Navigator.pop(context, _quantities.entries.where((entry) => entry.value > 0).map((entry) => {'item': entry.key, 'allocated_quantity': entry.value.toString()}).toList()), child: const Text('CONTINUAR'))]));
  Widget _item(QuickSaleCheckoutItem item) { final max = int.tryParse(item.quantity.split('.').first) ?? 0; final value = _quantities[item.id] ?? 0; return Card(child: ListTile(title: Text(item.name), subtitle: Text('Disponível: ${_preview?.availableQuantities[item.id] ?? item.quantity} ${item.unit}'), trailing: Row(mainAxisSize: MainAxisSize.min, children: [IconButton(onPressed: value == 0 ? null : () { setState(() => _quantities[item.id] = value - 1); _update(); }, icon: const Icon(Icons.remove)), Text('$value'), IconButton(onPressed: value >= max ? null : () { setState(() => _quantities[item.id] = value + 1); _update(); }, icon: const Icon(Icons.add))]))); }
}

class _EqualSplitPage extends StatefulWidget { const _EqualSplitPage({required this.remaining}); final String remaining; @override State<_EqualSplitPage> createState() => _EqualSplitPageState(); }
class _EqualSplitPageState extends State<_EqualSplitPage> { int _people = 2; @override Widget build(BuildContext context) { final cents = _MoneyEntry.centsFor(widget.remaining); final part = cents ~/ _people; final remainder = cents % _people; return Scaffold(appBar: AppBar(title: const Text('Dividir igual')), body: Padding(padding: const EdgeInsets.all(24), child: Column(children: [Text('DIVIDIR ENTRE: $_people'), Slider(value: _people.toDouble(), min: 2, max: 12, divisions: 10, label: '$_people', onChanged: (value) => setState(() => _people = value.round())), Text('Parte: ${formatMoney('${part ~/ 100}.${(part % 100).toString().padLeft(2, '0')}')}'), if (remainder > 0) Text('As primeiras $remainder partes recebem R\$ 0,01 adicional.'), const Spacer(), FilledButton(onPressed: () => Navigator.pop(context, '${part ~/ 100}.${(part % 100).toString().padLeft(2, '0')}'), child: const Text('USAR ESTA PARTE'))]))); } }
