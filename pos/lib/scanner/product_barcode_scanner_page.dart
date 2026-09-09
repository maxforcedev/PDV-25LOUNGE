import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'barcode_cooldown.dart';

class ProductBarcodeScannerPage extends StatefulWidget {
  const ProductBarcodeScannerPage({required this.onBarcode, super.key});

  final Future<void> Function(String barcode) onBarcode;

  @override
  State<ProductBarcodeScannerPage> createState() =>
      _ProductBarcodeScannerPageState();
}

class _ProductBarcodeScannerPageState extends State<ProductBarcodeScannerPage> {
  final _controller = MobileScannerController();
  final _cooldown = BarcodeCooldown();
  bool _processing = false;
  String? _message;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture capture) async {
    final barcode = capture.barcodes.firstOrNull?.rawValue?.trim();
    if (_processing || barcode == null || !_cooldown.accept(barcode)) return;
    setState(() {
      _processing = true;
      _message = 'Consultando produto...';
    });
    await _controller.stop();
    await widget.onBarcode(barcode);
    if (!mounted) return;
    setState(() {
      _processing = false;
      _message = 'Produto processado. Aponte para o próximo código.';
    });
    await WidgetsBinding.instance.endOfFrame;
    if (mounted &&
        !_processing &&
        !_controller.value.isRunning &&
        !_controller.value.isStarting) {
      await _controller.start();
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
                  Text(_message!, textAlign: TextAlign.center),
                ],
                const SizedBox(height: 12),
                OutlinedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('CANCELAR'),
                ),
              ]),
            ),
          ]),
        ),
      );
}
