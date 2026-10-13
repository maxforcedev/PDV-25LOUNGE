"""Shared ReportLab presentation layer for authorized report exports.

This module deliberately receives serialized data only. Views remain responsible for
period rules, calculations, redaction and tenant/branch authorization.
"""
import html
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import Flowable, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .export_labels import export_label, export_value


PDF_MODES = ('executive', 'detailed')
CORE_BLUE = colors.HexColor('#3454D1')
CORE_DARK = colors.HexColor('#283C50')
CORE_MUTED = colors.HexColor('#64748B')
CORE_PALE = colors.HexColor('#F0F2F8')
CORE_BORDER = colors.HexColor('#E2E8F0')
CORE_SUCCESS = colors.HexColor('#17C666')
CORE_WARNING = colors.HexColor('#FFA21D')
CORE_DANGER = colors.HexColor('#EA4D4D')
CORE_LOGO = Path(__file__).parent / 'assets' / 'core-logo-compact-light.png'

# ``value`` is intentionally absent. A presentation column must retain the
# source key in ``__report_key`` instead of becoming currency by its own name.
CURRENCY_TERMS = (
    'amount', 'price', 'cost', 'revenue', 'received', 'payment', 'commission',
    'discount', 'fee', 'opening', 'expected', 'informed', 'difference', 'result',
    'impact', 'payable', 'charged', 'benefit', 'subsidy',
)
CURRENCY_KEYS = {
    'gross', 'total', 'ticket_average', 'average', 'margin', 'inventory_value',
    'historical_cost', 'historical_sales_cogs', 'historical_consumption_cogs',
    'operating_expenses', 'fixed_cost', 'applied_amount', 'received_amount',
    'change_amount', 'applied_total', 'received_total', 'change_total',
    'net_subtotal', 'subtotal', 'unit_price', 'average_unit_cost', 'last_unit_cost',
}
PERCENT_TERMS = ('percent', 'percentage', 'participation', 'rate')
PERCENT_KEYS = {'margin_percent', 'margin_percentage', 'commission_rate'}
QUANTITY_TERMS = ('count', 'quantity', 'uses', 'products', 'records', 'items')
ENTITY_NAME_KEYS = ('name', 'display_name', 'full_name', 'title', 'label', 'description')


def _decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _semantic_key(row, key):
    # Key/value summaries retain their origin in a private field. Applying that
    # origin to the indicator text would incorrectly format labels as numbers.
    if key == 'value':
        return str(row.get('__report_key') or row.get('semantic_key') or key)
    return str(key)


def _label(key):
    if '.' in str(key):
        return ' · '.join(_label(part) for part in str(key).split('.'))
    special = {
        'record': 'Registro',
        'indicator': 'Indicador',
        'hour': 'Horário',
        'day': 'Dia',
        'date': 'Data',
        'state': 'Situação',
        'ticket_average': 'Ticket médio',
        'total_discount': 'Descontos',
        'percentage': 'Percentual',
        'hourly_sales': 'Vendas por horário',
        'product_ranking': 'Produtos em destaque',
        'current_quantity': 'Saldo atual',
        'minimum_quantity': 'Estoque mínimo',
        'applied_amount': 'Valor aplicado',
        'received_amount': 'Valor recebido',
        'change_amount': 'Troco',
    }
    if key in special:
        return special[key]
    label = export_label(key)
    return label if label != key else str(key).replace('_', ' ').capitalize()


def _is_currency(key):
    key = str(key).casefold()
    if key in {'payment_method'} or key.endswith(('_name', '_code', '_id', '_status', '_type')):
        return False
    return (
        key in CURRENCY_KEYS
        or (any(term in key for term in CURRENCY_TERMS) and not key.endswith('_count'))
    )


def _is_percent(key):
    key = str(key).casefold()
    return key in PERCENT_KEYS or any(term in key for term in PERCENT_TERMS)


def _is_identifier(key):
    key = str(key).casefold()
    return key == 'id' or key.endswith(('_id', '_ids', '_number', '_code', '_reference'))


def _number(value, *, currency=False, percent=False):
    value = _decimal(value)
    if value is None:
        return 'Não disponível'
    if currency:
        text = f'{value:,.2f}'
    else:
        text = format(value.normalize(), 'f')
        if '.' in text:
            text = text.rstrip('0').rstrip('.')
        if text in ('', '-0'):
            text = '0'
        whole, dot, fraction = text.partition('.')
        negative = whole.startswith('-')
        whole = f'{abs(int(whole)):,}'
        if negative:
            whole = f'-{whole}'
        text = f'{whole}{dot}{fraction}' if dot else whole
    text = text.replace(',', '_').replace('.', ',').replace('_', '.')
    if percent:
        return f'{text}%'
    return f'R$ {text}' if currency else text


def _date_value(value, key):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return None
    if timezone.is_aware(parsed):
        parsed = timezone.localtime(parsed)
    return parsed.strftime('%d/%m/%Y às %H:%M' if str(key).endswith('_at') or 'datetime' in str(key) else '%d/%m/%Y')


