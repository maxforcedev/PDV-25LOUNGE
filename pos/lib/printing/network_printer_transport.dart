import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'models.dart';

enum PrintTransportState { sent, failedBeforeSend, uncertain }

class PrintTransportResult {
  const PrintTransportResult(this.state,
      {this.detail = '', this.printerObserved = false});
  final PrintTransportState state;
  final String detail;
  final bool printerObserved;
}

class NetworkPrinterTransport {
  Future<PrintTransportResult> send(
      NetworkPrinter printer, Uint8List bytes) async {
    if (printer.host.trim().isEmpty ||
        printer.port < 1 ||
        printer.port > 65535) {
      return const PrintTransportResult(PrintTransportState.failedBeforeSend,
          detail: 'Configuração de rede inválida.');
    }
    Socket? socket;
    var started = false;
    var connected = false;
    try {
      socket = await Socket.connect(printer.host, printer.port,
          timeout: Duration(seconds: printer.timeoutSeconds));
      connected = true;
      socket.add(bytes);
      started = true;
      await socket.flush().timeout(Duration(seconds: printer.timeoutSeconds));
      await socket.close().timeout(Duration(seconds: printer.timeoutSeconds));
      return const PrintTransportResult(PrintTransportState.sent,
          printerObserved: true);
    } on TimeoutException {
      return PrintTransportResult(
          started
              ? PrintTransportState.uncertain
              : PrintTransportState.failedBeforeSend,
          detail: started
              ? 'Timeout após iniciar o envio para a impressora.'
              : 'Timeout ao conectar à impressora.',
          printerObserved: connected);
    } on SocketException catch (error) {
      return PrintTransportResult(
          started
              ? PrintTransportState.uncertain
              : PrintTransportState.failedBeforeSend,
          detail: error.message,
          printerObserved: connected);
    } catch (error) {
      return PrintTransportResult(
          started
              ? PrintTransportState.uncertain
              : PrintTransportState.failedBeforeSend,
          detail: error.toString(),
          printerObserved: connected);
    } finally {
      socket?.destroy();
    }
  }
}
