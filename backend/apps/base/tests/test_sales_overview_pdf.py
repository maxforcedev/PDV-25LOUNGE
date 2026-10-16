import io
import re
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

    def render(self, rows=None, summary=None, *, pdf_mode='executive'):
        return render_report_export(
            self.request(f'scope=overview&export=pdf&operator=7&page=2&pdf_mode={pdf_mode}'),
            filename='relatorio-vendas.csv', title='Vendas',
            headers=('sale_number', 'items', 'payments'), rows=rows or [],
            period={'start_datetime': '2026-09-10T00:00:00-03:00',
                     'end_datetime': '2026-10-09T23:59:59-03:00'}, summary=summary or {},
        )

    def test_nested_data_and_real_period_are_readable_and_concise(self):
        rows = [{
            'sale_number': f'V{index:06}', 'event_at': '2026-10-09T19:00:00-03:00',
            'status': 'finalized', 'event_type': 'record', 'total_received': ['62.00', '62.00', '6.00'][index-1],
            'operator': {'id': 7, 'name': 'Operador & <Nome>'},
            'items': [{'product_name': 'Produto especial', 'quantity': '1.000',
                       'unit_price': '43.33', 'net_subtotal': '43.33'}],
            'payments': [{'payment_method_name': 'PIX', 'amount': '43.33',
                          'received_amount': None, 'change_amount': None}],
        } for index in range(1, 4)]
        summary = {'gross': '130.00', 'sales_revenue': '130.00', 'count': 3,
                   'ticket_average': '43.33', 'total_received': '130.00',
                   'payment_totals': [{'name': 'PIX', 'payment_total': '130.00'}]}
        response = self.render(rows, summary, pdf_mode='detailed')
        reader = PdfReader(io.BytesIO(response.content))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        self.assertLessEqual(len(reader.pages), 4)
        for expected in ['10/09/2026', '09/10/2026', 'R$ 130,00', 'V000001',
                          'V000003', 'Produto especial', 'Operador & <Nome>', 'PIX']:
            self.assertIn(expected, text)
        self.assertNotIn('product_name', text)
        self.assertNotIn('start_datetime', text)
        self.assertNotIn('{', text)
        for index, page in enumerate(reader.pages, 1):
            self.assertRegex(
                page.extract_text(), rf'P.gina {index} de {len(reader.pages)}',
            )
            self.assertTrue(page['/Resources'].get('/XObject'))
            self.assertIn('& <CARIOCA>', page.extract_text())

    def test_long_report_contains_every_row_and_repeats_headers(self):
        rows = [{'sale_number': f'V{index:06}', 'event_at': '2026-10-09T19:00:00-03:00',
                 'status': 'finalized', 'event_type': 'record', 'total_received': '1.00'}
                for index in range(120)]
        reader = PdfReader(io.BytesIO(self.render(rows, pdf_mode='detailed').content))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        for index in range(120):
            self.assertIn(f'Venda V{index:06}', text)
        self.assertGreater(len(reader.pages), 2)
        self.assertIn('Vendas detalhadas', text)
        for index, page in enumerate(reader.pages, 1):
            page_text = page.extract_text()
            self.assertIn('DETALHADO', page_text)
            self.assertRegex(page_text, rf'P.gina {index} de {len(reader.pages)}')

    def test_executive_summary_contains_only_consolidated_sales_data(self):
        rows = [{
            'sale_number': 'V000001', 'event_at': '2026-10-09T19:00:00-03:00',
            'status': 'finalized', 'event_type': 'record', 'total_received': '130.00',
            'operator': {'id': 7, 'name': 'Operador & <Nome>'},
            'items': [{'product_name': 'Produto especial', 'quantity': '1.000'}],
            'payments': [{'payment_method_name': 'PIX', 'amount': '130.00'}],
        }]
        summary = {'gross': '130.00', 'sales_revenue': '130.00', 'count': 3,
                   'ticket_average': '43.33', 'total_received': '130.00',
                   'payment_totals': [{'name': 'PIX', 'payment_total': '130.00'}]}
        reader = PdfReader(io.BytesIO(self.render(rows, summary).content))
        self.assertEqual(len(reader.pages), 1)
        text = reader.pages[0].extract_text()
        for expected in ['RESUMO EXECUTIVO', 'FATURAMENTO', 'VENDAS', 'R$ 130,00',
                         'R$ 43,33', 'PIX', 'Matriz', '& <CARIOCA>', '10/09/2026',
                         '09/10/2026', 'Escopo: overview, Operador: 7']:
            self.assertIn(expected, text)
        self.assertRegex(text, r'TICKET M.DIO')
        self.assertRegex(text, r'P.gina 1 de 1')
        for unexpected in ['V000001', 'Produto especial', 'Operador & <Nome>',
                           'Vendas detalhadas', 'product_name']:
            self.assertNotIn(unexpected, text)

    def test_empty_data_does_not_invent_zero_values(self):
        reader = PdfReader(io.BytesIO(self.render().content))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        self.assertIn('Sem dados consolidados', text)
        self.assertNotIn('Sem registros', text)
        self.assertNotIn('R$ 0,00', text)