def pdf_value(value, key='', *, row=None):
    """Format a scalar using its original semantic key, never a generic cell name."""
    if value is None or value == '':
        return 'Não disponível'
    source_key = _semantic_key(row or {}, key)
    if _is_identifier(source_key):
        return str(export_value(value))
    if isinstance(value, (datetime, date)) or source_key.endswith(('_at', '_date')) or source_key == 'as_of' or 'datetime' in source_key:
        formatted = _date_value(value, source_key)
        if formatted is not None:
            return formatted
    if isinstance(value, dict):
        for name_key in ENTITY_NAME_KEYS:
            if value.get(name_key) not in (None, '') and not isinstance(value[name_key], (dict, list, tuple)):
                return pdf_value(value[name_key], name_key)
        if value.get('id') not in (None, ''):
            return pdf_value(value['id'], 'id')
        return 'Não disponível'
    if isinstance(value, (list, tuple)):
        return 'Ver detalhamento'
    value = export_value(value)
    if source_key == 'state':
        return {
            'below_minimum': 'Abaixo do mínimo',
            'zero': 'Zerado',
            'negative': 'Saldo negativo',
            'normal': 'Normal',
            'archived_with_stock': 'Arquivado com saldo',
        }.get(str(value), str(value))
    if _is_percent(source_key):
        return _number(value, percent=True)
    if _is_currency(source_key):
        return _number(value, currency=True)
    if _decimal(value) is not None and (
        isinstance(value, Decimal) or any(term in source_key.casefold() for term in QUANTITY_TERMS)
    ):
        return _number(value)
    return str(value)


def period_label(period):
    if not isinstance(period, dict):
        return pdf_value(period)
    start = period.get('start_datetime') or period.get('start')
    end = period.get('end_datetime') or period.get('end')
    if start and end:
        return f'{pdf_value(start, "start_datetime")} a {pdf_value(end, "end_datetime")}'
    as_of = period.get('as_of')
    if as_of:
        return f'Posição em {pdf_value(as_of, "as_of")}'
    values = [f'{_label(key)}: {pdf_value(value, key)}' for key, value in period.items() if value]
    return ' · '.join(values) or 'Não disponível'


def _paragraph(value, style):
    return Paragraph(html.escape(str(value)).replace('\n', '<br/>'), style)


def _styles():
    source = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('CoreReportTitle', parent=source['Title'], fontName='Helvetica-Bold', fontSize=21, leading=25, textColor=CORE_DARK, spaceAfter=2),
        'subtitle': ParagraphStyle('CoreReportSubtitle', parent=source['Normal'], fontSize=9, leading=13, textColor=CORE_MUTED, spaceAfter=12),
        'section': ParagraphStyle('CoreReportSection', parent=source['Heading2'], fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=CORE_DARK, spaceBefore=15, spaceAfter=7, keepWithNext=True),
        'section_note': ParagraphStyle('CoreReportSectionNote', parent=source['Normal'], fontSize=8, leading=10, textColor=CORE_MUTED, alignment=2),
        'body': ParagraphStyle('CoreReportBody', parent=source['BodyText'], fontSize=8.6, leading=11.5, textColor=CORE_DARK, wordWrap='CJK', splitLongWords=1),
        'small': ParagraphStyle('CoreReportSmall', parent=source['BodyText'], fontSize=7.5, leading=9.5, textColor=CORE_DARK, wordWrap='CJK', splitLongWords=1),
        'right': ParagraphStyle('CoreReportRight', parent=source['BodyText'], fontSize=8.6, leading=11.5, textColor=CORE_DARK, alignment=2, wordWrap='CJK', splitLongWords=1),
        'table_header': ParagraphStyle('CoreReportTableHeader', parent=source['BodyText'], fontName='Helvetica-Bold', fontSize=7.5, leading=9, textColor=CORE_DARK),
        'card_label': ParagraphStyle('CoreReportCardLabel', parent=source['BodyText'], fontName='Helvetica-Bold', fontSize=7.2, leading=9, textColor=CORE_MUTED),
        'card_value': ParagraphStyle('CoreReportCardValue', parent=source['BodyText'], fontName='Helvetica-Bold', fontSize=15, leading=18, textColor=CORE_DARK),
        'card_note': ParagraphStyle('CoreReportCardNote', parent=source['BodyText'], fontSize=7.3, leading=9, textColor=CORE_MUTED),
    }


def _summary_scalars(summary):
    return [(key, value) for key, value in (summary or {}).items() if not isinstance(value, (dict, list))]


def _flatten_row(row, prefix=''):
    """Expand nested records only in detailed tables, retaining every leaf field."""
    flattened = {}
    for key, value in (row or {}).items():
        if str(key).startswith('__'):
            continue
        field = f'{prefix}.{key}' if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(_flatten_row(value, field))
        elif isinstance(value, (list, tuple)):
            flattened[field] = value
        else:
            flattened[field] = value
    return flattened


def _expanded_table_data(headers, rows):
    expanded_rows = [_flatten_row(row) for row in rows]
    expanded_headers = []
    for header in headers:
        matches = [key for row in expanded_rows for key in row if key == header or key.startswith(f'{header}.')]
        for key in matches or [header]:
            if key not in expanded_headers:
                expanded_headers.append(key)
    for row in expanded_rows:
        for key in row:
            if key not in expanded_headers and not isinstance(row[key], (list, tuple)):
                expanded_headers.append(key)
    return tuple(
        key for key in expanded_headers
        if not any(isinstance(row.get(key), (list, tuple)) for row in expanded_rows)
    ), expanded_rows


