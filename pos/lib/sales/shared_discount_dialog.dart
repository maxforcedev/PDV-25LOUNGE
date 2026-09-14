import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import 'sale_models.dart';

class SharedDiscountDialog extends StatefulWidget {
  const SharedDiscountDialog({
    required this.initial,
    this.maximumAmount,
    this.prefillInitialValue = false,
    super.key,
  });

  final QuickSaleDiscountIntent initial;
  final double? maximumAmount;
  final bool prefillInitialValue;

  @override
  State<SharedDiscountDialog> createState() => _SharedDiscountDialogState();
}

class _SharedDiscountDialogState extends State<SharedDiscountDialog> {
  late String _type = widget.initial.type;
  late final _value = TextEditingController(
      text: widget.prefillInitialValue ? widget.initial.value : '');

  @override
  void dispose() {
    _value.dispose();
    super.dispose();
  }

  bool get _valid {
    final value = double.tryParse(_value.text.trim().replaceAll(',', '.'));
    return value != null &&
        value > 0 &&
        (_type == 'amount'
            ? value <= (widget.maximumAmount ?? 999999999999.99)
            : value <= 100);
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
              )),
              const SizedBox(width: 8),
              Expanded(
                  child: _DiscountTypeButton(
                label: '%',
                selected: _type == 'percentage',
                onTap: () => _setType('percentage'),
              )),
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
                    ? _type == 'amount' && widget.maximumAmount != null
                        ? 'O desconto máximo disponível para esta venda é ${formatMoney(widget.maximumAmount!.toStringAsFixed(2))}.'
                        : 'Informe um valor válido.'
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
                : () => Navigator.of(context).pop(
                      QuickSaleDiscountIntent(
                          type: _type,
                          value: _value.text.trim().replaceAll(',', '.')),
                    ),
            child: const Text('APLICAR'),
          ),
        ],
      );
}

class _DiscountTypeButton extends StatelessWidget {
  const _DiscountTypeButton(
      {required this.label, required this.selected, required this.onTap});

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
                      : const Color(0xffcbd5e1)),
            ),
            child: Text(label,
                style: TextStyle(
                  color: selected ? Colors.white : const Color(0xff1e293b),
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                )),
          ),
        ),
      );
}
