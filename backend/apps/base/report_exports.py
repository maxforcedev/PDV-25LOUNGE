import csv
import html
import io
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from uuid import UUID

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .export_labels import export_label, export_value
from .report_pdf import render_pdf_export

FORMULA_PREFIXES = ('=', '+', '-', '@')
CURRENCY_FIELDS = (
    'amount', 'price', 'cost', 'revenue', 'received', 'ordered_total', 'payment',
    'commission', 'discount', 'fee', 'opening', 'expected', 'informed', 'difference', 'result',
    'gross', 'average',
)
PDF_MODES = ('executive', 'detailed')
PDF_SECTION_KEYS = {
    'payment_totals', 'payment_methods', 'payment_distribution', 'product_ranking',
    'category_ranking', 'top_products', 'top_categories', 'top_sellers', 'top_operators',
    'seller_groups', 'operator_groups', 'hourly_sales', 'weekly_comparison', 'event_accounting',
    'movement_types', 'movement_groups', 'category_groups', 'status_groups', 'cash_registers',
    'withdrawals_by_category', 'suppliers', 'purchase_statuses', 'inventory_statuses',
    'transfer_statuses', 'ticket_statuses', 'promotions', 'modifiers',
}
PDF_INDICATOR_PRIORITY = (
    'gross', 'gross_revenue', 'sales_revenue', 'effective_revenue', 'revenue', 'total_received',
    'payment_total', 'count', 'sales_count', 'ticket_average', 'average', 'total_discount',
    'discount', 'service_fee', 'cancellation_count', 'cancellation_value', 'estimated_result',
    'result', 'margin', 'costs_and_expenses', 'quantity', 'movement_count', 'difference',
)
CORE_BLUE = colors.HexColor('#3454D1')
CORE_DARK_BLUE = colors.HexColor('#2945B6')
CORE_TEXT = colors.HexColor('#283C50')
CORE_MUTED = colors.HexColor('#64748B')
CORE_PALE = colors.HexColor('#F0F2F8')
CORE_BORDER = colors.HexColor('#E2E8F0')
CORE_SUCCESS = colors.HexColor('#17C666')
CORE_WARNING = colors.HexColor('#FFA21D')
CORE_DANGER = colors.HexColor('#EA4D4D')
CORE_LOGO = Path(__file__).parent / 'assets' / 'core-logo-compact-light.png'


def _value(value):
    value = export_value(value)
    return json.dumps(
        _json_value(value), ensure_ascii=False, separators=(',', ':'),
    ) if isinstance(value, (dict, list, tuple)) else value


def _json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return str(value)


def _csv_value(value):
    value = _value(value)
    if value is None:
        return ''
    value = str(value)
    if value.startswith(FORMULA_PREFIXES):
        try:
            Decimal(value)
        except InvalidOperation:
            value = "'" + value
    return value


def _text(value):
    return _csv_value(value)


def _paragraph(value, style):
    return Paragraph(html.escape(str(value)).replace('\n', '<br/>'), style)


def _company_name(branch):
    company = branch.company
    return company.trade_name or company.legal_name


def _typed_value(key, value):
    value = _value(value)
    if isinstance(value, datetime):
        return timezone.localtime(value).replace(tzinfo=None) if timezone.is_aware(value) else value
    if value is None or not isinstance(value, str):
        return value
    if key.endswith(('_at', '_date')):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return timezone.localtime(parsed).replace(tzinfo=None) if timezone.is_aware(parsed) else parsed
        except ValueError:
            return value
    if any(part in key.casefold() for part in CURRENCY_FIELDS):
        try:
            return Decimal(value)
        except InvalidOperation:
            pass
    if 'percent' in key.casefold() or 'percentage' in key.casefold():
        try:
            return Decimal(value) / Decimal('100')
        except InvalidOperation:
            pass
    return _csv_value(value)


