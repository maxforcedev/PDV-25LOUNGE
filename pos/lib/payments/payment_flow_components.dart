import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../cash/cash_models.dart' show createIdempotencyKey, formatMoney;
import '../sales/sale_models.dart';
import 'payment_contract.dart';
import 'shared_payment_widgets.dart';

class PaymentPageLayout extends StatelessWidget {
  const PaymentPageLayout({
    required this.summary,
    required this.methodGrid,
    required this.history,
    required this.summaryPanel,
    this.pendingAction,
    super.key,
  });

  final PaymentSummaryData summary;
  final Widget methodGrid;
  final Widget history;
  final Widget summaryPanel;
  final Widget? pendingAction;

  @override
  Widget build(BuildContext context) {
    final content = Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        PaymentBalanceCard(summary: summary),
        const SizedBox(height: 10),
        const Text('FORMAS DE PAGAMENTO',
            style: TextStyle(fontWeight: FontWeight.w900)),
        const SizedBox(height: 8),
        methodGrid,
        if (pendingAction != null) ...[
          const SizedBox(height: 8),
          pendingAction!,
        ],
        const SizedBox(height: 10),
        const Text('PAGAMENTOS REALIZADOS',
            style: TextStyle(fontWeight: FontWeight.w900)),
        const SizedBox(height: 4),
        Expanded(child: history),
      ]),
    );
    return SafeArea(
      child: LayoutBuilder(builder: (context, constraints) {
        return constraints.maxWidth >= 960
            ? Row(children: [
                Expanded(child: content),
                SizedBox(width: 350, child: summaryPanel),
              ])
            : Column(children: [
                Expanded(child: content),
                summaryPanel,
              ]);
      }),
    );
  }
}

class PaymentHeaderActions extends StatelessWidget {
  const PaymentHeaderActions({
    required this.customerLabel,
    required this.canEditCustomer,
    required this.canSplit,
    required this.onCustomer,
    required this.onSplit,
    required this.menu,
    super.key,
  });

  final String customerLabel;
  final bool canEditCustomer;
  final bool canSplit;
  final VoidCallback onCustomer;
  final VoidCallback onSplit;
  final Widget menu;

  @override
  Widget build(BuildContext context) {
    final compact = MediaQuery.sizeOf(context).width < 620;
    Widget action(String label, String tooltip, IconData icon, bool enabled,
            VoidCallback callback) =>
        compact
            ? IconButton(
                tooltip: tooltip,
                onPressed: enabled ? callback : null,
                icon: Icon(icon),
              )
            : TextButton.icon(
                onPressed: enabled ? callback : null,
                icon: Icon(icon, size: 18),
                label: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 76),
                  child: Text(label, overflow: TextOverflow.ellipsis),
                ),
              );
    return Row(mainAxisSize: MainAxisSize.min, children: [
      action(customerLabel, 'Cliente: $customerLabel', Icons.person_outline,
          canEditCustomer, onCustomer),
      action(
          'DIVIDIR', 'Dividir pagamento', Icons.call_split, canSplit, onSplit),
      menu,
    ]);
  }
}

class PaymentMethodGrid extends StatelessWidget {
  const PaymentMethodGrid({
    required this.methods,
    required this.enabled,
    required this.onSelect,
    super.key,
  });

  final List<QuickSalePaymentMethod> methods;
  final bool enabled;
  final Future<void> Function(List<QuickSalePaymentMethod> methods) onSelect;

