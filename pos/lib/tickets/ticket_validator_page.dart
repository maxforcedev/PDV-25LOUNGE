import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../cash/cash_models.dart';
import '../core/app_controller.dart';
import '../scanner/scanner_beep.dart';
import 'ticket_models.dart';

class TicketValidatorPage extends StatefulWidget {
  const TicketValidatorPage({required this.controller, super.key});
  final AppController controller;
  @override
  State<TicketValidatorPage> createState() => _TicketValidatorPageState();
}

enum _ValidatorState {
  scanning,
  lookingUp,
  reviewing,
  validating,
  success,
  error
}

class _TicketValidatorPageState extends State<TicketValidatorPage> {
  final _number = TextEditingController();
  final _scanner = MobileScannerController();
  TicketValidationTicket? _ticket;
  String _quantity = '1.000';
  _ValidatorState _state = _ValidatorState.scanning;
  String? _validationKey;
  String _inputMethod = 'manual';
  String? _redeemedNow;
  bool _startingScanner = false;

  @override
  void dispose() {
    _number.dispose();
    _scanner.dispose();
    super.dispose();
  }

  Future<void> _lookup({String inputMethod = 'manual'}) async {
    final value = _number.text.trim();
    if (value.isEmpty ||
        !(_state == _ValidatorState.scanning ||
            _state == _ValidatorState.error)) {
      return;
    }
    setState(() {
      _state = _ValidatorState.lookingUp;
      _inputMethod = inputMethod;
    });
    await _scanner.stop();
    final result = await widget.controller.lookupTicket(
      ticketNumber: int.tryParse(value),
      validationCode: int.tryParse(value) == null ? value : null,
    );
    if (mounted) {
      setState(() {
        _state =
            result == null ? _ValidatorState.error : _ValidatorState.reviewing;
        _ticket = result?.ticket;
        _quantity = '1.000';
        _validationKey = null;
      });
    }
  }

