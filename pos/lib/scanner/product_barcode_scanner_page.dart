import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'barcode_cooldown.dart';

class ProductBarcodeScannerPage extends StatefulWidget {
  const ProductBarcodeScannerPage({
    required this.onBarcode,
    required this.cartListenable,
    required this.itemCount,
    required this.total,
    super.key,
  });

  final Future<bool> Function(String barcode) onBarcode;
  final Listenable cartListenable;
  final String Function() itemCount;
  final String Function() total;

  @override
  State<ProductBarcodeScannerPage> createState() =>
      _ProductBarcodeScannerPageState();
}

class _ProductBarcodeScannerPageState extends State<ProductBarcodeScannerPage> {
  final _controller = MobileScannerController();
  final _cooldown = BarcodeCooldown();
  bool _processing = false;
  String? _message;
  String? _lastProcessedBarcode;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    final barcode = capture.barcodes.firstOrNull?.rawValue?.trim();
    if (_processing || barcode == null || !_cooldown.accept(barcode)) return;
    _lastProcessedBarcode = barcode;
    setState(() {
      _processing = true;
      _message = 'Consultando produto...';
    });
    await _controller.stop();
    final accepted = await widget.onBarcode(barcode);
    if (!mounted) return;
    setState(() {
      _processing = false;
      _message = accepted
          ? 'Produto adicionado. Aponte para o próximo código.'
          : 'Produto não encontrado. Aponte para o próximo código.';
    });
    if (accepted) SystemSound.play(SystemSoundType.click);
    await WidgetsBinding.instance.endOfFrame;
    if (mounted &&
        !_processing &&
        !_controller.value.isRunning &&
        !_controller.value.isStarting) {
      await _controller.start();
      _cooldown.keepBlocked(_lastProcessedBarcode ?? '');
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('ESCANEAR PRODUTO'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('CONCLUIR'),
            ),
          ],
        ),
        body: SafeArea(
          child: Column(children: [
            Expanded(
              child: Stack(fit: StackFit.expand, children: [
                MobileScanner(
                  controller: _controller,
                  onDetect: _onDetect,
                  errorBuilder: (context, error) => Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.no_photography_outlined, size: 48),
                          const SizedBox(height: 12),
                          const Text(
                            'Não foi possível acessar a câmera. Você ainda pode buscar o produto manualmente.',
                            textAlign: TextAlign.center,
                          ),
                          TextButton(
                            onPressed: () => Navigator.of(context).pop(),
                            child: const Text('VOLTAR À VENDA'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                Center(
                  child: Container(
                    width: 260,
                    height: 150,
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.white, width: 3),
                      borderRadius: BorderRadius.circular(18),
                    ),
                  ),
                ),
                if (_processing)
                  const ColoredBox(
                    color: Color(0x66000000),
                    child: Center(child: CircularProgressIndicator()),
                  ),
              ]),
            ),
            Padding(
                padding: const EdgeInsets.all(20),
                child: Column(children: [
                  const Text('Aponte para o código de barras do produto',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontWeight: FontWeight.w800)),
                  if (_message != null) ...[
                    const SizedBox(height: 8),
                    Text(_message!, textAlign: TextAlign.center)
                  ],
                  const SizedBox(height: 12),
                  AnimatedBuilder(
                    animation: widget.cartListenable,
                    builder: (_, __) => Card(
                      margin: EdgeInsets.zero,
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Row(children: [
                          const Icon(Icons.shopping_cart_rounded),
                          const SizedBox(width: 10),
                          Expanded(
                              child: Text('${widget.itemCount()} itens',
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w800))),
                          Text(widget.total(),
                              style:
                                  const TextStyle(fontWeight: FontWeight.w900)),
                          const SizedBox(width: 10),
                          TextButton(
                              onPressed: () => Navigator.of(context).pop(true),
                              child: const Text('VER CARRINHO')),
                        ]),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton(
                      onPressed: () => Navigator.of(context).pop(),
                      child: const Text('CANCELAR')),
                ])),
          ]),
        ),
      );
}