def _structured_sections(summary, prefix=''):
    sections = []
    for key, value in (summary or {}).items():
        title = f'{prefix}.{key}' if prefix else key
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            headers = tuple(dict.fromkeys(field for row in value for field in row if not field.startswith('__')))
            if headers:
                sections.append((title, headers, value))
        elif isinstance(value, (list, tuple)) and value:
            sections.append((title, ('value',), [{'value': item, '__report_key': key} for item in value]))
        elif isinstance(value, dict) and value:
            rows = [
                {'indicator': _label(item_key), 'value': item_value, '__report_key': item_key}
                for item_key, item_value in value.items() if not isinstance(item_value, (dict, list))
            ]
            if rows:
                sections.append((title, ('indicator', 'value'), rows))
            sections.extend(_structured_sections(value, title))
    return sections


def _profile(title, filename, summary):
    token = f'{title} {filename}'.casefold()
    if 'resultado operacional' in token or 'estimated_result' in (summary or {}):
        return 'result'
    if 'posição de estoque' in token or 'posicao-estoque' in token:
        return 'stock'
    if 'dashboard' in token:
        return 'dashboard'
    if 'venda' in token or {'gross', 'sales_revenue', 'product_ranking'} & set(summary or {}):
        return 'sales'
    if any(word in token for word in ('caixa', 'sangria', 'contas a pagar', 'recebimento')):
        return 'finance'
    if any(word in token for word in ('estoque', 'compra', 'fornecedor', 'inventário', 'inventario', 'preço', 'preco')):
        return 'inventory'
    if any(word in token for word in ('comanda', 'mesa', 'ticket', 'promo', 'modificador', 'cliente')):
        return 'operations'
    return 'general'


def _nested(summary, key):
    value = (summary or {}).get(key)
    return value if isinstance(value, dict) else {}


def _value_at(summary, *keys):
    for key in keys:
        if key in summary and summary[key] is not None:
            return key, summary[key]
    return None, None


def _metric(summary, label, *keys, note=''):
    key, value = _value_at(summary, *keys)
    return (label, key, value, note) if key is not None else None


def _metrics(kind, summary):
    if kind == 'dashboard':
        sales = _nested(summary, 'sales')
        inventory = _nested(summary, 'inventory')
        return [item for item in (
            _metric(sales, 'FATURAMENTO', 'sales_revenue', 'effective_revenue', note='Operação do período'),
            _metric(sales, 'VENDAS', 'count', 'inflow_count', note='Operações registradas'),
            _metric(sales, 'TICKET MÉDIO', 'ticket_average', 'average', note='Por venda'),
            _metric(inventory, 'ESTOQUE BAIXO', 'below_minimum_count', 'below_minimum', note='Abaixo do mínimo'),
        ) if item]
    if kind == 'sales':
        return [item for item in (
            _metric(summary, 'FATURAMENTO', 'sales_revenue', 'effective_revenue', 'revenue', note='Líquido de descontos'),
            _metric(summary, 'VENDAS', 'count', 'sales_count', 'inflow_count', note='Operações do período'),
            _metric(summary, 'TICKET MÉDIO', 'ticket_average', 'average', note='Por venda'),
            _metric(summary, 'DESCONTOS', 'total_discount', 'discount', 'discounts', note='Promoções + manuais'),
        ) if item]
    if kind == 'result':
        return [item for item in (
            _metric(summary, 'RECEITA EFETIVA', 'effective_revenue', 'sales_revenue', note='Operações do período'),
            _metric(summary, 'CUSTOS E DESPESAS', 'costs_and_expenses', note='Conforme dados disponíveis'),
            _metric(summary, 'RESULTADO ESTIMADO', 'estimated_result', 'result', note='Não substitui DRE contábil'),
        ) if item]
    if kind == 'stock':
        return [item for item in (
            _metric(summary, 'PRODUTOS', 'product_count', note='Cadastrados e ativos'),
            _metric(summary, 'ESTOQUE BAIXO', 'below_minimum', 'below_minimum_count', note='Abaixo do mínimo'),
            _metric(summary, 'ZERADOS', 'zero', 'zero_count', note='Precisam de atenção'),
            _metric(summary, 'SALDO NEGATIVO', 'negative', 'negative_count', note='Revisar movimentações'),
        ) if item]
    maps = {
        'finance': ('total_received', 'payment_total', 'count', 'difference', 'withdrawals', 'pending_total', 'paid_total'),
        'inventory': ('count', 'quantity', 'entries', 'exits', 'inventory_value', 'ordered_total', 'received_total'),
        'operations': ('count', 'quantity', 'uses', 'affected_quantity', 'customer_count', 'ticket_average'),
        'general': ('count', 'quantity', 'total', 'amount', 'value'),
    }
    chosen = []
    for key in maps[kind]:
        if key in summary and not isinstance(summary[key], (dict, list)):
            chosen.append((_label(key).upper(), key, summary[key], 'Indicador consolidado'))
        if len(chosen) == 4:
            break
    return chosen