  Future<void> _validate() async {
    final ticket = _ticket;
    if (ticket == null || _state != _ValidatorState.reviewing) return;
    setState(() => _state = _ValidatorState.validating);
    final result = await widget.controller.validateTicket(
      ticketNumber: ticket.number,
      quantity: _quantity,
      idempotencyKey: _validationKey ??= createIdempotencyKey(),
      inputMethod: _inputMethod,
    );
    if (!mounted) {
      return;
    }
    setState(() {
      _state =
          result == null ? _ValidatorState.reviewing : _ValidatorState.success;
      _ticket = result?.ticket ?? ticket;
      _redeemedNow = result?.redeemedNow;
    });
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('VALIDAR TICKET')),
        body: SafeArea(child: LayoutBuilder(builder: (context, constraints) {
          final content = switch (_state) {
            _ValidatorState.scanning ||
            _ValidatorState.lookingUp ||
            _ValidatorState.error =>
              _lookupPanel(),
            _ValidatorState.success => _successPanel(_ticket!),
            _ => _ticketPanel(_ticket!),
          };
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
        ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: SizedBox(
                height: 220,
                child: MobileScanner(
                  controller: _scanner,
                  onDetect: (capture) {
                    if (_state != _ValidatorState.scanning) return;
                    final code = capture.barcodes.firstOrNull?.rawValue;
                    if (code == null || code.isEmpty) return;
                    _number.text = code;
                    ScannerBeep.play();
                    _lookup(inputMethod: 'scan');
                  },
                ))),
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
        if (_state == _ValidatorState.error)
          const Padding(
              padding: EdgeInsets.only(bottom: 12),
              child: Text(
                  'Não foi possível consultar o ticket. Verifique a conexão ou o código e tente novamente.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Color(0xffb42318)))),
        FilledButton(
            onPressed: _state == _ValidatorState.scanning ||
                    _state == _ValidatorState.error
                ? _lookup
                : null,
            child: Text(_state == _ValidatorState.lookingUp
                ? 'CONSULTANDO...'
                : 'CONSULTAR TICKET')),
        if (_state == _ValidatorState.error)
          TextButton(
              onPressed: _reset, child: const Text('VOLTAR PARA A CÂMERA')),
      ]);

  Widget _ticketPanel(TicketValidationTicket ticket) {
    final blocked = !ticket.redeemable;
    final remaining = double.tryParse(ticket.redeemableQuantity) ?? 0;
    return DecoratedBox(
      decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(4),
          boxShadow: const [
            BoxShadow(
                color: Color(0x220f172a), blurRadius: 16, offset: Offset(0, 6))
          ]),
      child: Padding(
          padding: const EdgeInsets.all(24),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const Text('CORE PDV',
                textAlign: TextAlign.center,
                style:
                    TextStyle(fontWeight: FontWeight.w900, letterSpacing: 2)),
            const Text('TICKET DE RETIRADA',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12, letterSpacing: 1.2)),
            const SizedBox(height: 14),
            Text(_ticketNumber(ticket.number),
                textAlign: TextAlign.center,
                style:
                    const TextStyle(fontSize: 34, fontWeight: FontWeight.w900)),
            Text(_statusText(ticket.status),
                textAlign: TextAlign.center,
                style: TextStyle(
                    fontWeight: FontWeight.w900,
                    color: ticket.status == 'cancelled'
                        ? const Color(0xffb42318)
                        : ticket.status == 'used'
                            ? const Color(0xff475569)
                            : const Color(0xff16803c))),
            const _TicketDivider(),
            const SizedBox(height: 10),
            Text(ticket.productName.toUpperCase(),
                style:
                    const TextStyle(fontSize: 21, fontWeight: FontWeight.w900)),
            if (ticket.modifiers.isNotEmpty) ...[
              const SizedBox(height: 18),
              const Text('ADICIONAIS',
                  style: TextStyle(fontWeight: FontWeight.w900)),
              ...ticket.modifiers.map((item) =>
                  Text('• ${item['name'] ?? item['option_name'] ?? ''}'))
            ],
            if (ticket.notes.isNotEmpty) ...[
              const SizedBox(height: 16),
              const Text('OBSERVAÇÃO',
                  style: TextStyle(fontWeight: FontWeight.w900)),
              Text(ticket.notes)
            ],
            const _TicketDivider(),
            _quantityLine('Emitido', ticket.totalQuantity),
            _quantityLine('Já retirado', ticket.redeemedQuantity),
            _quantityLine(
                ticket.status == 'cancelled' ? 'Cancelado' : 'Restante',
                ticket.status == 'cancelled'
                    ? ticket.cancelledUnredeemedQuantity
                    : ticket.redeemableQuantity),
            if (ticket.status == 'used') ...[
              const SizedBox(height: 16),
              const Text('Este ticket já foi totalmente utilizado.',
                  textAlign: TextAlign.center)
            ],
            if (ticket.status == 'cancelled') ...[
              const SizedBox(height: 16),
              const Text('Este ticket não pode mais ser utilizado.',
                  textAlign: TextAlign.center)
            ],
            if (!blocked) ...[
              const _TicketDivider(),
              const Text('QUANTO ENTREGAR?',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontWeight: FontWeight.w900)),
              const SizedBox(height: 8),
              Row(children: [
                IconButton(
                    onPressed: _decrementQuantity,
                    icon: const Icon(Icons.remove_circle_outline)),
                Expanded(
                    child: Text(_quantityText(_quantity),
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                            fontSize: 24, fontWeight: FontWeight.w900))),
                IconButton(
                    onPressed: () => _incrementQuantity(remaining),
                    icon: const Icon(Icons.add_circle_outline))
              ]),
              const SizedBox(height: 8),
              FilledButton(
                  onPressed:
                      _state == _ValidatorState.reviewing ? _validate : null,
                  child: Text(_state == _ValidatorState.validating
                      ? 'REGISTRANDO...'
                      : 'ENTREGAR ${_quantityText(_quantity)}')),
              if (remaining > 1)
                OutlinedButton(
                    onPressed: () {
                      setState(() {
                        _quantity = ticket.redeemableQuantity;
                      });
                    },
                    child: Text(
                        'ENTREGAR TODAS AS ${_quantityText(ticket.redeemableQuantity)}')),
            ],
            const SizedBox(height: 8),
            TextButton(
                onPressed: _reset, child: const Text('VALIDAR OUTRO TICKET')),
          ])),
    );
  }

  Future<void> _reset() async {
    setState(() {
      _ticket = null;
      _number.clear();
      _quantity = '1.000';
      _validationKey = null;
      _redeemedNow = null;
      _inputMethod = 'manual';
      _state = _ValidatorState.scanning;
    });
    await _startScannerAfterFrame();
  }

  Future<void> _startScannerAfterFrame() async {
    await WidgetsBinding.instance.endOfFrame;
    if (!mounted ||
        _state != _ValidatorState.scanning ||
        _startingScanner ||
        _scanner.value.isRunning ||
        _scanner.value.isStarting) {
      return;
    }
    _startingScanner = true;
    try {
      await _scanner.start();
    } on MobileScannerException {
      // The preview's error builder handles denied or unavailable cameras.
    } finally {
      _startingScanner = false;
    }
  }

  Widget _successPanel(TicketValidationTicket ticket) =>
      Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        const Icon(Icons.check_circle_rounded,
            size: 72, color: Color(0xff16803c)),
        const SizedBox(height: 16),
        Text(
            ticket.status == 'used'
                ? 'TICKET TOTALMENTE UTILIZADO'
                : 'ENTREGA REGISTRADA',
            textAlign: TextAlign.center,
            style: const TextStyle(fontWeight: FontWeight.w900)),
        const SizedBox(height: 12),
        Text('TICKET ${_ticketNumber(ticket.number)}',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900)),
        Text(ticket.productName, textAlign: TextAlign.center),
        const SizedBox(height: 16),
        _quantityLine('Entregue agora', _redeemedNow ?? '0'),
        _quantityLine('Total retirado', ticket.redeemedQuantity),
        _quantityLine('Restante', ticket.redeemableQuantity),
        const SizedBox(height: 20),
        FilledButton(
            onPressed: _reset, child: const Text('VALIDAR OUTRO TICKET')),
      ]);

  String _ticketNumber(int number) => '#${number.toString().padLeft(4, '0')}';
  String _quantityText(String value) => value
      .replaceFirst(RegExp(r'\.0+$'), '')
      .replaceFirst(RegExp(r'(\.\d*?)0+$'), r'$1')
      .replaceAll('.', ',');
  String _statusText(String status) => switch (status) {
        'issued' => 'VÁLIDO',
        'partially_used' => 'PARCIALMENTE USADO',
        'used' => 'USADO',
        'cancelled' => 'CANCELADO',
        _ => status
      };
  Widget _quantityLine(String label, String value) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(children: [
        Expanded(child: Text(label)),
        Text(_quantityText(value),
            style: const TextStyle(fontWeight: FontWeight.w800))
      ]));
  void _decrementQuantity() {
    final value = double.tryParse(_quantity) ?? 1;
    if (value > 1) {
      setState(() {
        _quantity = (value - 1).toStringAsFixed(3);
      });
    }
  }

  void _incrementQuantity(double remaining) {
    final value = double.tryParse(_quantity) ?? 0;
    if (value < remaining) {
      setState(() {
        _quantity = (value + 1).clamp(0, remaining).toStringAsFixed(3);
      });
    }
  }
}

class _TicketDivider extends StatelessWidget {
  const _TicketDivider();
  @override
  Widget build(BuildContext context) => const Padding(
      padding: EdgeInsets.symmetric(vertical: 18),
      child: Text('- - - - - - - - - - - - - - - -',
          textAlign: TextAlign.center,
          style: TextStyle(color: Color(0xff94a3b8))));
}