  @override
  Widget build(BuildContext context) {
    final groups = <PaymentMethodGroup, List<QuickSalePaymentMethod>>{};
    for (final method in methods) {
      groups.putIfAbsent(paymentMethodGroup(method), () => []).add(method);
    }
    const order = [
      PaymentMethodGroup.cash,
      PaymentMethodGroup.debit,
      PaymentMethodGroup.pix,
      PaymentMethodGroup.credit,
      PaymentMethodGroup.other,
    ];
    final entries = order
        .where(groups.containsKey)
        .map((group) => MapEntry(group, groups[group]!))
        .toList(growable: false);
    const extent = 56.0;
    const spacing = 8.0;
    final rows = (entries.length / 2).ceil().clamp(1, 3);
    return SizedBox(
      height: rows * extent + (rows - 1) * spacing,
      child: GridView.builder(
        physics: const NeverScrollableScrollPhysics(),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          mainAxisExtent: extent,
          mainAxisSpacing: spacing,
          crossAxisSpacing: spacing,
        ),
        itemCount: entries.length,
        itemBuilder: (_, index) {
          final entry = entries[index];
          return PaymentMethodButton(
            label: switch (entry.key) {
              PaymentMethodGroup.cash => 'Dinheiro',
              PaymentMethodGroup.debit => 'Débito',
              PaymentMethodGroup.pix => 'PIX',
              PaymentMethodGroup.credit => 'Crédito',
              PaymentMethodGroup.other => 'Outros',
            },
            icon: paymentMethodIcon(entry.value.first),
            onTap: enabled ? () => onSelect(entry.value) : null,
          );
        },
      ),
    );
  }
}

class PaymentSplitSelector extends StatelessWidget {
  const PaymentSplitSelector({
    required this.canPayByItems,
    required this.enabled,
    required this.onEqualSplit,
    required this.onItems,
    super.key,
  });

  final bool canPayByItems;
  final bool enabled;
  final VoidCallback onEqualSplit;
  final VoidCallback onItems;

  @override
  Widget build(BuildContext context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Align(
              alignment: Alignment.centerLeft,
              child: Text('DIVIDIR PAGAMENTO',
                  style: TextStyle(fontWeight: FontWeight.w900)),
            ),
            const SizedBox(height: 8),
            ListTile(
              leading: const Icon(Icons.call_split),
              title: const Text('DIVIDIR IGUAL'),
              subtitle: const Text('Dividir o saldo entre pessoas.'),
              enabled: enabled,
              onTap: enabled ? onEqualSplit : null,
            ),
            if (canPayByItems)
              ListTile(
                leading: const Icon(Icons.format_list_bulleted),
                title: const Text('PAGAR POR ITENS'),
                subtitle: const Text('Escolher quais itens serão pagos.'),
                enabled: enabled,
                onTap: enabled ? onItems : null,
              ),
          ]),
        ),
      );
}

class PaymentMethodPicker extends StatelessWidget {
  const PaymentMethodPicker({
    required this.title,
    required this.methods,
    super.key,
  });

  final String title;
  final List<QuickSalePaymentMethod> methods;

  static Future<QuickSalePaymentMethod?> show(
    BuildContext context, {
    required String title,
    required List<QuickSalePaymentMethod> methods,
  }) =>
      showModalBottomSheet<QuickSalePaymentMethod>(
        context: context,
        isScrollControlled: true,
        builder: (_) => PaymentMethodPicker(title: title, methods: methods),
      );

  @override
  Widget build(BuildContext context) => SafeArea(
        child: ConstrainedBox(
          constraints:
              BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * .7),
          child: ListView(children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(title,
                  style: Theme.of(context)
                      .textTheme
                      .titleLarge
                      ?.copyWith(fontWeight: FontWeight.w900)),
            ),
            for (final method in methods)
              ListTile(
                leading: Icon(paymentMethodIcon(method)),
                title: Text(method.name),
                onTap: () => Navigator.pop(context, method),
              ),
          ]),
        ),
      );
}

class PaymentHistoryList extends StatelessWidget {
  const PaymentHistoryList({
    required this.entries,
    super.key,
  });

  final List<PaymentHistoryEntry> entries;

  @override
  Widget build(BuildContext context) {
    if (entries.isEmpty) {
      return const Center(child: Text('Nenhum pagamento registrado.'));
    }
    return ListView.separated(
      padding: EdgeInsets.zero,
      itemCount: entries.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (_, index) {
        final entry = entries[index];
        return PaymentHistoryItem(
          payment: entry.payment,
          reversed: entry.reversed,
          reversalReason: entry.reversalReason,
          working: entry.working,
          onReverse: entry.onReverse,
        );
      },
    );
  }
}

class PaymentHistoryEntry {
  const PaymentHistoryEntry({
    required this.payment,
    required this.reversed,
    required this.working,
    required this.onReverse,
    this.reversalReason,
  });

  final PaymentDisplayEntry payment;
  final bool reversed;
  final bool working;
  final VoidCallback onReverse;
  final String? reversalReason;
}