def _metric_cards(document, metrics, styles):
    if not metrics:
        return None
    count = len(metrics)
    columns = 3 if count == 3 else 4 if count >= 4 else count
    cards = []
    for label, key, value, note in metrics:
        cards.append(Table([[_MetricCard(
            document.width / columns - 10, label, pdf_value(value, key), note,
            CORE_DANGER if 'negative' in key or key in ('difference', 'total_discount')
            else CORE_WARNING if key in ('below_minimum', 'zero', 'zero_count') else CORE_BLUE,
        )]], colWidths=[document.width / columns - 10], rowHeights=[_MetricCard.height], style=TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ])))
    while len(cards) % columns:
        cards.append('')
    return Table([cards[index:index + columns] for index in range(0, len(cards), columns)], colWidths=[document.width / columns] * columns, style=TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))


def _card_text(value, maximum=38):
    text = str(value).replace('\n', ' ')
    return f'{text[:maximum - 3]}...' if len(text) > maximum else text


class _MetricCard(Flowable):
    """Compact metric block matching the rounded, colored-side treatment in the approved layout."""

    height = 50

    def __init__(self, width, label, value, note, accent):
        super().__init__()
        self.width = width
        self.label = _card_text(label, 28)
        self.value = _card_text(value, 24)
        self.note = _card_text(note, 48)
        self.accent = accent

    def wrap(self, available_width, available_height):
        self.width = min(self.width, available_width)
        return self.width, self.height

    def draw(self):
        canvas_object = self.canv
        canvas_object.saveState()
        canvas_object.setFillColor(colors.white)
        canvas_object.setStrokeColor(CORE_BORDER)
        canvas_object.setLineWidth(.45)
        canvas_object.roundRect(0, 0, self.width, self.height, 5, fill=1, stroke=1)
        canvas_object.setFillColor(self.accent)
        canvas_object.roundRect(0, 0, 4, self.height, 2, fill=1, stroke=0)
        canvas_object.setFillColor(CORE_MUTED)
        canvas_object.setFont('Helvetica-Bold', 6.8)
        canvas_object.drawString(10, 38, self.label)
        canvas_object.setFillColor(CORE_DARK)
        canvas_object.setFont('Helvetica-Bold', 13.5)
        canvas_object.drawString(10, 21, self.value)
        canvas_object.setFillColor(CORE_MUTED)
        canvas_object.setFont('Helvetica', 6.7)
        canvas_object.drawString(10, 9, self.note)
        canvas_object.restoreState()


def _table_widths(document, headers, rows):
    weights = []
    for key in headers:
        sample = [len(_label(key))]
        for row in rows[:30]:
            sample.append(min(len(pdf_value(row.get(key), key, row=row)), 40))
        numeric = _is_currency(key) or _is_percent(key) or any(term in key.casefold() for term in QUANTITY_TERMS)
        weights.append(max(1.1 if numeric else 1.6, min(max(sample) / 11, 4.8)))
    total = sum(weights) or 1
    return [document.width * weight / total for weight in weights]


