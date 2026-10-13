"""Generate the visual approval PDFs with clearly identified demonstration data.

Run from ``backend`` with ``python -m apps.base.report_pdf_demo``. This is a
presentation-artifact generator, not an automated test or a production export.
"""
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

import django

django.setup()

from .report_exports import report_key_value_rows
from .report_pdf import render_pdf_export


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / 'docs' / 'report-examples'
PERIOD = {'start_datetime': '2026-10-01T00:00:00-03:00', 'end_datetime': '2026-10-13T23:59:00-03:00'}
COMPANY = SimpleNamespace(trade_name='Empresa Demonstração', legal_name='Empresa Demonstração')
BRANCH = SimpleNamespace(company=COMPANY, name='Unidade Centro')


class DemoRequest:
    branch_context = BRANCH

    def __init__(self, mode):
        self.query_params = {'pdf_mode': mode}


def _sales_rows():
    payments = ('Cartão de crédito', 'PIX', 'Dinheiro', 'PIX', 'Cartão de débito')
    amounts = ('184.00', '72.00', '140.00', '230.00', '96.00', '315.00', '68.00', '120.00', '54.00', '195.00', '89.00', '160.00')
    rows = []
    for index, amount in enumerate(amounts):
        number = 10284 - index
        payment = payments[index % len(payments)]
        rows.append({
            'event_at': f'2026-10-13T{21 - index // 3:02d}:{36 - (index % 3) * 11:02d}:00-03:00',
            'sale_number': f'#{number}', 'status': 'finalized', 'payment_method_name': payment,
            'total_received': amount, 'operator': 'Equipe Centro',
            'items': [{'product_name': 'Heineken Long Neck', 'quantity': '2', 'unit_price': '12.00', 'net_subtotal': '24.00'}],
            'payments': [{'payment_method_name': payment, 'applied_amount': amount, 'received_amount': amount, 'change_amount': '0.00'}],
        })
    return rows


SALES_SUMMARY = {
    'gross': '24850.00', 'sales_revenue': '23720.00', 'count': 162,
    'ticket_average': '146.42', 'total_discount': '1130.00', 'service_fee': '0.00',
    'total_received': '23720.00',
    'payment_totals': [
        {'name': 'PIX', 'payment_total': '12334.40', 'percentage': '52.00'},
        {'name': 'Cartão', 'payment_total': '8064.80', 'percentage': '34.00'},
        {'name': 'Dinheiro', 'payment_total': '3320.80', 'percentage': '14.00'},
    ],
    'hourly_sales': [
        {'hour': '07/10', 'sales_revenue': '2510.00'}, {'hour': '08/10', 'sales_revenue': '2980.00'},
        {'hour': '09/10', 'sales_revenue': '3370.00'}, {'hour': '10/10', 'sales_revenue': '3100.00'},
        {'hour': '11/10', 'sales_revenue': '4020.00'}, {'hour': '12/10', 'sales_revenue': '3550.00'},
        {'hour': '13/10', 'sales_revenue': '4190.00'},
    ],
    'product_ranking': [
        {'product_name': 'Heineken Long Neck', 'quantity': '94'}, {'product_name': 'Red Bull Tradicional', 'quantity': '58'},
        {'product_name': 'Combo Gin', 'quantity': '32'}, {'product_name': 'Água sem gás', 'quantity': '29'},
    ],
}


RESULT_SUMMARY = {
    'effective_revenue': '23720.00', 'historical_sales_cogs': '11850.00',
    'commission': '480.00', 'operating_expenses': '2850.00', 'costs_and_expenses': '15980.00',
    'estimated_result': '7740.00', 'margin': '32.63',
    'notice': 'O resultado é uma estimativa gerencial baseada nos dados demonstrativos disponíveis no CORE PDV; não constitui DRE contábil.',
}


STOCK_ROWS = [
    {'product': 'Heineken Long Neck', 'current_quantity': '8', 'minimum_quantity': '30', 'unit': 'un.', 'state': 'below_minimum'},
    {'product': 'Red Bull Melancia', 'current_quantity': '0', 'minimum_quantity': '15', 'unit': 'un.', 'state': 'zero'},
    {'product': 'Gelo em cubos', 'current_quantity': '2', 'minimum_quantity': '10', 'unit': 'sacos', 'state': 'below_minimum'},
    {'product': 'Água sem gás', 'current_quantity': '-2', 'minimum_quantity': '20', 'unit': 'un.', 'state': 'negative'},
    {'product': 'Coca-Cola lata', 'current_quantity': '4', 'minimum_quantity': '24', 'unit': 'un.', 'state': 'below_minimum'},
    {'product': 'Tônica lata', 'current_quantity': '0', 'minimum_quantity': '12', 'unit': 'un.', 'state': 'zero'},
    {'product': 'Whisky 12 anos', 'current_quantity': '1', 'minimum_quantity': '4', 'unit': 'un.', 'state': 'below_minimum'},
]
STOCK_SUMMARY = {'product_count': 248, 'below_minimum': 12, 'zero': 6, 'negative': 2, 'inventory_value': '52610.00'}


def _write(name, title, mode, headers, rows, summary, period=PERIOD):
    response = render_pdf_export(
        DemoRequest(mode), filename=name, title=title, headers=headers, rows=rows,
        period=period, summary=summary, filters='DADOS DEMONSTRATIVOS',
    )
    (OUTPUT / name).write_bytes(response.content)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sale_headers = ('event_at', 'sale_number', 'status', 'total_received', 'operator', 'items', 'payments')
    sales_rows = _sales_rows()
    _write('vendas-executivo-demo.pdf', 'Relatório de Vendas', 'executive', sale_headers, sales_rows, SALES_SUMMARY)
    _write('vendas-detalhado-demo.pdf', 'Relatório de Vendas', 'detailed', sale_headers, sales_rows, SALES_SUMMARY)
    _write('resultado-operacional-demo.pdf', 'Resultado Operacional', 'executive', ('statement', 'value'), [], RESULT_SUMMARY)
    _write('posicao-estoque-demo.pdf', 'Posição de Estoque', 'executive', ('product', 'current_quantity', 'minimum_quantity', 'unit', 'state'), STOCK_ROWS, STOCK_SUMMARY, {'as_of': '2026-10-13T11:40:00-03:00'})
    dashboard = {'sales': SALES_SUMMARY, 'inventory': STOCK_SUMMARY, 'commands': {'open_count': 4}}
    _write('dashboard-executivo-demo.pdf', 'Dashboard Executivo', 'executive', ('indicator', 'value'), report_key_value_rows(dashboard), dashboard)


if __name__ == '__main__':
    main()