enum PaymentAmountContext { value, items, equalSplit, remaining }

class PaymentEntryResult {
  const PaymentEntryResult({
    required this.intentId,
    required this.amount,
    required this.receivedAmount,
    required this.payingRemaining,
  });

  final String intentId;
  final String amount;
  final String? receivedAmount;
  final bool payingRemaining;
}

class PaymentEntryPage extends StatefulWidget {
  const PaymentEntryPage({
    required this.method,
    required this.remaining,
    required this.amountContext,
    this.initialAmount,
    this.amountLocked = false,
    super.key,
  });

  final QuickSalePaymentMethod method;
  final String remaining;
  final String? initialAmount;
  final bool amountLocked;
  final PaymentAmountContext amountContext;

  @override
  State<PaymentEntryPage> createState() => _PaymentEntryPageState();
}

class PaymentEqualSplitPart {
  PaymentEqualSplitPart(this.cents, {this.paid = false});

  final int cents;
  bool paid;

  PaymentEqualSplitPart copy() => PaymentEqualSplitPart(cents, paid: paid);
  String get amount =>
      '${cents ~/ 100}.${(cents % 100).toString().padLeft(2, '0')}';
}

class PaymentEqualSplitSelection {
  const PaymentEqualSplitSelection({
    required this.amount,
    this.parts,
    this.index,
  });

  final String amount;
  final List<PaymentEqualSplitPart>? parts;
  final int? index;
}

class PaymentEqualSplitPage extends StatefulWidget {
  const PaymentEqualSplitPage({
    required this.remaining,
    this.initialParts,
    this.officialPerson,
    this.officialPeopleCount,
    this.officialAmount,
    super.key,
  });

  final String remaining;
  final List<PaymentEqualSplitPart>? initialParts;
  final int? officialPerson;
  final int? officialPeopleCount;
  final String? officialAmount;

  bool get isOfficial => officialPerson != null;

  @override
  State<PaymentEqualSplitPage> createState() => _PaymentEqualSplitPageState();
}

class _PaymentEqualSplitPageState extends State<PaymentEqualSplitPage> {
  late List<PaymentEqualSplitPart> _parts;
  late int _people;

  @override
  void initState() {
    super.initState();
    _parts = widget.initialParts?.map((part) => part.copy()).toList() ??
        _partsFor(_PaymentMoneyEntry.centsFor(widget.remaining), 2);
    _people = _parts.length;
  }

  List<PaymentEqualSplitPart> _partsFor(int cents, int people) {
    final base = cents ~/ people;
    final remainder = cents % people;
    return List.generate(people,
        (index) => PaymentEqualSplitPart(base + (index < remainder ? 1 : 0)));
  }

  @override
  Widget build(BuildContext context) {
    if (widget.isOfficial) {
      final person = widget.officialPerson!;
      final people = widget.officialPeopleCount ?? person;
      final amount = widget.officialAmount ?? '0.00';
      return Scaffold(
        appBar: AppBar(title: const Text('DIVIDIR IGUAL')),
        body: Padding(
          padding: const EdgeInsets.all(24),
          child: _partCard(
            context,
            label: 'PESSOA $person DE $people',
            amount: amount,
            onPay: () => Navigator.pop(
              context,
              PaymentEqualSplitSelection(amount: amount),
            ),
          ),
        ),
      );
    }

    final hasPaidPart = _parts.any((part) => part.paid);
    final total = _parts.fold(0, (sum, part) => sum + part.cents);
    return Scaffold(
      appBar: AppBar(title: const Text('DIVIDIR IGUAL')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(children: [
          Text('DIVIDIR ENTRE: $_people'),
          Slider(
            value: _people.toDouble(),
            min: 2,
            max: 12,
            divisions: 10,
            label: '$_people',
            onChanged: hasPaidPart
                ? null
                : (value) => setState(() {
                      _people = value.round();
                      _parts = _partsFor(total, _people);
                    }),
          ),
          Text('Total: ${formatMoney(_moneyValue(total))}'),
          const SizedBox(height: 12),
          Expanded(
            child: ListView.builder(
              itemCount: _parts.length,
              itemBuilder: (context, index) {
                final part = _parts[index];
                return _partCard(
                  context,
                  label: 'PARTE ${index + 1} DE $_people',
                  amount: part.amount,
                  paid: part.paid,
                  onPay: part.paid || part.cents == 0
                      ? null
                      : () => Navigator.pop(
                            context,
                            PaymentEqualSplitSelection(
                              amount: part.amount,
                              parts: _parts,
                              index: index,
                            ),
                          ),
                );
              },
            ),
          ),
        ]),
      ),
    );
  }