def report_table(document, headers, rows, styles, *, status_column=None, emphasize_last=False):
    if not headers:
        return None
    content = [[_paragraph(_label(key).upper(), styles['table_header']) for key in headers]]
    numeric = {
        index for index, key in enumerate(headers)
        if _is_currency(key) or _is_percent(key) or any(term in key.casefold() for term in QUANTITY_TERMS)
    }
    for row in rows:
        content.append([
            _paragraph(pdf_value(row.get(key), key, row=row), styles['right'] if index in numeric else styles['body'])
            for index, key in enumerate(headers)
        ])
    table = LongTable(content, colWidths=_table_widths(document, headers, rows), repeatRows=1, splitByRow=1, splitInRow=1, hAlign='LEFT')
    commands = [
        ('BACKGROUND', (0, 0), (-1, 0), CORE_PALE),
        ('LINEBELOW', (0, 0), (-1, 0), .65, CORE_BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FAFBFE')]),
        ('LINEBELOW', (0, 1), (-1, -1), .25, CORE_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    if emphasize_last and len(content) > 1:
        commands.extend([('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E8EEFF')), ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold')])
    if status_column is not None:
        index = headers.index(status_column)
        for row_number, row in enumerate(rows, 1):
            state = str(row.get(status_column, '')).casefold()
            if state in ('negative', 'saldo negativo'):
                commands.append(('TEXTCOLOR', (index, row_number), (index, row_number), CORE_DANGER))
            elif state in ('zero', 'zerado', 'below_minimum', 'abaixo do mínimo'):
                commands.append(('TEXTCOLOR', (index, row_number), (index, row_number), CORE_WARNING))
    table.setStyle(TableStyle(commands))
    return table


def _section_heading(story, title, styles, note=None):
    if note:
        story.append(Table([[_paragraph(title, styles['section']), _paragraph(note, styles['section_note'])]], colWidths=[None, 3.2 * cm], style=TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ])))
    else:
        story.append(_paragraph(title, styles['section']))


def _bar_chart(values, *, width, title_key, value_key, max_items=7, colorset=None, percent_key=None):
    values = values[:max_items]
    if not values:
        return None
    height = 98
    drawing = Drawing(width, height)
    amounts = [_decimal(item.get(value_key)) or Decimal('0') for item in values]
    maximum = max(amounts) or Decimal('1')
    label_width = min(width * .3, 116)
    value_width = min(width * .36, 92)
    chart_width = max(width - label_width - value_width - 8, 24)
    row_height = (height - 10) / len(values)
    palette = colorset or (CORE_BLUE, colors.HexColor('#6D83E4'), colors.HexColor('#AAB8F2'))
    for index, (item, amount) in enumerate(zip(values, amounts)):
        y = height - (index + 1) * row_height + 3
        label = pdf_value(item.get(title_key) or item.get('name') or item.get('product_name') or 'Não informado', title_key, row=item)[:24]
        drawing.add(String(0, y + 3, label, fontName='Helvetica', fontSize=7.4, fillColor=CORE_DARK))
        drawing.add(Rect(label_width, y, chart_width, 8, fillColor=CORE_PALE, strokeColor=None))
        drawing.add(Rect(label_width, y, float(Decimal(str(chart_width)) * amount / maximum), 8, fillColor=palette[index % len(palette)], strokeColor=None))
        text = pdf_value(item.get(value_key), value_key, row=item)
        if percent_key and item.get(percent_key) is not None:
            text = f'{text} · {pdf_value(item.get(percent_key), percent_key, row=item)}'
        drawing.add(String(width - 1, y + 2, text, textAnchor='end', fontName='Helvetica-Bold', fontSize=6.5, fillColor=CORE_DARK))
    return drawing


def _chart_value_key(values):
    return next(
        (key for key in ('sales_revenue', 'effective_revenue', 'total_received', 'payment_total', 'count')
         if any(row.get(key) is not None for row in values)),
        'count',
    )


def _timeline_label(value, key, index):
    if value in (None, ''):
        return str(index + 1)
    text = str(value)
    if key == 'hour':
        try:
            parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            parsed = None
        if parsed is not None:
            if timezone.is_aware(parsed):
                parsed = timezone.localtime(parsed)
            return parsed.strftime('%H:%M')
        if text.isdigit():
            return f'{int(text):02d}h'
        return text[:5] if ':' in text else text[:9]
    formatted = _date_value(value, key)
    if formatted:
        return formatted[:5] if key in ('date', 'day') else formatted
    return text[:9]


def _timeline_chart(values, width, previous=None):
    values = values[-7:]
    if not values:
        return None
    previous = (previous or [])[-len(values):]
    value_key = _chart_value_key(values + previous)
    label_key = next((key for key in ('date', 'day', 'hour') if any(key in row for row in values)), 'day')
    height = 134
    drawing = Drawing(width, height)
    amounts = [_decimal(row.get(value_key)) or Decimal('0') for row in values]
    previous_amounts = [_decimal(row.get(value_key)) or Decimal('0') for row in previous]
    maximum = max(amounts + previous_amounts) or Decimal('1')
    chart_height, left, bottom = 76, 15, 29
    drawing.add(Line(left, bottom, width - 8, bottom, strokeColor=CORE_BORDER, strokeWidth=.6))
    if previous:
        drawing.add(Rect(width - 104, 118, 7, 7, fillColor=CORE_BLUE, strokeColor=None))
        drawing.add(String(width - 94, 118, 'Atual', fontName='Helvetica', fontSize=6.8, fillColor=CORE_MUTED))
        drawing.add(Rect(width - 55, 118, 7, 7, fillColor=colors.HexColor('#AAB8F2'), strokeColor=None))
        drawing.add(String(width - 45, 118, 'Anterior', fontName='Helvetica', fontSize=6.8, fillColor=CORE_MUTED))
    gap = (width - left - 12) / max(len(values), 1)
    for index, (row, amount) in enumerate(zip(values, amounts)):
        bar_width = min(18, gap * (.3 if previous else .55))
        x = left + index * gap + (gap - bar_width * (2 if previous else 1)) / 2
        if previous and index < len(previous_amounts):
            previous_height = float(Decimal(str(chart_height)) * previous_amounts[index] / maximum)
            drawing.add(Rect(x, bottom, bar_width, previous_height, fillColor=colors.HexColor('#AAB8F2'), strokeColor=None))
            x += bar_width + 2
        bar_height = float(Decimal(str(chart_height)) * amount / maximum)
        drawing.add(Rect(x, bottom, bar_width, bar_height, fillColor=CORE_BLUE, strokeColor=None))
        drawing.add(String(x + bar_width / 2, bottom + bar_height + 4, pdf_value(row.get(value_key), value_key, row=row), textAnchor='middle', fontName='Helvetica-Bold', fontSize=5.7, fillColor=CORE_DARK))
        label = _timeline_label(row.get(label_key), label_key, index)
        drawing.add(String(x + bar_width / 2, 11, label, textAnchor='middle', fontName='Helvetica', fontSize=6.8, fillColor=CORE_MUTED))
    return drawing


def _financial_statement(document, summary, styles, kind, width=None):
    if kind == 'sales':
        items = (
            ('Valor bruto', 'gross'), ('Descontos', 'total_discount'), ('Faturamento final', 'sales_revenue'),
            ('Taxa de serviço', 'service_fee'), ('Total recebido', 'total_received'),
        )
    elif kind == 'result':
        items = (
            ('Faturamento efetivo', 'effective_revenue'), ('CMV histórico / mercadorias', 'historical_sales_cogs'),
            ('Comissões e taxas', 'commission'), ('Despesas operacionais', 'operating_expenses'),
            ('Custos e despesas', 'costs_and_expenses'), ('Resultado operacional estimado', 'estimated_result'),
        )
    else:
        items = tuple((export_label(key), key) for key, _ in _summary_scalars(summary)[:6])
    rows = []
    for label, key in items:
        if key in summary and summary[key] is not None:
            value = pdf_value(summary[key], key)
            if key in ('total_discount', 'historical_sales_cogs', 'commission', 'operating_expenses', 'costs_and_expenses') and not value.startswith('-'):
                value = f'- {value}'
            rows.append([_paragraph(label, styles['body']), _paragraph(value, styles['right'])])
    if not rows:
        return None
    width = width or document.width
    return Table(rows, colWidths=[width * .62, width * .38], style=TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), .3, CORE_BORDER), ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5), ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E8EEFF')), ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))


