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
    coca_modifier = {
        'group_id': 41, 'group_name': 'Adicionais', 'option_id': 412,
        'option_name': 'Coca Lata', 'option_type': 'product_input',
        'additional_price': '7.00', 'selected_quantity': '2', 'contribution': '14.00',
        'stock_product_id': 10, 'stock_product_name': 'Coca Lata',
        'stock_effect': 'product_input',
    }
    return [
        {
            'event_at': '2026-10-13T18:10:00-03:00', 'sale_number': 'V000001',
            'status': 'finalized', 'channel': 'counter', 'operator': 'Equipe Centro',
            'total_received': '22.00', 'sales_revenue': '22.00', 'payment_total': '22.00',
            'items': [
                {'id': 1, 'product_name': 'Coca Lata', 'quantity': '2', 'unit': 'un.', 'unit_price': '7.00', 'subtotal': '14.00', 'net_subtotal': '14.00'},
                {'id': 2, 'product_name': 'Amendoim', 'quantity': '1', 'unit': 'un.', 'unit_price': '8.00', 'subtotal': '8.00', 'net_subtotal': '8.00'},
            ],
            'payments': [{'payment_method_name': 'PIX', 'applied_amount': '22.00', 'received_amount': '22.00', 'change_amount': '0.00'}],
        },
        {
            'event_at': '2026-10-13T19:25:00-03:00', 'sale_number': 'V000002',
            'status': 'finalized', 'channel': 'counter', 'operator': 'Equipe Centro',
            'total_received': '105.00', 'sales_revenue': '105.00', 'payment_total': '105.00',
            'items': [
                {'id': 3, 'product_name': 'Coca Lata', 'quantity': '6', 'unit': 'un.', 'unit_price': '7.00', 'subtotal': '42.00', 'net_subtotal': '42.00'},
                {'id': 4, 'product_name': 'Combo da Casa', 'quantity': '1', 'unit': 'un.', 'unit_price': '63.00', 'subtotal': '63.00', 'net_subtotal': '63.00'},
            ],
            'payments': [{'payment_method_name': 'Cartão de crédito', 'applied_amount': '105.00', 'received_amount': '105.00', 'change_amount': '0.00'}],
        },
        {
            'event_at': '2026-10-13T20:40:00-03:00', 'sale_number': 'V000003',
            'status': 'finalized', 'channel': 'counter', 'operator': 'Equipe Centro',
            'total_received': '36.00', 'sales_revenue': '36.00', 'payment_total': '36.00',
            'items': [{
                'id': 5, 'product_name': 'Batata Frita', 'quantity': '1', 'unit': 'un.',
                'unit_price': '36.00', 'base_unit_price': '22.00', 'modifier_unit_total': '14.00',
                'modifier_snapshot': [coca_modifier], 'subtotal': '36.00', 'net_subtotal': '36.00',
            }],
            'payments': [
                {'payment_method_name': 'Cartão de crédito', 'applied_amount': '5.00', 'received_amount': '5.00', 'change_amount': '0.00'},
                {'payment_method_name': 'PIX', 'applied_amount': '20.00', 'received_amount': '20.00', 'change_amount': '0.00'},
                {'payment_method_name': 'Dinheiro', 'applied_amount': '11.00', 'received_amount': '11.00', 'change_amount': '0.00'},
            ],
        },
    ]


SALES_SUMMARY = {
    'gross': '163.00', 'sales_revenue': '163.00', 'count': 3,
    'ticket_average': '54.33', 'total_discount': '0.00', 'service_fee': '0.00',
    'total_received': '163.00', 'payment_total': '163.00', 'reconciliation_delta': '0.00',
    'payment_totals': [
        {'name': 'PIX', 'payment_total': '42.00', 'percentage': '25.77'},
        {'name': 'Cartão de crédito', 'payment_total': '110.00', 'percentage': '67.48'},
        {'name': 'Dinheiro', 'payment_total': '11.00', 'percentage': '6.75'},
    ],
    'hourly_sales': [
        {'hour': '20:00', 'sales_revenue': '163.00'},
    ],
    'product_ranking': [
        {'product_name': 'Coca Lata', 'quantity': '8', 'unit': 'un.', 'sales_revenue': '56.00'},
        {'product_name': 'Amendoim', 'quantity': '1', 'unit': 'un.', 'sales_revenue': '8.00'},
        {'product_name': 'Batata Frita', 'quantity': '1', 'unit': 'un.', 'sales_revenue': '36.00'},
        {'product_name': 'Combo da Casa', 'quantity': '1', 'unit': 'un.', 'sales_revenue': '63.00'},
    ],
    'product_consumption': [
        {'product_name': 'Coca Lata', 'unit': 'un.', 'direct_quantity': '8', 'modifier_quantity': '2', 'consolidated_quantity': '10'},
        {'product_name': 'Amendoim', 'unit': 'un.', 'direct_quantity': '1', 'modifier_quantity': '0', 'consolidated_quantity': '1'},
        {'product_name': 'Batata Frita', 'unit': 'un.', 'direct_quantity': '1', 'modifier_quantity': '0', 'consolidated_quantity': '1'},
    ],
    'modifier_ranking': [
        {'group_name': 'Adicionais', 'option_name': 'Coca Lata', 'quantity': '2', 'additional_revenue': '14.00'},
    ],
}