  Widget _partCard(
    BuildContext context, {
    required String label,
    required String amount,
    required VoidCallback? onPay,
    bool paid = false,
  }) =>
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Text(label, style: const TextStyle(fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            Text(formatMoney(amount),
                style: Theme.of(context)
                    .textTheme
                    .headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w900)),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: onPay,
              child: Text(paid ? 'PARTE PAGA' : 'PAGAR ESTA PARTE'),
            ),
          ]),
        ),
      );

  String _moneyValue(int cents) =>
      '${cents ~/ 100}.${(cents % 100).toString().padLeft(2, '0')}';
}

class _PaymentEntryPageState extends State<PaymentEntryPage> {
  late final String _intentId = createIdempotencyKey();
  late final _PaymentMoneyEntry _amount =
      _PaymentMoneyEntry(widget.initialAmount ?? '0.00');
  late final _PaymentMoneyEntry _received = _PaymentMoneyEntry('0.00');
  bool _receiving = false;
  bool _payingRemaining = false;

  bool get _editingAmount => !widget.amountLocked || _receiving;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(widget.method.name)),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('FALTA ${formatMoney(widget.remaining)}',
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 14),
                  Text(
                    _receiving
                        ? 'VALOR RECEBIDO'
                        : switch (widget.amountContext) {
                            PaymentAmountContext.items =>
                              'VALOR OFICIAL DOS ITENS',
                            PaymentAmountContext.equalSplit => 'VALOR DA PARTE',
                            PaymentAmountContext.remaining => 'VALOR APLICADO',
                            PaymentAmountContext.value => 'VALOR APLICADO',
                          },
                    textAlign: TextAlign.center,
                  ),
                  Text(formatMoney((_receiving ? _received : _amount).value),
                      textAlign: TextAlign.center,
                      style: Theme.of(context)
                          .textTheme
                          .displaySmall
                          ?.copyWith(fontWeight: FontWeight.w900)),
                  if (widget.method.isCash) ...[
                    SwitchListTile(
                      title: const Text('Informar valor recebido'),
                      value: _receiving,
                      onChanged: (value) => setState(() => _receiving = value),
                    ),
                    if (_receiving)
                      Text('Troco: ${formatMoney(_received.subtract(_amount))}',
                          textAlign: TextAlign.center),
                  ],
                  const SizedBox(height: 10),
                  Wrap(alignment: WrapAlignment.center, spacing: 8, children: [
                    for (final value in ['5.00', '10.00', '20.00', '50.00'])
                      OutlinedButton(
                        onPressed: !_editingAmount
                            ? null
                            : () => setState(() {
                                  (_receiving ? _received : _amount).set(value);
                                  _payingRemaining = false;
                                }),
                        child: Text('R\$ ${value.split('.').first}'),
                      ),
                    OutlinedButton(
                      onPressed: widget.amountLocked
                          ? null
                          : () => setState(() {
                                _amount.set(widget.remaining);
                                _payingRemaining = true;
                              }),
                      child: const Text('PAGAR SALDO'),
                    ),
                  ]),
                  const Spacer(),
                  if (_editingAmount) _keypad(),
                  const SizedBox(height: 14),
                  FilledButton(
                    onPressed: _valid
                        ? () => Navigator.pop(
                              context,
                              PaymentEntryResult(
                                intentId: _intentId,
                                amount: _amount.value,
                                receivedAmount: widget.method.isCash
                                    ? (_receiving
                                        ? _received.value
                                        : _amount.value)
                                    : null,
                                payingRemaining: _payingRemaining,
                              ),
                            )
                        : null,
                    child: const Text('CONFIRMAR PAGAMENTO MANUAL'),
                  ),
                ]),
          ),
        ),
      );

  bool get _valid =>
      _amount.cents > 0 &&
      _amount.cents <= _PaymentMoneyEntry.centsFor(widget.remaining) &&
      (!widget.method.isCash ||
          !_receiving ||
          _received.cents >= _amount.cents);

  Widget _keypad() => GridView.count(
        crossAxisCount: 3,
        shrinkWrap: true,
        childAspectRatio: 1.6,
        children: [
          for (final digit in [
            '1',
            '2',
            '3',
            '4',
            '5',
            '6',
            '7',
            '8',
            '9',
            '00',
            '0'
          ])
            OutlinedButton(
              onPressed: () => setState(() {
                (_receiving ? _received : _amount).append(digit);
                _payingRemaining = false;
              }),
              child: Text(digit, style: const TextStyle(fontSize: 22)),
            ),
          OutlinedButton(
            onPressed: () =>
                setState(() => (_receiving ? _received : _amount).backspace()),
            child: const Icon(Icons.backspace_outlined),
          ),
        ],
      );
}