def _payment_rows(summary):
    for key in ('payment_totals', 'payment_distribution', 'payment_methods'):
        value = summary.get(key)
        if isinstance(value, list):
            return value
    return []


def _ranking_rows(summary):
    for key in ('product_ranking', 'top_products', 'category_ranking', 'top_categories', 'seller_groups', 'operator_groups'):
        value = summary.get(key)
        if isinstance(value, list) and value:
            return key, value
    return None, []


def _stock_attention(rows):
    return [row for row in rows if str(row.get('state', '')).casefold() in ('negative', 'zero', 'below_minimum')]


def _executive_story(story, document, styles, kind, summary, rows):
    if not summary:
        _section_heading(story, 'Sem dados consolidados', styles)
        story.append(_paragraph(
            'Não há indicadores autorizados para os filtros selecionados. O relatório executivo não inclui automaticamente registros individuais; use o modo detalhado para conferência.',
            styles['body'],
        ))
        return
    metrics = _metrics(kind, summary)
    cards = _metric_cards(document, metrics, styles)
    if cards:
        _section_heading(story, 'Visão de resultado' if kind == 'result' else 'Indicadores do período' if kind in ('sales', 'dashboard') else 'Estoque da filial' if kind == 'stock' else 'Indicadores consolidados', styles, 'Dados consolidados' if kind != 'stock' else 'Saldo atual')
        story.extend([cards, Spacer(1, 5)])
    if kind in ('sales', 'dashboard'):
        sales = _nested(summary, 'sales') if kind == 'dashboard' else summary
        statement = _financial_statement(document, sales, styles, 'sales', document.width * .52)
        payments = _payment_rows(sales)
        if statement or payments:
            _section_heading(story, 'Composição financeira', styles)
            left = [statement] if statement else [_paragraph('Sem composição financeira autorizada.', styles['body'])]
            right = [_paragraph('Recebimentos por forma', styles['body'])]
            payment_value = next((key for key in ('payment_total', 'received_total', 'applied_total', 'amount') if any(key in row for row in payments)), 'amount')
            chart = _bar_chart(
                payments, width=document.width * .40, title_key='name', value_key=payment_value,
                percent_key='percentage' if any('percentage' in row for row in payments) else None,
            ) if payments else None
            right.append(chart or _paragraph('Sem distribuição disponível.', styles['body']))
            story.append(Table([[left, right]], colWidths=[document.width * .55, document.width * .45], style=TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ])))
        weekly_comparison = _nested(sales, 'weekly_comparison')
        timeline_key = 'hourly_sales' if sales.get('hourly_sales') else 'weekly_comparison'
        timeline = sales.get('hourly_sales') or weekly_comparison.get('current')
        if isinstance(timeline, list) and timeline:
            has_comparison = isinstance(weekly_comparison.get('previous'), list) and weekly_comparison['previous']
            _section_heading(
                story, 'Vendas por horário' if timeline_key == 'hourly_sales' else 'Evolução de vendas', styles,
                'Atual e período anterior' if has_comparison else 'Horários registrados no período' if timeline_key == 'hourly_sales' else 'Dias registrados no período',
            )
            story.append(_timeline_chart(timeline, document.width, weekly_comparison.get('previous')))
        ranking_key, ranking = _ranking_rows(sales)
        if ranking:
            _section_heading(story, 'Produtos em destaque' if 'product' in ranking_key else _label(ranking_key), styles)
            value_key = 'quantity' if any('quantity' in row for row in ranking) else 'sales_revenue'
            story.append(_bar_chart(ranking, width=document.width, title_key='product_name' if 'product' in ranking_key else 'name', value_key=value_key, max_items=5))
        return
    if kind == 'result':
        statement = _financial_statement(document, summary, styles, kind)
        if statement:
            _section_heading(story, 'Composição do resultado', styles)
            story.append(statement)
        if 'margin' in summary or 'notice' in summary:
            _section_heading(story, 'Leitura gerencial', styles)
            margin = pdf_value(summary.get('margin'), 'margin_percent') if 'margin' in summary else 'Não disponível'
            notice = str(summary.get('notice') or 'Estimativa gerencial baseada nos dados autorizados. Não substitui demonstração contábil.')
            story.append(Table([[
                [_paragraph('MARGEM ESTIMADA', styles['card_label']), _paragraph(margin, styles['card_value'])],
                [_paragraph(notice, styles['body'])],
            ]], colWidths=[document.width * .3, document.width * .7], style=TableStyle([
                ('BACKGROUND', (0, 0), (0, 0), CORE_PALE), ('BOX', (0, 0), (-1, -1), .4, CORE_BORDER),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 11), ('BOTTOMPADDING', (0, 0), (-1, -1), 11),
                ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ])))
        return
    if kind == 'stock':
        attention = _stock_attention(rows)
        if attention:
            _section_heading(story, 'Produtos que precisam de atenção', styles, 'Prioridades da filial')
            headers = tuple(key for key in ('product', 'current_quantity', 'minimum_quantity', 'unit', 'state') if any(key in row for row in attention))
            story.append(report_table(document, headers, attention, styles, status_column='state' if 'state' in headers else None))
        _section_heading(story, 'Nota de gestão', styles)
        story.append(_paragraph('Verifique itens críticos e planeje reposições conforme os movimentos registrados.', styles['body']))
        return
    ranking_key, ranking = _ranking_rows(summary)
    if ranking:
        _section_heading(story, _label(ranking_key), styles)
        value_key = next((key for key in ('amount', 'sales_revenue', 'net_revenue', 'quantity', 'count') if any(key in row for row in ranking)), 'count')
        name_key = next((key for key in ('name', 'product_name', 'category_name', 'supplier_name') if any(key in row for row in ranking)), 'name')
        story.append(_bar_chart(ranking, width=document.width, title_key=name_key, value_key=value_key, max_items=6))
    elif rows:
        _section_heading(story, 'Leitura operacional', styles)
        story.append(_paragraph('Consulte o PDF detalhado para os registros autorizados do período.', styles['body']))