def _filters(request):
    ignored = {'export', 'pdf_mode', 'branch', 'page', 'page_size', 'start_datetime', 'end_datetime'}
    return ', '.join(
        f'{export_label(key)}: {_text(value)}'
        for key, value in request.query_params.items() if key not in ignored and value
    ) or 'Sem filtros adicionais'


def _summary_rows(summary):
    return [
        (key, export_label(key), value)
        for key, value in (summary or {}).items()
        if not isinstance(value, (dict, list))
    ]


def _structured_sections(summary):
    sections = []
    for key, value in (summary or {}).items():
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            headers = []
            for item in value:
                for item_key in item:
                    if item_key not in headers:
                        headers.append(item_key)
            if headers:
                sections.append((key, tuple(headers), value))
        elif isinstance(value, list) and value:
            sections.append((key, ('value',), [{'value': item} for item in value]))
        elif isinstance(value, dict):
            section_rows = report_key_value_rows(value, export_label(key))
            if section_rows:
                sections.append((key, ('indicator', 'value'), section_rows))
    return sections


def _sheet_title(workbook, value):
    base = ''.join(character for character in export_label(value) if character not in r'[]:*?/\\')[:31] or 'Seção'
    title = base
    suffix = 2
    while title in workbook.sheetnames:
        ending = f' {suffix}'
        title = f'{base[:31 - len(ending)]}{ending}'
        suffix += 1
    return title


def _write_sheet_table(sheet, headers, rows):
    labels = [export_label(key) for key in headers]
    sheet.append(labels)
    for row in rows:
        sheet.append([_typed_value(key, row.get(key)) for key in headers])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='3454D1')
    if headers:
        sheet.auto_filter.ref = f'A1:{get_column_letter(len(headers))}{sheet.max_row}'
        sheet.freeze_panes = 'A2'
    for column, key in enumerate(headers, 1):
        values = [len(labels[column - 1]), 10]
        values.extend(len(_csv_value(row.get(key))) for row in rows)
        sheet.column_dimensions[get_column_letter(column)].width = min(max(values) + 2, 45)
        for cells in sheet.iter_cols(min_col=column, max_col=column, min_row=2):
            for cell in cells:
                if isinstance(cell.value, Decimal):
                    cell.number_format = (
                        '0.00%'
                        if 'percent' in key.casefold() or 'percentage' in key.casefold()
                        else 'R$ #,##0.00'
                        if any(part in key.casefold() for part in CURRENCY_FIELDS)
                        else '#,##0.000'
                    )
                elif isinstance(cell.value, datetime):
                    cell.number_format = 'dd/mm/yyyy hh:mm'
                elif isinstance(cell.value, date):
                    cell.number_format = 'dd/mm/yyyy'
                cell.alignment = Alignment(vertical='top', wrap_text=True)


def report_key_value_rows(data, prefix=''):
    """Flatten an already prepared response without interpreting its values."""
    rows = []
    for key, value in data.items():
        label = f'{prefix} {export_label(key)}'.strip()
        if isinstance(value, dict):
            rows.extend(report_key_value_rows(value, label))
        else:
            # Keep the leaf key so presentation can distinguish a count from a
            # monetary amount after this generic two-column representation.
            rows.append({'indicator': label, 'value': value, '__report_key': key})
    return rows


def _pdf_mode(request):
    mode = request.query_params.get('pdf_mode', 'executive')
    if mode not in PDF_MODES:
        raise ValidationError({'pdf_mode': 'Informe "executive" ou "detailed".'})
    return mode


def _decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _format_number(value, *, currency=False, percent=False, places=2):
    value = _decimal(value)
    if value is None:
        return 'Não disponível'
    result = f'{value:,.{places}f}'.replace(',', '_').replace('.', ',').replace('_', '.')
    if percent:
        return f'{result}%'
    return f'R$ {result}' if currency else result


def _format_datetime(value, key):
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
    return parsed.strftime('%d/%m/%Y às %H:%M' if key.endswith('_at') or 'datetime' in key else '%d/%m/%Y')


