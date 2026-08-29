from dataclasses import dataclass
import socket


@dataclass(frozen=True)
class PrintOutcome:
    status: str
    detail: str = ''


class PrinterAdapter:
    """Adapter boundary; no hardware vendor is claimed by this application."""
    def dispatch(self, print_job):
        raise NotImplementedError


class ManualPrinterAdapter(PrinterAdapter):
    def dispatch(self, print_job):
        return PrintOutcome('manual_confirmed', 'Despacho manual confirmado pelo operador; nenhum hardware foi acionado.')


class NetworkPrinterAdapter(PrinterAdapter):
    def dispatch(self, print_job):
        configuration = print_job.printer_device.technical_configuration
        host, port = configuration.get('host'), configuration.get('port')
        timeout = configuration.get('timeout', 5)
        try:
            with socket.create_connection((host, port), timeout=float(timeout)) as connection:
                connection.sendall(b'CORE PDV\nTESTE DE IMPRESSAO\n' if print_job.is_test else b'CORE PDV\n')
            return PrintOutcome('manual_confirmed', 'Impressora de rede aceitou a conexão e os dados de impressão.')
        except (OSError, TypeError, ValueError):
            return PrintOutcome('failed', f'Não foi possível conectar à impressora {host}:{port}.')


class LocalBridgePrinterAdapter(PrinterAdapter):
    def dispatch(self, print_job):
        return PrintOutcome('failed', 'Print Bridge necessária para utilizar esta impressora.')


def adapter_for(print_job):
    if print_job.printer_device.connection_type == 'network':
        return NetworkPrinterAdapter()
    if print_job.printer_device.connection_type in ('usb', 'bluetooth'):
        return LocalBridgePrinterAdapter()
    return ManualPrinterAdapter()
