import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'models.dart';

enum PrintTransportState { sent, failedBeforeSend, uncertain }

class PrintTransportResult {
  const PrintTransportResult(this.state, [this.detail = '']);
  final PrintTransportState state;
  final String detail;
}

class NetworkPrinterTransport {
  Future<PrintTransportResult> send(
      NetworkPrinter printer, Uint8List bytes) async {
    if (printer.host.trim().isEmpty ||
        printer.port < 1 ||
        printer.port > 65535) {
      return const PrintTransportResult(PrintTransportState.failedBeforeSend,
          'Configuração de rede inválida.');
    }
    Socket? socket;
    var started = false;
    try {
      socket = await Socket.connect(printer.host, printer.port,
          timeout: Duration(seconds: printer.timeoutSeconds));
      socket.add(bytes);
      started = true;
      await socket.flush().timeout(Duration(seconds: printer.timeoutSeconds));
      await socket.close().timeout(Duration(seconds: printer.timeoutSeconds));
      return const PrintTransportResult(PrintTransportState.sent);
    } on TimeoutException {
      return PrintTransportResult(
          started
              ? PrintTransportState.uncertain
              : PrintTransportState.failedBeforeSend,
          started
              ? 'Timeout após iniciar o envio para a impressora.'
              : 'Timeout ao conectar à impressora.');
    } on SocketException catch (error) {
      return PrintTransportResult(
          started
              ? PrintTransportState.uncertain
              : PrintTransportState.failedBeforeSend,
          error.message);
    } catch (error) {
      return PrintTransportResult(
          started
              ? PrintTransportState.uncertain
              : PrintTransportState.failedBeforeSend,
          error.toString());
    } finally {
      socket?.destroy();
    }
  }
}