class PaymentAllocationItem {
  const PaymentAllocationItem({
    required this.id,
    required this.name,
    required this.quantity,
    required this.availableQuantity,
    required this.unit,
  });

  final int id;
  final String name;
  final String quantity;
  final String availableQuantity;
  final String unit;
}

class PaymentAllocationPreview {
  const PaymentAllocationPreview({
    required this.total,
    required this.availableQuantities,
  });

  final String total;
  final Map<int, String> availableQuantities;
}

class PaymentAllocationSelection {
  const PaymentAllocationSelection(this.allocations, this.total);
  final List<Map<String, dynamic>> allocations;
  final String total;
}

class PaymentItemAllocationPage extends StatefulWidget {
  const PaymentItemAllocationPage({
    required this.items,
    required this.remaining,
    required this.preview,
    super.key,
  });

  final List<PaymentAllocationItem> items;
  final String remaining;
  final Future<PaymentAllocationPreview?> Function(
      List<Map<String, dynamic>> allocations) preview;

  @override
  State<PaymentItemAllocationPage> createState() =>
      _PaymentItemAllocationPageState();
}

class _PaymentItemAllocationPageState extends State<PaymentItemAllocationPage> {
  final Map<int, int> _quantities = {};
  final Map<int, TextEditingController> _inputs = {};
  final Map<int, String> _errors = {};
  PaymentAllocationPreview? _preview;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    for (final item in widget.items) {
      _inputs[item.id] = TextEditingController(text: '0');
    }
  }

  @override
  void dispose() {
    for (final controller in _inputs.values) {
      controller.dispose();
    }
    super.dispose();
  }

  List<Map<String, dynamic>> get _allocations => _quantities.entries
      .where((entry) => entry.value > 0)
      .map((entry) => {
            'item': entry.key,
            'allocated_quantity': _quantityValue(entry.value),
          })
      .toList(growable: false);

  bool get _exceedsRemaining =>
      _preview != null &&
      _PaymentMoneyEntry.centsFor(_preview!.total) >
          _PaymentMoneyEntry.centsFor(widget.remaining);

  Future<void> _update() async {
    if (_errors.isNotEmpty) return;
    final allocations = _allocations;
    if (allocations.isEmpty) {
      setState(() => _preview = null);
      return;
    }
    setState(() => _loading = true);
    final preview = await widget.preview(allocations);
    if (mounted)
      setState(() {
        _loading = false;
        _preview = preview;
      });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('PAGAR POR ITENS')),
        body: ListView(padding: const EdgeInsets.all(20), children: [
          for (final item in widget.items) _item(item),
          if (_preview != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('TOTAL OFICIAL ${formatMoney(_preview!.total)}',
                        style: const TextStyle(fontWeight: FontWeight.w900)),
                    if (_exceedsRemaining) ...[
                      const SizedBox(height: 8),
                      Text(
                          'Os itens selecionados somam ${formatMoney(_preview!.total)}, mas faltam ${formatMoney(widget.remaining)}.'),
                    ],
                  ]),
            ),
          FilledButton(
            onPressed: _preview == null ||
                    _loading ||
                    _errors.isNotEmpty ||
                    _exceedsRemaining ||
                    _PaymentMoneyEntry.centsFor(_preview!.total) == 0
                ? null
                : () => Navigator.pop(context,
                    PaymentAllocationSelection(_allocations, _preview!.total)),
            child: const Text('CONTINUAR'),
          ),
        ]),
      );

  Widget _item(PaymentAllocationItem item) {
    final max = _quantityUnits(
        _preview?.availableQuantities[item.id] ?? item.availableQuantity);
    final step = item.unit.toLowerCase() == 'un' ? 1000 : 1;
    final value = _quantities[item.id] ?? 0;
    final input = _inputs[item.id]!;
    final error = _errors[item.id];
    void setValue(int next) {
      setState(() {
        _quantities[item.id] = next;
        _errors.remove(item.id);
        input.text = _quantityValue(next);
      });
      _update();
    }

    return Card(
      child: ListTile(
        title: Text(item.name),
        subtitle:
            Text(error ?? 'Disponível: ${_quantityValue(max)} ${item.unit}'),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          IconButton(
              onPressed:
                  _loading || value == 0 ? null : () => setValue(value - step),
              icon: const Icon(Icons.remove)),
          SizedBox(
            width: 72,
            child: TextField(
              controller: input,
              enabled: !_loading,
              textAlign: TextAlign.center,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [
                TextInputFormatter.withFunction((oldValue, newValue) =>
                    RegExp(r'^\d*(?:[\.,]\d{0,3})?$').hasMatch(newValue.text)
                        ? newValue
                        : oldValue)
              ],
              onChanged: (text) {
                final next = _quantityUnits(text);
                final valid =
                    RegExp(r'^\d*(?:[\.,]\d{0,3})?$').hasMatch(text) &&
                        (item.unit.toLowerCase() != 'un' || next % 1000 == 0) &&
                        next <= max;
                setState(() {
                  _preview = null;
                  if (valid) {
                    _quantities[item.id] = next;
                    _errors.remove(item.id);
                  } else {
                    _errors[item.id] =
                        'Informe até ${_quantityValue(max)} ${item.unit}.';
                  }
                });
              },
              onEditingComplete: _update,
            ),
          ),
          IconButton(
              onPressed: _loading || value + step > max
                  ? null
                  : () => setValue(value + step),
              icon: const Icon(Icons.add)),
        ]),
      ),
    );
  }
}

