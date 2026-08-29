from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.production.adapters import LocalBridgePrinterAdapter, NetworkPrinterAdapter


class PrinterAdapterTests(SimpleTestCase):
    def network_job(self, host='192.168.1.50', port=9100):
        return SimpleNamespace(
            is_test=True,
            printer_device=SimpleNamespace(technical_configuration={'host': host, 'port': port, 'timeout': 1}),
        )

    @patch('apps.production.adapters.socket.create_connection')
    def test_network_adapter_confirms_only_after_connection_and_send(self, connect):
        connection = MagicMock()
        connect.return_value.__enter__.return_value = connection
        outcome = NetworkPrinterAdapter().dispatch(self.network_job())
        self.assertEqual(outcome.status, 'manual_confirmed')
        connection.sendall.assert_called_once()

    @patch('apps.production.adapters.socket.create_connection', side_effect=TimeoutError('timed out'))
    def test_network_adapter_reports_timeout(self, _connect):
        outcome = NetworkPrinterAdapter().dispatch(self.network_job())
        self.assertEqual(outcome.status, 'failed')
        self.assertIn('Não foi possível conectar', outcome.detail)

    @patch('apps.production.adapters.socket.create_connection', side_effect=ConnectionRefusedError('refused'))
    def test_network_adapter_reports_refused_connection(self, _connect):
        outcome = NetworkPrinterAdapter().dispatch(self.network_job())
        self.assertEqual(outcome.status, 'failed')
        self.assertIn('Não foi possível conectar', outcome.detail)

    def test_local_bridge_adapter_fails_controlled_without_bridge(self):
        outcome = LocalBridgePrinterAdapter().dispatch(SimpleNamespace())
        self.assertEqual(outcome.status, 'failed')
        self.assertIn('Print Bridge', outcome.detail)