RESULT_SUMMARY = {
    'effective_revenue': '23720.00', 'historical_sales_cogs': '11850.00',
    'commission': '480.00', 'operating_expenses': '2850.00', 'costs_and_expenses': '15180.00',
    'estimated_result': '8540.00', 'margin': '36.00',
    'notice': 'O resultado é uma estimativa gerencial baseada nos dados demonstrativos disponíveis no CORE PDV; não constitui DRE contábil.',
}


STOCK_ROWS = [
    {'product': {'id': 1, 'name': 'Heineken Long Neck', 'internal_code': 'HEI-LN'}, 'current_quantity': '8.000', 'minimum_quantity': '30.000', 'unit': 'un.', 'state': 'below_minimum'},
    {'product': {'id': 2, 'name': 'Red Bull Melancia', 'internal_code': 'RED-MEL'}, 'current_quantity': '0.000', 'minimum_quantity': '15.000', 'unit': 'un.', 'state': 'zero'},
    {'product': {'id': 3, 'name': 'Gelo em cubos', 'internal_code': 'GEL-CUB'}, 'current_quantity': '2.000', 'minimum_quantity': '10.000', 'unit': 'sacos', 'state': 'below_minimum'},
    {'product': {'id': 4, 'name': 'Água sem gás', 'internal_code': 'AGU-SG'}, 'current_quantity': '-2.000', 'minimum_quantity': '20.000', 'unit': 'un.', 'state': 'negative'},
    {'product': {'id': 5, 'name': 'Coca-Cola lata', 'internal_code': 'COC-LAT'}, 'current_quantity': '4.000', 'minimum_quantity': '24.000', 'unit': 'un.', 'state': 'below_minimum'},
    {'product': {'id': 6, 'name': 'Tônica lata', 'internal_code': 'TON-LAT'}, 'current_quantity': '0.000', 'minimum_quantity': '12.000', 'unit': 'un.', 'state': 'zero'},
    {'product': {'id': 7, 'name': 'Whisky 12 anos', 'internal_code': 'WHI-12'}, 'current_quantity': '1.000', 'minimum_quantity': '4.000', 'unit': 'un.', 'state': 'below_minimum'},
]
STOCK_SUMMARY = {'product_count': 248, 'below_minimum': 12, 'zero': 6, 'negative': 2, 'inventory_value': '52610.00'}


def _write(name, title, mode, headers, rows, summary, period=PERIOD, sample_label=''):
    response = render_pdf_export(
        DemoRequest(mode), filename=name, title=title, headers=headers, rows=rows,
        period=period, summary=summary, filters='DADOS DEMONSTRATIVOS',
        sample_label=sample_label,
    )
    (OUTPUT / name).write_bytes(response.content)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sale_headers = ('event_at', 'sale_number', 'status', 'payment_method_name', 'total_received', 'operator', 'items', 'payments')
    sales_rows = _sales_rows()
    _write('vendas-executivo-demo.pdf', 'Relatório de Vendas', 'executive', sale_headers, sales_rows, SALES_SUMMARY)
    _write(
        'vendas-detalhado-demo.pdf', 'Relatório de Vendas', 'detailed', sale_headers,
        sales_rows, SALES_SUMMARY,
        sample_label='Dados demonstrativos: 3 vendas e R$ 163,00 conciliados',
    )
    _write('resultado-operacional-demo.pdf', 'Resultado Operacional', 'executive', ('statement', 'value'), [], RESULT_SUMMARY)
    _write('posicao-estoque-demo.pdf', 'Posição de Estoque', 'executive', ('product', 'current_quantity', 'minimum_quantity', 'unit', 'state'), STOCK_ROWS, STOCK_SUMMARY, {'as_of': '2026-10-13T11:40:00-03:00'})
    dashboard = {'sales': SALES_SUMMARY, 'inventory': STOCK_SUMMARY, 'commands': {'open_count': 4}}
    _write('dashboard-executivo-demo.pdf', 'Dashboard Executivo', 'executive', ('indicator', 'value'), report_key_value_rows(dashboard), dashboard)


if __name__ == '__main__':
    main()