def _related_details(story, document, styles, rows):
    """Keep every nested child field in consolidated, relationship-preserving tables."""
    grouped = {}

    def collect(row, identity, prefix=''):
        for key, values in row.items():
            if str(key).startswith('__'):
                continue
            section_key = f'{prefix}.{key}' if prefix else key
            if isinstance(values, dict):
                collect(values, identity, section_key)
            elif isinstance(values, (list, tuple)) and values:
                grouped.setdefault(section_key, [])
                if all(isinstance(item, dict) for item in values):
                    children = [{'record': identity, **item} for item in values]
                    grouped[section_key].extend(children)
                    for child in children:
                        collect(child, identity, section_key)
                else:
                    grouped[section_key].extend(
                        {'record': identity, 'value': item, '__report_key': key}
                        for item in values
                    )

    for row in rows:
        identity = row.get('sale_number') or row.get('operation_id') or row.get('id') or 'Registro'
        collect(row, identity)
    for key, values in grouped.items():
        headers = ('record',) + tuple(dict.fromkeys(
            field for item in values for field in item if not field.startswith('__') and field != 'record'
        ))
        headers, values = _expanded_table_data(headers, values)
        _section_heading(story, f'{_label(key)} por registro', styles)
        story.append(report_table(document, headers, values, styles))
    return bool(grouped)


def _detailed_story(story, document, styles, summary, headers, rows):
    metrics = _metrics(_profile('', '', summary), summary)[:4]
    cards = _metric_cards(document, metrics, styles)
    if cards:
        _section_heading(story, 'Resumo e conferência', styles)
        story.append(cards)
    scalars = _summary_scalars(summary)
    if scalars:
        _section_heading(story, 'Resumo consolidado', styles)
        summary_rows = [{'indicator': _label(key), 'value': value, '__report_key': key} for key, value in scalars]
        story.append(report_table(document, ('indicator', 'value'), summary_rows, styles))
    # Detailed exports retain every authorized aggregate rather than applying the
    # executive editorial limits.
    for key, section_headers, section_rows in _structured_sections(summary):
        section_headers, section_rows = _expanded_table_data(section_headers, section_rows)
        _section_heading(story, _label(key), styles)
        story.append(report_table(document, section_headers, section_rows, styles))
    _section_heading(story, 'Movimentações individualizadas', styles, 'Registros autorizados')
    visible_headers = tuple(key for key in headers if not any(isinstance(row.get(key), (list, tuple)) for row in rows))
    visible_headers, visible_rows = _expanded_table_data(visible_headers, rows)
    if rows and visible_headers:
        story.append(report_table(document, visible_headers, visible_rows, styles))
    elif not rows:
        story.append(_paragraph('Sem registros para os filtros selecionados.', styles['body']))
    _related_details(story, document, styles, rows)


