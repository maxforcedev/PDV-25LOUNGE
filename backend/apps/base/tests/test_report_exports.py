import csv
import io
from datetime import datetime
from types import SimpleNamespace

from django.http import QueryDict
from django.test import SimpleTestCase
from openpyxl import load_workbook
from pypdf import PdfReader
from unittest.mock import patch

from apps.base.report_exports import render_report_export
from apps.reports.views import BaseReportView


class ReportExportTests(SimpleTestCase):
    def setUp(self):
        query = QueryDict('', mutable=True)
        query.update({'export': 'pdf', 'search': '=SUM(A1)', 'branch': '999'})
        self.request = SimpleNamespace(
            query_params=query,
            branch_context=SimpleNamespace(
                name='Matriz & Centro',
                company=SimpleNamespace(
                    trade_name='A&B <Especial>', legal_name='Razão Social Ltda.',
                ),
            ),
        )
        self.headers = ('name', 'amount', 'created_at')
        self.rows = [{
            'name': '=SUM(A1)', 'amount': '12.50',
            'created_at': '2026-08-27T10:30:00+00:00',
        }]

    def render(self, export):
        self.request.query_params = self.request.query_params.copy()
        self.request.query_params['export'] = export
        return render_report_export(
            self.request, filename='relatorio.csv', title='A&B <Especial>',
            headers=self.headers, rows=self.rows, period='2026-08-01 a 2026-08-27',
            summary={'amount': '12.50'},
        )

    def test_pdf_escapes_company_metadata_and_is_readable(self):
        response = self.render('pdf')
        self.assertEqual(response['Content-Type'], 'application/pdf')
        reader = PdfReader(io.BytesIO(response.content))
        self.assertEqual(len(reader.pages), 1)
        text = reader.pages[0].extract_text()
        self.assertIn('A&B <Especial>', text)
        self.assertIn('Matriz & Centro', text)

    def test_csv_is_parseable_and_protects_formulas_without_changing_numbers(self):
        response = self.render('csv')
        parsed = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(parsed[1], ["'=SUM(A1)", '12.50', '2026-08-27T10:30:00+00:00'])

    def test_xlsx_preserves_typed_values_and_sanitizes_text_metadata(self):
        response = self.render('xlsx')
        workbook = load_workbook(io.BytesIO(response.content), data_only=False)
        summary = workbook['Resumo']
        details = workbook['Dados']
        self.assertEqual(summary['B2'].value, 'A&B <Especial>')
        self.assertEqual(summary['B8'].value, 12.50)
        self.assertEqual(details['A1'].value, 'Nome')
        self.assertEqual(details['A2'].value, "'=SUM(A1)")
        self.assertEqual(details['B2'].value, 12.50)
        self.assertIsInstance(details['C2'].value, datetime)
        self.assertEqual(details.freeze_panes, 'A2')
        self.assertEqual(details.auto_filter.ref, 'A1:C2')

    def test_export_removes_commission_when_not_visible_in_report(self):
        class Report(BaseReportView):
            csv_headers = ('name', 'commission', 'amount')

            def serialize_rows(self, rows, request):
                return rows

        self.request.query_params = QueryDict('export=csv')
        self.request.user = SimpleNamespace()
        with patch('apps.reports.views.user_has_code', return_value=False), patch(
            'apps.reports.views.audit_log'
        ):
            response = Report().respond(
                self.request,
                rows=[{'name': 'Linha', 'commission': '99.00', 'amount': '10.00'}],
                period='Hoje', summary={'commission': '99.00', 'amount': '10.00'},
            )
        parsed = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(parsed[0], ['Nome', 'Valor'])
        self.assertNotIn('99.00', response.content.decode('utf-8-sig'))

    def test_export_uses_all_filtered_rows_not_the_visual_page(self):
        class Report(BaseReportView):
            csv_headers = ('id', 'name')

            def serialize_rows(self, rows, request):
                return rows

        self.request.query_params = QueryDict(
            'export=csv&start_datetime=2026-08-01T00:00:00Z&end_datetime=2026-08-31T23:59:59Z&seller=7&page=2&page_size=10'
        )
        self.request.user = SimpleNamespace()
        rows = [{'id': number, 'name': f'Operação {number}'} for number in range(1, 26)]
        with patch('apps.reports.views.user_has_code', return_value=True), patch(
            'apps.reports.views.audit_log'
        ):
            response = Report().respond(
                self.request, rows=rows, period='Agosto', summary={'count': 25},
            )
        parsed = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(len(parsed), 26)
        self.assertEqual(parsed[1], ['1', 'Operação 1'])
        self.assertEqual(parsed[-1], ['25', 'Operação 25'])