def _pdf_value(value, key=''):
    if value is None or value == '':
        return 'Não disponível'
    if isinstance(value, (dict, list, tuple)):
        if isinstance(value, dict):
            return '\n'.join(
                f'{export_label(item_key)}: {_pdf_value(item_value, str(item_key))}'
                for item_key, item_value in value.items()
            ) or 'Não disponível'
        return '\n'.join(
            _pdf_value(item, key) if not isinstance(item, dict) else
            ' · '.join(f'{export_label(item_key)}: {_pdf_value(item_value, str(item_key))}' for item_key, item_value in item.items())
            for item in value
        ) or 'Não disponível'
    value = export_value(value)
    normalized_key = str(key).casefold()
    if isinstance(value, (datetime, date)) or normalized_key.endswith(('_at', '_date')) or 'datetime' in normalized_key:
        formatted = _format_datetime(value, normalized_key)
        if formatted is not None:
            return formatted
    if 'percent' in normalized_key or 'percentage' in normalized_key or normalized_key in {'margin'}:
        return _format_number(value, percent=True)
    if any(part in normalized_key for part in CURRENCY_FIELDS):
        return _format_number(value, currency=True)
    if isinstance(value, Decimal):
        return _format_number(value, places=3 if 'quantity' in normalized_key else 2)
    return str(value)


def _period_label(period):
    if not isinstance(period, dict):
        return _pdf_value(period)
    start = period.get('start_datetime') or period.get('start')
    end = period.get('end_datetime') or period.get('end')
    if start and end:
        return f'{_pdf_value(start, "start_datetime")} a {_pdf_value(end, "end_datetime")}'
    return ' · '.join(
        f'{export_label(key)}: {_pdf_value(value, key)}' for key, value in period.items()
    ) or 'Não disponível'


def _pdf_summary_rows(summary, mode):
    rows = _summary_rows(summary)
    if mode == 'detailed':
        return rows
    priority = {key: index for index, key in enumerate(PDF_INDICATOR_PRIORITY)}
    ordered = sorted(rows, key=lambda row: priority.get(row[0], len(priority)))
    return ordered[:8]


def _pdf_sections(summary):
    return [
        section for section in _structured_sections(summary)
        if section[0] in PDF_SECTION_KEYS
    ]


def _column_widths(document, headers, rows):
    sample = rows[:30]
    weights = []
    for key, label in zip(headers, (export_label(header) for header in headers)):
        longest = max([len(str(label))] + [min(len(_pdf_value(row.get(key), key)), 48) for row in sample])
        numeric = any(part in str(key).casefold() for part in CURRENCY_FIELDS) or str(key).casefold() in {'count', 'quantity'}
        weights.append(max(1.1 if numeric else 1.6, min(longest / 12, 4.5)))
    total = sum(weights) or 1
    return [document.width * weight / total for weight in weights]


def _needs_landscape(headers, rows):
    if len(headers) > 6:
        return True
    sample = rows[:20]
    estimated_width = sum(
        max(len(export_label(key)), *(min(len(_pdf_value(row.get(key), key)), 36) for row in sample))
        for key in headers
    )
    return len(headers) > 4 and estimated_width > 100


def _pdf_styles():
    styles = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('ReportTitle', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=20, leading=24, textColor=CORE_TEXT, spaceAfter=3),
        'subtitle': ParagraphStyle('ReportSubtitle', parent=styles['Normal'], fontSize=9, leading=13, textColor=CORE_MUTED, spaceAfter=10),
        'section': ParagraphStyle('ReportSection', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=CORE_TEXT, spaceBefore=14, spaceAfter=6, keepWithNext=True),
        'body': ParagraphStyle('ReportBody', parent=styles['BodyText'], fontSize=8.5, leading=11, textColor=CORE_TEXT, wordWrap='CJK', splitLongWords=1),
        'small': ParagraphStyle('ReportSmall', parent=styles['BodyText'], fontSize=7.5, leading=9.5, textColor=CORE_TEXT, wordWrap='CJK', splitLongWords=1),
        'header': ParagraphStyle('ReportHeader', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white, wordWrap='CJK'),
        'right': ParagraphStyle('ReportRight', parent=styles['BodyText'], fontSize=8.5, leading=11, textColor=CORE_TEXT, alignment=2, wordWrap='CJK', splitLongWords=1),
        'card_label': ParagraphStyle('ReportCardLabel', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=7, leading=9, textColor=CORE_MUTED),
        'card_value': ParagraphStyle('ReportCardValue', parent=styles['BodyText'], fontName='Helvetica-Bold', fontSize=12, leading=15, textColor=CORE_TEXT),
    }