class _ReportCanvas(canvas.Canvas):
    def __init__(self, *args, footer='', **kwargs):
        super().__init__(*args, **kwargs)
        self._footer = footer
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.setStrokeColor(CORE_BORDER)
            self.setLineWidth(.35)
            self.line(1.5 * cm, 1.12 * cm, self._pagesize[0] - 1.5 * cm, 1.12 * cm)
            self.setFont('Helvetica', 7.3)
            self.setFillColor(CORE_MUTED)
            self.drawString(1.5 * cm, .7 * cm, self._footer)
            self.drawRightString(self._pagesize[0] - 1.5 * cm, .7 * cm, f'Página {self._pageNumber} de {page_count}')
            super().showPage()
        super().save()


def _header(company, branch, mode):
    def decorate(page, document):
        width, height = document.pagesize
        page.saveState()
        page.setFillColor(CORE_BLUE)
        page.rect(0, height - .18 * cm, width, .18 * cm, fill=1, stroke=0)
        x = 1.5 * cm
        if CORE_LOGO.is_file():
            # This compact official mark already contains the wordmark and slogan.
            page.drawImage(str(CORE_LOGO), x, height - 1.48 * cm, width=1.08 * cm, height=1.08 * cm, mask='auto', preserveAspectRatio=True, anchor='c')
            x += 1.25 * cm
        page.setFillColor(CORE_DARK)
        page.setFont('Helvetica-Bold', 8.2)
        page.drawString(x, height - .78 * cm, company)
        page.setFont('Helvetica-Bold', 7.2)
        page.setFillColor(CORE_MUTED)
        page.drawString(x, height - 1.06 * cm, branch)
        page.drawRightString(width - 1.5 * cm, height - .8 * cm, mode.upper())
        page.setStrokeColor(CORE_BORDER)
        page.setLineWidth(.35)
        page.line(1.5 * cm, height - 1.58 * cm, width - 1.5 * cm, height - 1.58 * cm)
        page.restoreState()
    return decorate


def _metadata(document, styles, company, branch, period, generated_at, filters):
    data = [
        [_paragraph('EMPRESA', styles['card_label']), _paragraph('FILIAL', styles['card_label'])],
        [_paragraph(company, styles['body']), _paragraph(branch, styles['body'])],
        [_paragraph('PERÍODO', styles['card_label']), _paragraph('GERADO EM', styles['card_label'])],
        [_paragraph(period_label(period), styles['body']), _paragraph(generated_at, styles['body'])],
    ]
    blocks = [Table(data, colWidths=[document.width / 2] * 2, style=TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white), ('BOX', (0, 0), (-1, -1), .4, CORE_BORDER),
        ('INNERGRID', (0, 0), (-1, -1), .25, CORE_BORDER), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))]
    if filters and filters != 'Sem filtros adicionais':
        blocks.extend([Spacer(1, 5), _paragraph(f'FILTROS APLICADOS · {filters}', styles['small'])])
    return blocks


def _needs_landscape(headers, rows):
    if len(headers) > 6:
        return True
    return len(headers) > 4 and sum(len(export_label(key)) for key in headers) > 70


def render_pdf_export(request, *, filename, title, headers, rows, period=None, summary=None, filters=''):
    mode = request.query_params.get('pdf_mode', 'executive')
    if mode not in PDF_MODES:
        raise ValidationError({'pdf_mode': 'Informe "executive" ou "detailed".'})
    summary = summary or {}
    rows = list(rows)
    headers = tuple(headers)
    page_size = landscape(A4) if mode == 'detailed' and _needs_landscape(headers, rows) else portrait(A4)
    output = io.BytesIO()
    company = request.branch_context.company.trade_name or request.branch_context.company.legal_name
    branch = request.branch_context.name
    generated_at = timezone.localtime().strftime('%d/%m/%Y às %H:%M')
    mode_label = 'Relatório detalhado' if mode == 'detailed' else 'Resumo executivo'
    document = SimpleDocTemplate(output, pagesize=page_size, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=2.15 * cm, bottomMargin=1.55 * cm, title=title, author='CORE PDV', allowSplitting=1)
    styles = _styles()
    kind = _profile(title, filename, summary)
    subtitle = {
        'sales': 'Resumo executivo · Indicadores e desempenho da operação',
        'result': 'Resumo executivo · Acompanhamento gerencial estimado',
        'stock': 'Resumo executivo · Saldo atual e atenção operacional',
        'dashboard': 'Resumo executivo · Indicadores autorizados da operação',
    }.get(kind, f'{mode_label} · Informações autorizadas para o período selecionado')
    if mode == 'detailed':
        subtitle = 'Analítico · Registros para conferência e auditoria'
    story = [_paragraph(title, styles['title']), _paragraph(subtitle, styles['subtitle'])]
    story.extend(_metadata(document, styles, company, branch, period, generated_at, filters))
    if mode == 'executive':
        _executive_story(story, document, styles, kind, summary, rows)
    else:
        _detailed_story(story, document, styles, summary, headers, rows)
    footer = f'CORE PDV · {mode_label} · Gerado em {generated_at}'
    document.build(story, onFirstPage=_header(company, branch, mode_label), onLaterPages=_header(company, branch, mode_label), canvasmaker=lambda *args, **kwargs: _ReportCanvas(*args, footer=footer, **kwargs))
    response = HttpResponse(output.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
