import csv
import html
import io
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from .export_labels import export_label, export_value

FORMULA_PREFIXES = ('=', '+', '-', '@')
CURRENCY_FIELDS = ('amount', 'price', 'cost', 'value', 'revenue', 'received', 'payment', 'commission', 'discount', 'fee', 'opening', 'expected', 'informed', 'difference', 'result')


def _value(value):
    value = export_value(value)
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')) if isinstance(value, (dict, list)) else value


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
    """Safe text for spreadsheet metadata and ReportLab Paragraph markup."""
    return _csv_value(value)


def _paragraph(value, style):
    return Paragraph(html.escape(str(_text(value))), style)


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
    if any(part in key for part in CURRENCY_FIELDS):
        try:
            return Decimal(value)
        except InvalidOperation:
            pass
    # OpenPyXL interprets leading '=' strings as formulas too.
    return _csv_value(value)


def _filters(request):
    return ', '.join(
        f'{export_label(key)}: {_text(value)}'
        for key, value in request.query_params.items() if key != 'export'
    ) or 'Sem filtros adicionais'


def _summary_rows(summary):
    return [
        (key, export_label(key), value)
        for key, value in (summary or {}).items()
        if not isinstance(value, (dict, list))
    ]


def report_key_value_rows(data, prefix=''):
    """Flatten an already prepared response without interpreting its values."""
    rows = []
    for key, value in data.items():
        label = f'{prefix} {export_label(key)}'.strip()
        if isinstance(value, dict):
            rows.extend(report_key_value_rows(value, label))
        elif not isinstance(value, list):
            rows.append({'indicator': label, 'value': value})
    return rows


def render_report_export(request, *, filename, title, headers, rows, period=None, summary=None):
    """Render an already computed, permission-redacted report dataset."""
    export_format = request.query_params['export']
    headers, rows = tuple(headers), list(rows)
    filename = f'{filename.rsplit(".", 1)[0]}.{export_format}'
    labels = [export_label(key) for key in headers]
    company_name = _company_name(request.branch_context)
    metadata = (
        ('Empresa', company_name),
        ('Filial', request.branch_context.name),
        ('Período', period or ''),
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
        sheet.title = 'Relatório'
        for row in (['CORE PDV', _text(title)], *metadata, []):
            sheet.append([_typed_value('', value) for value in row])
        sheet.append(labels)
        header_row = sheet.max_row
        for row in rows:
            sheet.append([_typed_value(key, row.get(key)) for key in headers])
        for cell in sheet[header_row]:
            cell.font, cell.fill = Font(bold=True, color='FFFFFF'), PatternFill('solid', fgColor='1F4E78')
        sheet.auto_filter.ref = f'A{header_row}:{get_column_letter(len(headers))}{sheet.max_row}'
        sheet.freeze_panes = f'A{header_row + 1}'
        for column, key in enumerate(headers, 1):
            sheet.column_dimensions[get_column_letter(column)].width = min(max([len(labels[column - 1]), 10] + [len(_csv_value(row.get(key))) for row in rows]) + 2, 45)
            for cell in sheet.iter_cols(min_col=column, max_col=column, min_row=header_row + 1):
                for item in cell:
                    if isinstance(item.value, Decimal): item.number_format = 'R$ #,##0.00'
                    elif isinstance(item.value, (date, datetime)): item.number_format = 'dd/mm/yyyy hh:mm'
        if summary:
            sheet.append([]); sheet.append(['Totais'])
            for key, label, value in _summary_rows(summary):
                sheet.append([_typed_value('', label), _typed_value(key, value)])
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    cell.value = _csv_value(cell.value)
                cell.alignment = Alignment(vertical='top', wrap_text=True)
        workbook.save(output)
        response = HttpResponse(output.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        output = io.BytesIO()
        page_size = portrait(A4) if len(headers) <= 5 else landscape(A4)
        document = SimpleDocTemplate(output, pagesize=page_size, leftMargin=.6 * cm, rightMargin=.6 * cm, topMargin=1.1 * cm, bottomMargin=1.1 * cm)
        styles = getSampleStyleSheet()
        story = [
            _paragraph(f'CORE PDV - {title}', styles['Title']), Spacer(1, 4),
            _paragraph(f'Empresa: {company_name} | Filial: {request.branch_context.name}', styles['Normal']),
            _paragraph(f'Período: {period or ""} | Filtros: {_filters(request)} | Gerado em: {timezone.localtime():%d/%m/%Y %H:%M}', styles['Normal']),
        ]
        data = [[_paragraph(label, styles['BodyText']) for label in labels]] + [
            [_paragraph(row.get(key), styles['BodyText']) for key in headers]
            for row in rows
        ]
        table = LongTable(data, repeatRows=1, colWidths=[document.width / max(len(headers), 1)] * len(headers))
        table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E78')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('GRID', (0, 0), (-1, -1), .25, colors.grey), ('FONTSIZE', (0, 0), (-1, -1), 6), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        story.extend([Spacer(1, 6), table])
        if summary:
            summary_data = [[_paragraph('Totais', styles['BodyText']), _paragraph('Valor', styles['BodyText'])]]
            summary_data.extend(
                [_paragraph(label, styles['BodyText']), _paragraph(value, styles['BodyText'])]
                for _, label, value in _summary_rows(summary)
            )
            story.extend([Spacer(1, 6), LongTable(summary_data, repeatRows=1, colWidths=[document.width * .45, document.width * .55])])

        def page_number(canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica', 7)
            canvas.drawRightString(doc.pagesize[0] - .6 * cm, .55 * cm, f'Página {doc.page}')
            canvas.restoreState()

        document.build(story, onFirstPage=page_number, onLaterPages=page_number)
        response = HttpResponse(output.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