def _report_table(document, headers, rows, styles, *, emphasize_total=False):
    if not headers:
        return None
    numeric_columns = {
        index for index, key in enumerate(headers)
        if any(part in str(key).casefold() for part in CURRENCY_FIELDS)
        or str(key).casefold() in {'count', 'quantity', 'percentage', 'margin'}
    }
    body_style = styles['small'] if len(headers) > 5 else styles['body']
    content = [[_paragraph(export_label(key), styles['header']) for key in headers]]
    content.extend([
        [_paragraph(_pdf_value(row.get(key), key), styles['right'] if index in numeric_columns else body_style)
         for index, key in enumerate(headers)]
        for row in rows
    ])
    table = LongTable(
        content, colWidths=_column_widths(document, headers, rows), repeatRows=1,
        splitByRow=1, splitInRow=1, hAlign='LEFT',
    )
    table_style = [
        ('BACKGROUND', (0, 0), (-1, 0), CORE_DARK_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, CORE_PALE]),
        ('LINEBELOW', (0, 0), (-1, -1), .25, CORE_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    if emphasize_total and len(content) > 2:
        table_style.extend([
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E8EEFF')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ])
    table.setStyle(TableStyle(table_style))
    return table


def _metric_cards(document, summary_rows, styles):
    if not summary_rows:
        return None
    cards = []
    for _key, label, value in summary_rows:
        cards.append([
            _paragraph(label.upper(), styles['card_label']),
            _paragraph(_pdf_value(value, _key), styles['card_value']),
        ])
    columns = 2 if len(cards) < 4 else 4
    while len(cards) % columns:
        cards.append(['', ''])
    rows = []
    for offset in range(0, len(cards), columns):
        row = []
        for card in cards[offset:offset + columns]:
            row.append(Table([card], colWidths=[document.width / columns - 12], style=TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), CORE_PALE),
                ('BOX', (0, 0), (-1, -1), .4, CORE_BORDER),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 9),
                ('RIGHTPADDING', (0, 0), (-1, -1), 9),
            ])))
        rows.append(row)
    return Table(rows, colWidths=[document.width / columns] * columns, hAlign='LEFT', style=TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))


class _ReportCanvas(canvas.Canvas):
    def __init__(self, *args, footer_text='', **kwargs):
        super().__init__(*args, **kwargs)
        self._footer_text = footer_text
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
            self.line(1.5 * cm, 1.25 * cm, self._pagesize[0] - 1.5 * cm, 1.25 * cm)
            self.setFont('Helvetica', 7.5)
            self.setFillColor(CORE_MUTED)
            self.drawString(1.5 * cm, .78 * cm, self._footer_text)
            self.drawRightString(self._pagesize[0] - 1.5 * cm, .78 * cm, f'Página {self._pageNumber} de {page_count}')
            super().showPage()
        super().save()


def _truncate(canvas_object, value, max_width):
    value = str(value)
    if canvas_object.stringWidth(value, 'Helvetica', 8) <= max_width:
        return value
    while value and canvas_object.stringWidth(f'{value}...', 'Helvetica', 8) > max_width:
        value = value[:-1]
    return f'{value}...'


