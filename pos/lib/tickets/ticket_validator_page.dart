import 'package:flutter/material.dart';

import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import 'ticket_models.dart';

class TicketValidatorPage extends StatefulWidget {
  const TicketValidatorPage({required this.controller, super.key});
  final AppController controller;
  @override
  State<TicketValidatorPage> createState() => _TicketValidatorPageState();
}

class _TicketValidatorPageState extends State<TicketValidatorPage> {
  final _number = TextEditingController();
  TicketValidationTicket? _ticket;
  String _quantity = '1.000';
  bool _loading = false;
  bool _validating = false;
  String? _validationKey;

  @override
  void dispose() {
    _number.dispose();
    super.dispose();
  }

  Future<void> _lookup() async {
    final value = _number.text.trim();
    if (value.isEmpty || _loading) return;
    setState(() => _loading = true);
    final result = await widget.controller.lookupTicket(
      ticketNumber: int.tryParse(value),
      validationCode: int.tryParse(value) == null ? value : null,
    );
    if (mounted) {
      setState(() {
        _loading = false;
        _ticket = result?.ticket;
        _quantity = '1.000';
        _validationKey = null;
      });
    }
  }

  Future<void> _validate() async {
    final ticket = _ticket;
    if (ticket == null || _validating) return;
    setState(() => _validating = true);
    final result = await widget.controller.validateTicket(
      ticketNumber: ticket.number,
      quantity: _quantity,
      idempotencyKey: _validationKey ??= createIdempotencyKey(),
      inputMethod: 'manual',
    );
    if (!mounted) {
      return;
    }
    setState(() {
      _validating = false;
      _ticket = result?.ticket ?? ticket;
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('VALIDAR TICKET')),
        body: SafeArea(child: LayoutBuilder(builder: (context, constraints) {
          final content =
              _ticket == null ? _lookupPanel() : _ticketPanel(_ticket!);
          return Center(
              child: ConstrainedBox(
            constraints: BoxConstraints(
                maxWidth: constraints.maxWidth >= 900 ? 760 : 560),
            child: SingleChildScrollView(
                padding: const EdgeInsets.all(20), child: content),
          ));
        })),
      );

  Widget _lookupPanel() =>
      Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Icon(Icons.qr_code_scanner_rounded,
            size: 80, color: Color(0xff3454d1)),
        const SizedBox(height: 16),
        const Text('Digite ou escaneie o código do ticket',
            textAlign: TextAlign.center,
            style: TextStyle(fontWeight: FontWeight.w800)),
        const SizedBox(height: 16),
        TextField(
            controller: _number,
            autofocus: true,
            onSubmitted: (_) => _lookup(),
            decoration:
                const InputDecoration(labelText: 'Número ou código do ticket')),
        const SizedBox(height: 12),
        FilledButton(
            onPressed: _loading ? null : _lookup,
            child: Text(_loading ? 'CONSULTANDO...' : 'CONSULTAR TICKET')),
      ]);

  Widget _ticketPanel(TicketValidationTicket ticket) {
    final blocked = !ticket.redeemable;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text('TICKET #${ticket.number}',
          style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
      Text(ticket.status.toUpperCase(),
          style: TextStyle(
              color: ticket.status == 'cancelled'
                  ? Colors.red
                  : const Color(0xff3454d1),
              fontWeight: FontWeight.w800)),
      const SizedBox(height: 16),
      Card(
          child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(ticket.productName,
                        style: const TextStyle(
                            fontSize: 20, fontWeight: FontWeight.w900)),
                    Text('Emitidas: ${ticket.totalQuantity} ${ticket.unit}'),
                    Text('Já retiradas: ${ticket.redeemedQuantity}'),
                    Text('Restantes: ${ticket.redeemableQuantity}',
                        style: const TextStyle(fontWeight: FontWeight.w800)),
                    if (ticket.modifiers.isNotEmpty)
                      Text(
                          'Modificadores: ${ticket.modifiers.map((item) => item['name'] ?? item['option_name'] ?? '').where((name) => name.isNotEmpty).join(', ')}'),
                    if (ticket.notes.isNotEmpty)
                      Text('Observação: ${ticket.notes}'),
                  ]))),
      if (!blocked) ...[
        const SizedBox(height: 12),
        TextField(
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            onChanged: (value) => _quantity = value.replaceAll(',', '.'),
            decoration:
                const InputDecoration(labelText: 'Quantidade a entregar')),
        const SizedBox(height: 12),
        FilledButton(
            onPressed: _validating ? null : _validate,
            child: Text(_validating ? 'REGISTRANDO...' : 'VALIDAR E ENTREGAR')),
      ],
      TextButton(
          onPressed: () => setState(() {
                _ticket = null;
                _number.clear();
                _validationKey = null;
              }),
          child: const Text('VALIDAR OUTRO TICKET')),
    ]);
  }
}
