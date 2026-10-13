import io
from types import SimpleNamespace

from django.http import QueryDict
from django.test import SimpleTestCase
from pypdf import PdfReader

from apps.base.report_exports import render_report_export


class SalesOverviewPdfTests(SimpleTestCase):
    def request(self, query='scope=overview&export=pdf&operator=7&page=2'):
        return SimpleNamespace(
            query_params=QueryDict(query),
            branch_context=SimpleNamespace(name='Matriz', company=SimpleNamespace(
                trade_name='ESPAÇO & <CARIOCA>', legal_name='Empresa', cnpj=None)),
        )

    def render(self, rows=None, summary=None):
        return render_report_export(
            self.request(), filename='relatorio-vendas.csv', title='Vendas',
            headers=('sale_number', 'items', 'payments'), rows=rows or [],
            period={'start_datetime': '2026-09-10T00:00:00-03:00',
                    'end_datetime': '2026-10-09T23:59:59-03:00'}, summary=summary or {},
        )

    def test_nested_data_and_real_period_are_readable_and_concise(self):
        rows = [{
            'sale_number': f'V{index:06}', 'event_at': '2026-10-09T19:00:00-03:00',
            'status': 'finalized', 'event_type': 'record', 'total_received': ['62.00', '62.00', '6.00'][index-1],
            'operator': {'id': 7, 'name': 'Operador & <Nome>'},
            'items': [{'product_name': 'Produto com acentuação', 'quantity': '1.000',
                       'unit_price': '43.33', 'net_subtotal': '43.33'}],
            'payments': [{'payment_method_name': 'PIX', 'amount': '43.33',
                          'received_amount': None, 'change_amount': None}],
        } for index in range(1, 4)]
        summary = {'gross': '130.00', 'sales_revenue': '130.00', 'count': 3,
                   'ticket_average': '43.33', 'total_received': '130.00',
                   'payment_totals': [{'name': 'PIX', 'payment_total': '130.00'}]}
        response = self.render(rows, summary)
        reader = PdfReader(io.BytesIO(response.content))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        self.assertLessEqual(len(reader.pages), 4)
        for expected in ['10/09/2026', '09/10/2026', 'R$ 130,00', 'V000001',
                         'V000003', 'Produto com acentuação', 'Operador & <Nome>',
                         'Operador: 7', 'ESPAÇO & <CARIOCA>']:
            self.assertIn(expected, text)
        self.assertNotIn('product_name', text)
        self.assertNotIn('start_datetime', text)
        self.assertNotIn('{', text)
        self.assertNotIn('Página: 2', text)
        for index, page in enumerate(reader.pages, 1):
            self.assertIn(f'Página {index} de {len(reader.pages)}', page.extract_text())
            self.assertTrue(page['/Resources'].get('/XObject'))
            self.assertIn('ESPAÇO & <CARIOCA>', page.extract_text())

    def test_long_report_contains_every_row_and_repeats_headers(self):
        rows = [{'sale_number': f'V{index:06}', 'event_at': '2026-10-09T19:00:00-03:00',
                 'status': 'finalized', 'event_type': 'record', 'total_received': '1.00'}
                for index in range(120)]
        reader = PdfReader(io.BytesIO(self.render(rows).content))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        self.assertIn('V000000', text)
        self.assertIn('V000119', text)
        self.assertGreater(len(reader.pages), 2)
        self.assertGreater(text.count('Data do evento'), 1)

    def test_empty_data_does_not_invent_zero_values(self):
        reader = PdfReader(io.BytesIO(self.render().content))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        self.assertIn('Sem registros', text)
        self.assertNotIn('R$ 0,00', text)
