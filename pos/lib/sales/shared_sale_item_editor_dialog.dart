import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import 'sale_models.dart';
import 'sale_presentation.dart';

class SharedSaleItemEditorDialog extends StatefulWidget {
  const SharedSaleItemEditorDialog({
    required this.product,
    this.initial,
    this.showQuantityAndNotes = false,
    super.key,
  });

  final QuickSaleProduct product;
  final QuickSaleCartItem? initial;
  final bool showQuantityAndNotes;

  @override
  State<SharedSaleItemEditorDialog> createState() =>
      _SharedSaleItemEditorDialogState();
}

class _SharedSaleItemEditorDialogState
    extends State<SharedSaleItemEditorDialog> {
  final Map<int, int> _quantities = {};
  late final TextEditingController _quantity;
  late final TextEditingController _notes;
  String? _validation;

  @override
  void initState() {
    super.initState();
    _quantity = TextEditingController(
        text: _formatItemQuantity(_number(widget.initial?.quantity)));
    _notes = TextEditingController(text: widget.initial?.notes ?? '');
    for (final modifier
        in widget.initial?.modifiers ?? const <Map<String, dynamic>>[]) {
      final option = widget.showQuantityAndNotes
          ? int.tryParse('${modifier['option'] ?? ''}')
          : modifier['option'] as int?;
      if (option != null) {
        _quantities[option] = int.tryParse('${modifier['quantity']}') ?? 1;
      }
    }
  }

  @override
  void dispose() {
    _quantity.dispose();
    _notes.dispose();
    super.dispose();
  }

  double get _itemQuantity => _number(_quantity.text);

  void _setQuantity(double quantity) {
    if (quantity <= 0) return;
    setState(() {
      _quantity.text = _formatItemQuantity(quantity);
      _validation = null;
    });
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

  String _formatItemQuantity(double value) => value == value.roundToDouble()
      ? '${value.toInt()}'
      : formatQuantityForApi(value);

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
        (widget.showQuantityAndNotes
            ? _itemQuantity
            : _number(widget.initial?.quantity));
    if (group.requiredQuantity != null && totalQuantity != required) {
      final difference = (required - totalQuantity).abs();
      final formatted = widget.showQuantityAndNotes
          ? _formatItemQuantity(difference)
          : _formatQuantity(difference);
      return totalQuantity < required
          ? 'Selecione mais $formatted unidade(s) em ${group.name}.'
          : 'Remova $formatted unidade(s) em ${group.name}.';
    }
    final minimum = _number(group.minTotalQuantity);
    if (minimum > 0 && totalQuantity < minimum) {
      final difference = minimum - totalQuantity;
      final formatted = widget.showQuantityAndNotes
          ? _formatItemQuantity(difference)
          : _formatQuantity(difference);
      return 'Selecione mais $formatted unidade(s) em ${group.name}.';
    }
    final maximum =
        group.maxTotalQuantity == null ? null : _number(group.maxTotalQuantity);
    if (maximum != null && totalQuantity > maximum) {
      final difference = totalQuantity - maximum;
      final formatted = widget.showQuantityAndNotes
          ? _formatItemQuantity(difference)
          : _formatQuantity(difference);
      return 'Remova $formatted unidade(s) em ${group.name}.';
    }
    return null;
  }

  void _save() {
    if (widget.showQuantityAndNotes) {
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
    }
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
      quantity: widget.showQuantityAndNotes
          ? _formatItemQuantity(_itemQuantity)
          : widget.initial?.quantity ?? '1',
      notes: widget.showQuantityAndNotes
          ? _notes.text.trim()
          : widget.initial?.notes ?? '',
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
              if (widget.showQuantityAndNotes)
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
                      decoration:
                          const InputDecoration(labelText: 'Quantidade'),
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
                    padding: EdgeInsets.only(
                        top: widget.showQuantityAndNotes ? 16 : 8),
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
                                  subtitle:
                                      Text(formatMoney(option.additionalPrice)),
                                )
                              : CheckboxListTile(
                                  contentPadding: EdgeInsets.zero,
                                  value: _quantities.containsKey(option.id),
                                  onChanged: (value) =>
                                      _toggle(group, option, value ?? false),
                                  title: Text(option.name),
                                  subtitle:
                                      Text(formatMoney(option.additionalPrice)),
                                ),
                    ),
                    if (group.allowOptionQuantity &&
                        _quantities.containsKey(option.id)) ...[
                      IconButton(
                        onPressed: () => _decrease(option),
                        icon: const Icon(Icons.remove),
                      ),
                      Text('${_quantities[option.id]}'),
                      IconButton(
                        onPressed: () => _increase(group, option),
                        icon: const Icon(Icons.add),
                      ),
                    ],
                  ]),
              ],
              if (widget.showQuantityAndNotes)
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
          FilledButton(
              onPressed: _save,
              child: Text(widget.initial == null ? 'ADICIONAR' : 'SALVAR')),
        ],
      );
}