def _page_header(company_name, branch_name, title, period, mode):
    def decorate(canvas_object, document):
        width, height = document.pagesize
        canvas_object.saveState()
        canvas_object.setFillColor(CORE_BLUE)
        canvas_object.rect(0, height - .2 * cm, width, .2 * cm, fill=1, stroke=0)
        canvas_object.setFillColor(CORE_TEXT)
        canvas_object.setFont('Helvetica-Bold', 9)
        canvas_object.drawString(1.5 * cm, height - .72 * cm, 'CORE PDV')
        canvas_object.setFont('Helvetica', 7.5)
        canvas_object.setFillColor(CORE_MUTED)
        canvas_object.drawString(1.5 * cm, height - 1.08 * cm, 'O CORAÇÃO DO SEU NEGÓCIO')
        text_width = width - 7.2 * cm
        canvas_object.setFont('Helvetica-Bold', 8.5)
        canvas_object.setFillColor(CORE_TEXT)
        canvas_object.drawRightString(width - 1.5 * cm, height - .72 * cm, _truncate(canvas_object, company_name, text_width))
        canvas_object.setFont('Helvetica', 7.5)
        canvas_object.setFillColor(CORE_MUTED)
        canvas_object.drawRightString(width - 1.5 * cm, height - 1.08 * cm, _truncate(canvas_object, f'{branch_name} · {mode}', text_width))
        canvas_object.setStrokeColor(CORE_BORDER)
        canvas_object.setLineWidth(.35)
        canvas_object.line(1.5 * cm, height - 1.32 * cm, width - 1.5 * cm, height - 1.32 * cm)
        if CORE_LOGO.is_file():
            canvas_object.drawImage(str(CORE_LOGO), width - 3.05 * cm, height - 3.05 * cm, width=1.45 * cm, height=1.45 * cm, mask='auto', preserveAspectRatio=True, anchor='c')
        canvas_object.restoreState()
    return decorate


def _render_pdf(request, *, filename, title, headers, rows, period, summary):
    return render_pdf_export(
        request, filename=filename, title=title, headers=headers, rows=rows,
        period=period, summary=summary, filters=_filters(request),
    )


def render_report_export(request, *, filename, title, headers, rows, period=None, summary=None):
    """Render an already computed, permission-redacted report dataset."""
    export_format = request.query_params['export']
    headers, rows = tuple(headers), list(rows)
    base_filename = filename.rsplit('.', 1)[0]
    filename = f'{base_filename}.{export_format}'
    labels = [export_label(key) for key in headers]
    metadata = (
        ('Empresa', _company_name(request.branch_context)),
        ('Filial', request.branch_context.name),
        ('Período', _period_label(period)),
        ('Filtros', _filters(request)),
    )
    if export_format == 'csv':
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(labels)
        writer.writerows([_csv_value(row.get(key)) for key in headers] for row in rows)
        response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    elif export_format == 'xlsx':
        output, workbook = io.BytesIO(), Workbook()
        sheet = workbook.active
        sheet.title = 'Resumo'
        for row in (['CORE PDV', _text(title)], *metadata, []):
            sheet.append([_typed_value('', value) for value in row])
        if summary:
            sheet.append(['KPIs / Resumo'])
            for key, label, value in _summary_rows(summary):
                sheet.append([_typed_value('', label), _typed_value(key, value)])
        details = workbook.create_sheet('Dados')
        _write_sheet_table(details, headers, rows)
        for key, section_headers, section_rows in _structured_sections(summary):
            section_sheet = workbook.create_sheet(_sheet_title(workbook, key))
            _write_sheet_table(section_sheet, section_headers, section_rows)
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    cell.value = _csv_value(cell.value)
                cell.alignment = Alignment(vertical='top', wrap_text=True)
        sheet.column_dimensions['A'].width = 34
        sheet.column_dimensions['B'].width = 55
        sheet.freeze_panes = 'A2'
        workbook.save(output)
        response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        mode = _pdf_mode(request)
        pdf_filename = f'{base_filename}-detalhado.pdf' if mode == 'detailed' else filename
        return _render_pdf(
            request, filename=pdf_filename, title=title, headers=headers, rows=rows,
            period=period, summary=summary,
        )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