class _PaymentMoneyEntry {
  _PaymentMoneyEntry(String value) : cents = centsFor(value);
  int cents;
  static int centsFor(String value) {
    final bits = value.replaceAll(',', '.').split('.');
    return (int.tryParse(bits.first) ?? 0) * 100 +
        int.parse((bits.length > 1 ? '${bits[1]}00' : '00').substring(0, 2));
  }

  String get value =>
      '${cents ~/ 100}.${(cents % 100).toString().padLeft(2, '0')}';
  void set(String value) => cents = centsFor(value);
  void append(String digits) => cents = int.parse('$cents$digits');
  void backspace() => cents ~/= 10;
  String subtract(_PaymentMoneyEntry other) => cents >= other.cents
      ? '${(cents - other.cents) ~/ 100}.${((cents - other.cents) % 100).toString().padLeft(2, '0')}'
      : '0.00';
}

IconData paymentMethodIcon(QuickSalePaymentMethod method) =>
    switch (paymentMethodGroup(method)) {
      PaymentMethodGroup.cash => Icons.payments_outlined,
      PaymentMethodGroup.debit => Icons.credit_card,
      PaymentMethodGroup.pix => Icons.qr_code_2,
      PaymentMethodGroup.credit => Icons.credit_card,
      PaymentMethodGroup.other => Icons.account_balance_wallet_outlined,
    };

int _quantityUnits(String value) {
  final bits = value.replaceAll(',', '.').split('.');
  return (int.tryParse(bits.first) ?? 0) * 1000 +
      (int.tryParse('${bits.length > 1 ? bits[1] : ''}000'.substring(0, 3)) ??
          0);
}

String _quantityValue(int thousandths) {
  final whole = thousandths ~/ 1000;
  final fraction = (thousandths % 1000)
      .toString()
      .padLeft(3, '0')
      .replaceFirst(RegExp(r'0+$'), '');
  return fraction.isEmpty ? '$whole' : '$whole.$fraction';
}
