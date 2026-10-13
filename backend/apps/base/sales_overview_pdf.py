"""Explicit PDF template for the sales overview; receives permission-redacted data."""
import html
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from pypdf import PdfReader, PdfWriter
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, PageBreak, TableStyle

from .export_labels import export_value

NAVY = colors.HexColor('#142444')
BLUE = colors.HexColor('#3454D1')
PALE = colors.HexColor('#F4F6FB')
LOGO = Path(__file__).parent / 'assets' / 'core-logo-compact-light.png'


def plain(value):
    if value is None or isinstance(value, (dict, list, tuple)):
        return '—'
    return str(export_value(value))


def number(value, places=2, currency=False):
    if value is None:
        return '—'
    try:
        parsed = Decimal(str(value))
        if not parsed.is_finite():
            return '—'
        result = f'{parsed:,.{places}f}'.replace(',', '_').replace('.', ',').replace('_', '.')
        return ('R$ ' if currency else '') + result
    except (ValueError, InvalidOperation):
        return '—'


def date_label(value):
    if not value:
        return '—'
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if timezone.is_aware(parsed):
            parsed = timezone.localtime(parsed)
        return parsed.strftime('%d/%m/%Y %H:%M:%S')
    except ValueError:
        return plain(value)


def render_sales_overview(request, *, filename, rows, period, summary):
    summary = summary or {}
    company = request.branch_context.company
    company_name = company.trade_name or company.legal_name
    emitted = timezone.localtime().strftime('%d/%m/%Y %H:%M %z')
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=40, rightMargin=40,
                            topMargin=115, bottomMargin=55, title='Relatório de vendas - Visão geral')
    body = ParagraphStyle('Body', fontName='Helvetica', fontSize=9, leading=13, textColor=NAVY)
    heading = ParagraphStyle('Heading', parent=body, fontName='Helvetica-Bold', fontSize=13,
                             leading=17, spaceBefore=14, spaceAfter=8, keepWithNext=True)
    title = ParagraphStyle('Title', parent=heading, fontSize=22, leading=27)
    header = ParagraphStyle('Header', parent=body, fontName='Helvetica-Bold', textColor=colors.white)
    right = ParagraphStyle('Right', parent=body, alignment=2)
    header_right = ParagraphStyle('HeaderRight', parent=header, alignment=2)
    def p(value, style=body):
        return Paragraph(html.escape(plain(value)), style)
    story = []
    def section(label):
        story.append(p(label, heading))
    def table(labels, data, widths, numeric=()):
        content = [[p(label, header_right if i in numeric else header) for i, label in enumerate(labels)]]
        content.extend([[p(value, right if i in numeric else body) for i, value in enumerate(row)] for row in data])
        if len(content) == 1:
            story.append(p('Sem registros para os filtros selecionados.'))
            return
        result = LongTable(content, colWidths=[doc.width * w for w in widths], repeatRows=1,
                           splitByRow=1, splitInRow=1, hAlign='LEFT')
        result.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PALE]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LINEBELOW', (0, 1), (-1, -1), .3, colors.HexColor('#DCE2EF')),
        ]))
        story.append(result)

    story.append(p('Relatório de vendas', title))
    story.append(p('Visão geral'))
    if isinstance(period, dict):
        period_text = f"{date_label(period.get('start_datetime'))} a {date_label(period.get('end_datetime'))}"
    else:
        period_text = plain(period)
    story.append(p(f'Período: {period_text}'))
    story.append(p(f'Fuso dos horários: {timezone.get_current_timezone_name()}'))
    filter_labels = {'operator': 'Operador', 'seller': 'Atendente', 'status': 'Situação',
                     'payment_method': 'Forma de pagamento', 'channel': 'Canal', 'search': 'Busca',
                     'product': 'Produto', 'category': 'Categoria', 'cash_session': 'Sessão de caixa',
                     'operation_type': 'Tipo de operação', 'ordering': 'Ordenação',
                     'start_time': 'Horário inicial', 'end_time': 'Horário final',
                     'number': 'Número da venda', 'customer': 'Cliente', 'weekday': 'Dia da semana',
                     'hour': 'Hora', 'minimum_value': 'Valor mínimo', 'maximum_value': 'Valor máximo',
                     'payment_method_code': 'Forma de pagamento (código)'}
    filters = [f'{filter_labels.get(key, key.replace("_", " ").capitalize())}: {plain(value)}'
               for key, value in request.query_params.items()
               if key not in ('export', 'scope', 'branch', 'page', 'page_size', 'start_datetime', 'end_datetime') and value]
    story.append(p('Filtros: ' + (' · '.join(filters) if filters else 'Sem filtros adicionais')))
    current = (summary.get('period_comparison') or {}).get('current') or summary.get('kpis') or {}
    def metric(key, fallback):
        return current[key] if key in current else summary.get(fallback)
    section('Resumo financeiro')
    table(['Indicador', 'Valor'], [
        ['Faturamento bruto', number(metric('gross_revenue', 'gross'), currency=True)],
        ['Faturamento de vendas', number(metric('net_revenue', 'sales_revenue'), currency=True)],
        ['Vendas', number(metric('sales_count', 'count'), 0)],
        ['Ticket médio', number(metric('ticket_average', 'ticket_average'), currency=True)],
        ['Total recebido', number(metric('total_received', 'total_received'), currency=True)],
        ['Descontos', number(metric('discounts', 'total_discount'), currency=True)],
        ['Taxa de serviço', number(metric('service_fee', 'service_fee'), currency=True)],
        ['Valor cancelado', number(current.get('cancellations', (summary.get('cancellations') or {}).get('value')), currency=True)],
        ['Diferença entre recebimentos e pagamentos', number(summary.get('payment_reconciliation_delta', summary.get('reconciliation_delta')), currency=True)],
    ], [.65, .35], (1,))
    section('Recebimentos por forma de pagamento')
    table(['Forma de pagamento', 'Valor aplicado'], [
        [row.get('name'), number(row.get('payment_total', row.get('amount')), currency=True)]
        for row in summary.get('payment_totals', [])
    ], [.65, .35], (1,))
    comparison = summary.get('period_comparison') or {}
    if comparison.get('previous'):
        section('Comparação com o período anterior')
        previous_period = comparison.get('previous_period') or {}
        story.append(p(f"Período anterior: {date_label(previous_period.get('start_datetime'))} a {date_label(previous_period.get('end_datetime'))}"))
        previous = comparison['previous']
        table(['Indicador', 'Atual', 'Anterior'], [
            [label, number(current.get(key), places, currency), number(previous.get(key), places, currency)]
            for label, key, places, currency in [('Faturamento', 'net_revenue', 2, True), ('Vendas', 'sales_count', 0, False), ('Ticket médio', 'ticket_average', 2, True)]
        ], [.4, .3, .3], (1, 2))
        story.append(Spacer(1, 6))
        story.append(p('Variação percentual não calculada quando a base anterior é zero.'))

    story.append(PageBreak())
    section('Detalhes das vendas')
    # Event rows preserve reversal signs and accounting already computed by the report service.
    table(['Venda', 'Data do evento', 'Situação / evento', 'Recebido'], [
        [row.get('sale_number'), date_label(row.get('event_at', row.get('created_at'))),
         f"{plain(row.get('status'))} / { {'record': 'Venda', 'reversal': 'Reversão', 'cancellation': 'Cancelamento'}.get(row.get('event_type'), plain(row.get('event_type')))}",
         number(row.get('total_received'), currency=True)] for row in rows
    ], [.18, .28, .29, .25], (3,))
    for key, label, name_key in [('product_ranking', 'Produtos vendidos', 'product_name'), ('category_ranking', 'Vendas por categoria', 'category_name')]:
        if summary.get(key):
            section(label)
            table(['Produto' if key == 'product_ranking' else 'Categoria', 'Quantidade', 'Faturamento'], [
                [row.get(name_key, row.get('name')), number(row.get('quantity'), 3),
                 number(row.get('sales_revenue', row.get('revenue')), currency=True)]
                for row in summary[key]
            ], [.55, .18, .27], (1, 2))

    if any(row.get('items') or row.get('payments') for row in rows):
        story.append(PageBreak())
        section('Itens e pagamentos por venda')
        story.append(p('Valores dos itens e pagamentos refletem os registros originais. Reversões são identificadas na lista de eventos; não some estes registros novamente ao resumo.'))
        for row in rows:
            event_label = {'record': 'Venda', 'reversal': 'Reversão'}.get(row.get('event_type'), plain(row.get('event_type')))
            section(f"Venda {plain(row.get('sale_number'))} · {event_label}")
            people = []
            for key, label in [('operator', 'Operador'), ('seller', 'Atendente')]:
                person = row.get(key)
                if isinstance(person, dict) and person.get('name'):
                    people.append(f"{label}: {person['name']}")
            if people:
                story.append(p(' · '.join(people)))
            if row.get('items'):
                table(['Produto', 'Quantidade', 'Preço unitário', 'Subtotal líquido'], [
                    [item.get('product_name'), number(item.get('quantity'), 3),
                     number(item.get('unit_price'), currency=True), number(item.get('net_subtotal'), currency=True)]
                    for item in row['items']
                ], [.4, .15, .22, .23], (1, 2, 3))
            if row.get('payments'):
                story.append(Spacer(1, 8))
                table(['Forma de pagamento', 'Valor aplicado', 'Recebido', 'Troco'], [
                    [payment.get('payment_method_name'), number(payment.get('applied_amount', payment.get('amount')), currency=True),
                     number(payment.get('received_amount'), currency=True), number(payment.get('change_amount'), currency=True)]
                    for payment in row['payments']
                ], [.4, .2, .2, .2], (1, 2, 3))

    def decorate(page, document):
        page.saveState()
        page.setFillColor(BLUE)
        page.rect(0, A4[1]-6, A4[0], 6, fill=1, stroke=0)
        name = p(company_name, ParagraphStyle('Company', parent=heading, fontSize=15, leading=18))
        _, height = name.wrap(doc.width - 105, 50)
        name.drawOn(page, 40, A4[1]-35-height)
        page.setFont('Helvetica', 9)
        page.setFillColor(NAVY)
        page.drawString(40, A4[1]-83, f'Filial: {request.branch_context.name}')
        cnpj = getattr(company, 'cnpj', None)
        if cnpj:
            page.drawString(40, A4[1]-98, f'CNPJ: {cnpj}')
        if LOGO.is_file():
            page.drawImage(str(LOGO), A4[0]-125, A4[1]-105, width=85, height=85, mask='auto')
        else:
            page.drawRightString(A4[0]-40, A4[1]-45, 'CORE PDV')
        page.setStrokeColor(colors.HexColor('#DCE2EF'))
        page.line(40, 45, A4[0]-40, 45)
        page.setFont('Helvetica', 8)
        page.drawString(40, 28, f'Gerado em: {emitted}')
        page.restoreState()
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    reader = PdfReader(io.BytesIO(output.getvalue()))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    for index, page in enumerate(writer.pages, 1):
        overlay = io.BytesIO()
        footer = canvas.Canvas(overlay, pagesize=A4)
        footer.setFont('Helvetica', 8)
        footer.setFillColor(NAVY)
        footer.drawRightString(A4[0] - 40, 28, f'Página {index} de {len(writer.pages)}')
        footer.save()
        page.merge_page(PdfReader(io.BytesIO(overlay.getvalue())).pages[0])
    final = io.BytesIO()
    writer.write(final)
    response = HttpResponse(final.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
