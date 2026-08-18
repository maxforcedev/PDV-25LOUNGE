import csv
import io
import json
from decimal import Decimal

from django.db.models import Count, DecimalField, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.base.datetimes import canonical_datetime_range, parse_datetime_range
from apps.base.pagination import StandardPagination
from apps.cash.models import CashRegister, CashSession, WithdrawalCategory
from apps.companies.rbac import OPERATING_PERMISSION_CODES
from apps.companies.selectors import branch_permission_codes, eligible_branch_users, user_has_company_permission
from apps.inventory.models import MovementType
from apps.products.models import Category, Product
from apps.sales.models import OperationType, PaymentMethod, SaleStatus
from apps.sales.serializers import readable_user_name

from .permissions import ReportsPermission
from .selectors import (
    commercial_summary,
    cancellation_summary,
    consumption_summary,
    current_cash_sessions,
    dashboard_time_analysis,
    filtered_cash_sessions,
    filtered_inventory_movements,
    filtered_sales,
    stock_consumption_report,
    filtered_withdrawals,
    inventory_kpis,
    hourly_sales,
    operational_result,
    payment_totals,
    sale_rankings,
    sale_rows,
    sale_user_groups,
    withdrawal_summary,
)
from .serializers import (
    CashReportQuerySerializer,
    CashSessionReportSerializer,
    ConsumptionsReportQuerySerializer,
    InventoryMovementReportSerializer,
    InventoryReportQuerySerializer,
    OperationalResultQuerySerializer,
    ReportSaleSerializer,
    SalesReportQuerySerializer,
    StockConsumptionMovementSerializer,
    StockConsumptionReportQuerySerializer,
    StockConsumptionSummarySerializer,
    WithdrawalReportSerializer,
    WithdrawalsReportQuerySerializer,
)


def decimal_string(value, places=2):
    value = value if isinstance(value, Decimal) else Decimal(value or 0)
    return f'{value:.{places}f}'


def user_has_code(request, code):
    if code not in OPERATING_PERMISSION_CODES:
        return request.user.is_superuser or user_has_company_permission(
            request.user, request.branch_context.company_id, code
        )
    return request.user.is_superuser or code in branch_permission_codes(
        request.user, request.branch_context.pk
    )


CSV_LABELS = {
    'id': 'ID', 'sale_number': 'Numero', 'operation_type': 'Operacao',
    'status': 'Status', 'operator': 'Operador', 'seller': 'Atendente',
    'beneficiary': 'Beneficiario', 'subtotal': 'Valor bruto',
    'promotion_discount_total': 'Desconto promocional',
    'discount': 'Desconto manual', 'service_fee_amount': 'Taxa de servico',
    'commission_amount': 'Comissao', 'total': 'Total cobrado',
    'created_at': 'Criado em', 'cancelled_at': 'Cancelado em',
    'items': 'Itens', 'payments': 'Pagamentos', 'opened_at': 'Aberto em',
    'closed_at': 'Fechado em', 'register': 'Caixa', 'opening': 'Abertura',
    'manual_entries': 'Entradas manuais', 'cash_payments': 'Pagamentos em dinheiro',
    'withdrawals': 'Sangrias', 'expected': 'Esperado', 'informed': 'Informado',
    'difference': 'Diferenca', 'amount': 'Valor', 'category': 'Categoria',
    'category_label': 'Categoria', 'cash_register': 'Caixa', 'reason': 'Motivo',
    'result_effect': 'Impacto no resultado', 'movement_type': 'Movimento',
    'product': 'Produto', 'previous_quantity': 'Saldo anterior',
    'quantity': 'Quantidade', 'final_quantity': 'Saldo final', 'user': 'Usuario',
    'sale': 'Venda', 'name': 'Nome', 'code': 'Codigo',
    'product_name': 'Nome do produto', 'internal_code': 'Codigo interno',
    'unit': 'Unidade', 'promotion': 'Promocao',
    'promotion_discount_type': 'Tipo do desconto promocional',
    'promotion_discount_value': 'Valor do desconto promocional',
    'payment_method_name': 'Forma de pagamento', 'payment_method_code': 'Identificador',
    'unit_price': 'Preco unitario', 'promotion_name': 'Promocao',
    'promotion_benefit': 'Beneficio promocional', 'net_subtotal': 'Subtotal liquido',
    'origin': 'Origem', 'gross_quantity': 'Quantidade bruta',
    'returned_quantity': 'Devolucoes', 'net_quantity': 'Quantidade liquida',
    'estimated_cost': 'Custo estimado', 'movement_count': 'Movimentos',
    'nature': 'Natureza', 'operation_reference': 'Referencia da operacao',
}
CSV_VALUES = {
    'finalized': 'Finalizada', 'cancelled': 'Cancelada', 'sale': 'Venda',
    'consumption': 'Consumacao', 'open': 'Aberta', 'closed': 'Fechada',
    'manual_entry': 'Entrada manual', 'withdrawal': 'Sangria', 'entry': 'Entrada',
    'exit': 'Saida', 'adjustment': 'Ajuste', 'operating_expense': 'Despesa operacional',
    'neutral': 'Nao afeta o resultado', 'unclassified': 'Nao classificado',
    'cash': 'Dinheiro', 'credit_card': 'Cartao de credito',
    'debit_card': 'Cartao de debito', 'fixed_amount': 'Valor fixo',
    'percentage': 'Percentual',
    'manual_exit': 'Saida manual', 'reversal': 'Reversao/cancelamento',
    'sale_cancellation': 'Cancelamento de venda',
    'consumption_cancellation': 'Cancelamento de consumacao',
    'bonus': 'Bonificada', 'return': 'Devolucao', 'opening_balance': 'Saldo inicial',
    'correction': 'Correcao', 'transfer': 'Transferencia', 'damage': 'Avaria',
    'loss': 'Perda', 'internal_use': 'Uso interno', 'inventory': 'Inventario',
    'regularization': 'Regularizacao', 'balance_correction': 'Correcao de saldo',
}


def translated_export_value(value):
    if isinstance(value, dict):
        return {
            CSV_LABELS.get(key, key): translated_export_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [translated_export_value(item) for item in value]
    if isinstance(value, str):
        return CSV_VALUES.get(value, value)
    return value


def safe_csv_cell(value):
    if value is None:
        return ''
    value = translated_export_value(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    value = str(value)
    if value.startswith(('=', '+', '-', '@')):
        value = "'" + value
    return value


def csv_response(filename, headers, rows):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(CSV_LABELS.get(header, header) for header in headers)
    for row in rows:
        writer.writerow(safe_csv_cell(row.get(header)) for header in headers)
    response = HttpResponse(
        '\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


class ReportsOptionsView(APIView):
    permission_classes = (ReportsPermission,)

    def get(self, request):
        branch = request.branch_context
        users = User.objects.filter(
            is_active=True,
            company_accesses__company_id=branch.company_id,
            company_accesses__is_active=True,
        ).distinct().order_by('first_name', 'last_name', 'id')
        operators = User.objects.filter(
            is_active=True,
            branch_accesses__branch=branch,
            branch_accesses__is_active=True,
        ).distinct().order_by('first_name', 'last_name', 'id')
        products = Product.objects.filter(company_id=branch.company_id).order_by('name', 'id')
        categories = Category.objects.filter(company_id=branch.company_id).order_by(
            'sort_order', 'name', 'id'
        )
        payment_methods = PaymentMethod.objects.filter(
            company_id=branch.company_id
        ).order_by('name', 'id')
        registers = CashRegister.objects.filter(branch=branch).order_by('name', 'id')
        sessions = CashSession.objects.filter(branch=branch).select_related(
            'cash_register'
        ).order_by('-opened_at', '-id')
        return Response({
            'operators': [
                {'id': user.pk, 'name': readable_user_name(user)} for user in operators
            ],
            'sellers': [
                {'id': user.pk, 'name': readable_user_name(user)}
                for user in eligible_branch_users(branch, 'sales.create')
            ],
            'beneficiaries': [
                {
                    'id': user.pk,
                    'name': readable_user_name(user),
                    'user_type': user.user_type,
                }
                for user in users
            ],
            'products': [
                {
                    'id': product.pk,
                    'name': product.name,
                    'internal_code': product.internal_code,
                    'status': product.status,
                }
                for product in products
            ],
            'categories': [
                {'id': category.pk, 'name': category.name, 'status': category.status}
                for category in categories
            ],
            'payment_methods': [
                {
                    'id': method.pk,
                    'name': method.name,
                    'code': method.code,
                    'status': method.status,
                }
                for method in payment_methods
            ],
            'cash_registers': [
                {'id': register.pk, 'name': register.name, 'status': register.status}
                for register in registers
            ],
            'cash_sessions': [
                {
                    'id': session.pk,
                    'name': f'#{session.pk} · {session.cash_register.name}',
                    'status': session.status,
                    'opened_at': session.opened_at,
                    'closed_at': session.closed_at,
                }
                for session in sessions
            ],
            'movement_types': [
                {'value': value, 'label': label} for value, label in MovementType.choices
            ],
            'withdrawal_categories': [
                {'value': value, 'label': label}
                for value, label in WithdrawalCategory.choices
            ],
            'user_types': [
                {'value': value, 'label': label} for value, label in User.UserType.choices
            ],
            'sale_statuses': [
                {'value': value, 'label': label} for value, label in SaleStatus.choices
            ],
        })


class BaseReportView(APIView):
    permission_classes = (ReportsPermission,)
    query_serializer_class = None
    row_serializer_class = None
    csv_filename = 'report.csv'
    csv_headers = ()

    def parse_query(self, request):
        serializer = self.query_serializer_class(
            data=request.query_params, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        start, end = parse_datetime_range(request.query_params, required=True)
        return serializer.validated_data, start, end

    def serialize_rows(self, rows, request):
        return self.row_serializer_class(rows, many=True, context={'request': request}).data

    def respond(self, request, *, rows, period, summary):
        if request.query_params.get('export') == 'csv':
            data = self.serialize_rows(rows, request)
            return csv_response(self.csv_filename, self.csv_headers, data)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        data = self.serialize_rows(page, request)
        return Response({
            'period': period,
            'summary': summary,
            'count': paginator.page.paginator.count,
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
            'results': data,
        })


class DashboardView(APIView):
    permission_classes = (ReportsPermission,)
    required_permissions = (
        'dashboard.view',
        'sales.view',
        'sales.view_consumption',
        'cash_registers.view',
        'cash_registers.withdraw',
        'inventory.view',
    )

    def get(self, request):
        start, end = parse_datetime_range(request.query_params, default_today=True)
        branch = request.branch_context
        response = {'period': canonical_datetime_range(start, end)}
        category = None
        if request.query_params.get('category'):
            try:
                category = int(request.query_params['category'])
            except (TypeError, ValueError):
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'category': 'Informe uma categoria valida.'})
            if not Category.objects.filter(pk=category, company_id=branch.company_id).exists():
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'category': 'Categoria fora da filial atual.'})
        response['filters'] = {
            'category': category,
            'categories': list(Category.objects.filter(
                company_id=branch.company_id, status='active'
            ).values('id', 'name').order_by('sort_order', 'name')),
        }

        if user_has_code(request, 'sales.view'):
            sales = filtered_sales(
                branch=branch,
                start=start,
                end=end,
                operation_type=OperationType.SALE,
                filters={'category': category} if category else {},
            )
            summary, _ = commercial_summary(sales)
            products, categories = sale_rankings(sales)
            operator_groups = sale_user_groups(sales, 'created_by')
            seller_groups = sale_user_groups(sales, 'seller_user')
            _cancelled_rows, cancellations = cancellation_summary(
                branch=branch, start=start, end=end, category=category,
            )
            discount_count = sales.filter(
                status=SaleStatus.FINALIZED, discount__gt=0
            ).count()
            heatmap, current_comparison, previous_comparison = dashboard_time_analysis(
                sales, branch=branch, start=start, end=end, category=category,
            )
            response['sales'] = {
                'revenue': decimal_string(summary['effective_revenue']),
                'gross': decimal_string(summary['gross']),
                'effective_revenue': decimal_string(summary['effective_revenue']),
                'count': summary['count'],
                'average': decimal_string(summary['average']),
                'manual_discount': decimal_string(summary['manual_discount']),
                'manual_discount_count': discount_count,
                'promotion_discount': decimal_string(summary['promotion_discount']),
                'total_discount': decimal_string(summary['total_discount']),
                'service_fee': decimal_string(summary['service_fee']),
                'commission': decimal_string(summary['commission']),
                'customer_total': decimal_string(summary['customer_total']),
                'cancellations': {
                    'count': cancellations['count'],
                    'value': decimal_string(cancellations['value']),
                },
                'hourly_sales': [
                    {
                        'hour': row['hour'],
                        'count': row['count'],
                        'effective_revenue': decimal_string(row['effective_revenue']),
                        'service_fee': decimal_string(row['service_fee']),
                        'customer_total': decimal_string(row['customer_total']),
                    }
                    for row in hourly_sales(sales)
                ],
                'payment_distribution': [
                    {
                        'code': row['payment_method_code'],
                        'name': row['payment_method_name'],
                        'amount': decimal_string(row['amount']),
                    }
                    for row in payment_totals(sales)
                ],
                'top_products': [
                    {**row, 'quantity': decimal_string(row['quantity'], 3), 'revenue': decimal_string(row['revenue'])}
                    for row in products
                ],
                'top_categories': [
                    {**row, 'quantity': decimal_string(row['quantity'], 3), 'revenue': decimal_string(row['revenue'])}
                    for row in categories
                ],
                'top_sellers': [_group_json(row) for row in seller_groups[:10]],
                'top_operators': [_group_json(row) for row in operator_groups[:10]],
                'heatmap': [
                    {**row, 'revenue': decimal_string(row['revenue']), 'average': decimal_string(row['average'])}
                    for row in heatmap
                ],
                'weekly_comparison': {
                    'current': [{**row, 'revenue': decimal_string(row['revenue'])} for row in current_comparison],
                    'previous': [{**row, 'revenue': decimal_string(row['revenue'])} for row in previous_comparison],
                },
                'latest_sales': ReportSaleSerializer(
                    sale_rows(sales)[:10], many=True, context={'request': request}
                ).data,
            }
            if not user_has_code(request, 'commissions.view'):
                response['sales'].pop('commission', None)
                for group in response['sales']['top_sellers'] + response['sales']['top_operators']:
                    group.pop('commission', None)

        if user_has_code(request, 'sales.view_consumption'):
            consumptions = filtered_sales(
                branch=branch,
                start=start,
                end=end,
                operation_type=OperationType.CONSUMPTION,
                filters={
                    **({'category': category} if category else {}),
                    'status': SaleStatus.FINALIZED,
                },
            )
            summary = consumption_summary(consumptions)
            response['consumptions'] = {
                'count': summary['count'],
                'reference': decimal_string(summary['reference']),
                'charged': decimal_string(summary['charged']),
                'subsidy': decimal_string(summary['subsidy']),
            }

        if user_has_code(request, 'cash_registers.withdraw'):
            response['withdrawals'] = _withdrawal_summary_json(
                withdrawal_summary(filtered_withdrawals(
                    branch=branch, start=start, end=end, filters={}
                )),
                include_groups=False,
            )

        if user_has_code(request, 'cash_registers.view'):
            sessions = current_cash_sessions(branch)
            response['current_cash'] = CashSessionReportSerializer(
                sessions, many=True, context={'request': request}
            ).data

        if (
            user_has_code(request, 'inventory.view')
            and user_has_code(request, 'inventory.view_stock_kpis')
        ):
            include_value = user_has_code(request, 'inventory.view_stock_costs')
            stock = inventory_kpis(branch, include_value=include_value)
            if include_value:
                stock['inventory_value'] = decimal_string(stock['inventory_value'])
            response['inventory'] = stock
        if user_has_code(request, 'reports.view_operational_result') and 'sales' in response:
            result = operational_result(
                branch=branch, start=start, end=end, sales=sales,
            )
            response['operational_result'] = {
                key: decimal_string(value)
                for key, value in result.items()
                if key in ('result', 'margin', 'cogs', 'operating_expenses', 'fixed_cost')
            }
        return Response(response)


class SalesReportView(BaseReportView):
    required_permissions = (
        'reports.view_sales', 'reports.view_products', 'reports.view_receipts',
        'reports.view_team', 'reports.view_discounts', 'commissions.view',
    )
    required_permission = 'reports.view_sales'
    permission_by_scope = {
        'overview': 'reports.view_sales', 'sales': 'reports.view_sales',
        'products': 'reports.view_products', 'receipts': 'reports.view_receipts',
        'operators': 'reports.view_team', 'sellers': 'reports.view_team',
        'commissions': 'commissions.view', 'discounts': 'reports.view_discounts',
    }
    query_serializer_class = SalesReportQuerySerializer
    row_serializer_class = ReportSaleSerializer
    csv_filename = 'relatorio-vendas.csv'
    csv_headers = (
        'id', 'sale_number', 'status', 'operator', 'seller', 'subtotal',
        'promotion_discount_total', 'discount', 'service_fee_amount',
        'commission_amount', 'total', 'created_at', 'cancelled_at',
        'items', 'payments',
    )

    def get(self, request):
        scope = request.query_params.get('scope', 'sales')
        filters, start, end = self.parse_query(request)
        sales = filtered_sales(
            branch=request.branch_context,
            start=start,
            end=end,
            operation_type=OperationType.SALE,
            filters=filters,
        )
        summary, cancellations = commercial_summary(sales)
        products, categories = sale_rankings(sales, filters=filters)
        operator_groups = sale_user_groups(sales, 'created_by')
        seller_groups = sale_user_groups(sales, 'seller_user')
        result = {
            'gross': decimal_string(summary['gross']),
            'effective_revenue': decimal_string(summary['effective_revenue']),
            'count': summary['count'],
            'average': decimal_string(summary['average']),
            'manual_discount': decimal_string(summary['manual_discount']),
            'promotion_discount': decimal_string(summary['promotion_discount']),
            'total_discount': decimal_string(summary['total_discount']),
            'service_fee': decimal_string(summary['service_fee']),
            'commission': decimal_string(summary['commission']),
            'customer_total': decimal_string(summary['customer_total']),
            'cancellations': {
                'count': cancellations['count'],
                'value': decimal_string(cancellations['value']),
            },
            'payment_totals': [
                {
                    'code': row['payment_method_code'],
                    'name': row['payment_method_name'],
                    'amount': decimal_string(row['amount']),
                }
                for row in payment_totals(sales, filters)
            ],
            'product_ranking': [
                {**row, 'quantity': decimal_string(row['quantity'], 3), 'revenue': decimal_string(row['revenue'])}
                for row in products
            ],
            'category_ranking': [
                {**row, 'quantity': decimal_string(row['quantity'], 3), 'revenue': decimal_string(row['revenue'])}
                for row in categories
            ],
            'operator_groups': [_group_json(row) for row in operator_groups],
            'seller_groups': [_group_json(row) for row in seller_groups],
        }
        if not user_has_code(request, 'commissions.view'):
            result.pop('commission', None)
            for group in result['operator_groups'] + result['seller_groups']:
                group.pop('commission', None)
        summary_keys = {
            'products': {'product_ranking', 'category_ranking'},
            'receipts': {'payment_totals'},
            'operators': {'operator_groups'},
            'sellers': {'seller_groups'},
            'commissions': {'seller_groups', 'commission'},
            'discounts': {'manual_discount', 'promotion_discount', 'total_discount', 'gross', 'count'},
        }.get(scope)
        if summary_keys is not None:
            result = {key: value for key, value in result.items() if key in summary_keys}
        if request.query_params.get('export') == 'csv':
            if scope == 'products':
                return csv_response('relatorio-produtos.csv', ('product_name', 'internal_code', 'quantity', 'revenue'), result.get('product_ranking', []))
            if scope == 'receipts':
                return csv_response('relatorio-recebimentos.csv', ('code', 'name', 'amount'), result.get('payment_totals', []))
            if scope in ('operators', 'sellers', 'commissions'):
                key = 'operator_groups' if scope == 'operators' else 'seller_groups'
                group_rows = [
                    {**row, 'name': row.get('user', {}).get('name', '')}
                    for row in result.get(key, [])
                ]
                headers = ('name', 'count', 'gross', 'effective_revenue', 'customer_total')
                if scope == 'commissions':
                    headers += ('commission',)
                return csv_response(f'relatorio-{scope}.csv', headers, group_rows)
        detail_rows = sale_rows(sales) if scope in ('overview', 'sales', 'discounts') else []
        return self.respond(
            request,
            rows=detail_rows,
            period=canonical_datetime_range(start, end),
            summary=result,
        )


class CancellationsReportView(BaseReportView):
    required_permission = 'reports.view_cancellations'
    query_serializer_class = SalesReportQuerySerializer
    row_serializer_class = ReportSaleSerializer
    csv_filename = 'relatorio-cancelamentos.csv'
    csv_headers = SalesReportView.csv_headers

    def get(self, request):
        filters, start, end = self.parse_query(request)
        rows, totals = cancellation_summary(
            branch=request.branch_context, start=start, end=end,
            category=filters.get('category'),
        )
        if filters.get('operator'):
            rows = rows.filter(created_by_id=filters['operator'])
        if filters.get('seller'):
            rows = rows.filter(seller_user_id=filters['seller'])
        if filters.get('product'):
            rows = rows.filter(items__product_id=filters['product']).distinct()
        totals = rows.aggregate(
            count=Count('id'),
            value=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField(max_digits=20, decimal_places=2)),
        )
        return self.respond(
            request, rows=sale_rows(rows), period=canonical_datetime_range(start, end),
            summary={'count': totals['count'], 'value': decimal_string(totals['value'])},
        )


def _group_json(row):
    return {
        **row,
        **{
            field: decimal_string(row[field])
            for field in (
                'gross', 'manual_discount', 'promotion_discount', 'total_discount',
                'effective_revenue', 'service_fee', 'commission', 'customer_total',
                'average',
            )
            if field in row
        },
    }


def _remove_commission_fields(data):
    data.pop('commission', None)
    return data


class OperationalResultReportView(BaseReportView):
    required_permission = 'reports.view_operational_result'
    query_serializer_class = OperationalResultQuerySerializer
    row_serializer_class = ReportSaleSerializer
    csv_filename = 'resultado-operacional-estimado.csv'
    csv_headers = SalesReportView.csv_headers

    def get(self, request):
        filters, start, end = self.parse_query(request)
        session = None
        if filters.get('cash_session'):
            session = CashSession.objects.get(
                pk=filters['cash_session'], branch=request.branch_context
            )
        sales = filtered_sales(
            branch=request.branch_context,
            start=start,
            end=end,
            operation_type=OperationType.SALE,
            filters={},
        )
        if session:
            sales = sales.filter(cash_session=session)
        summary = operational_result(
            branch=request.branch_context,
            start=start,
            end=end,
            sales=sales,
            cash_session=session,
        )
        data = {
            key: (
                {
                    'count': value['count'],
                    'amount': decimal_string(value['amount']),
                }
                if key == 'unclassified_withdrawals'
                else decimal_string(value)
            )
            for key, value in summary.items()
        }
        if not user_has_code(request, 'commissions.view'):
            data.pop('commission', None)
        data['cash_session'] = session.pk if session else None
        data['notice'] = 'Estimativa operacional; não constitui DRE contábil.'
        return self.respond(
            request,
            rows=sale_rows(sales),
            period=canonical_datetime_range(start, end),
            summary=data,
        )


class ConsumptionsReportView(BaseReportView):
    required_permission = 'reports.view_consumptions'
    query_serializer_class = ConsumptionsReportQuerySerializer
    row_serializer_class = ReportSaleSerializer
    csv_filename = 'relatorio-consumacoes.csv'
    csv_headers = (
        'id', 'sale_number', 'status', 'beneficiary', 'subtotal', 'total',
        'created_at', 'cancelled_at', 'items', 'payments',
    )

    def get(self, request):
        filters, start, end = self.parse_query(request)
        sales = filtered_sales(
            branch=request.branch_context,
            start=start,
            end=end,
            operation_type=OperationType.CONSUMPTION,
            filters=filters,
        )
        include_cost = user_has_code(request, 'inventory.view_stock_costs')
        summary = consumption_summary(
            sales, include_cost=include_cost, filters=filters
        )
        data = {
            'count': summary['count'],
            'reference': decimal_string(summary['reference']),
            'charged': decimal_string(summary['charged']),
            'subsidy': decimal_string(summary['subsidy']),
            'quantity': decimal_string(summary['quantity'], 3),
        }
        if include_cost:
            data['historical_cost'] = decimal_string(summary['historical_cost'])
        return self.respond(
            request,
            rows=sale_rows(sales),
            period=canonical_datetime_range(start, end),
            summary=data,
        )


class CashReportView(BaseReportView):
    required_permission = 'reports.view_cash'
    query_serializer_class = CashReportQuerySerializer
    row_serializer_class = CashSessionReportSerializer
    csv_filename = 'relatorio-caixa.csv'
    csv_headers = (
        'id', 'opened_at', 'closed_at', 'status', 'register', 'operator', 'opening',
        'manual_entries', 'cash_payments', 'withdrawals', 'expected', 'informed', 'difference',
    )

    def get(self, request):
        filters, start, end = self.parse_query(request)
        sessions = list(filtered_cash_sessions(
            branch=request.branch_context, start=start, end=end, filters=filters
        ))
        fields = {
            'opening': 'opening_amount',
            'manual_entries': 'manual_entries',
            'cash_payments': 'cash_payments',
            'withdrawals': 'withdrawals',
            'expected': 'expected',
            'informed': 'closing_amount_informed',
            'difference': 'closing_difference',
        }
        summary = {'count': len(sessions)}
        summary.update({
            name: decimal_string(sum(
                (getattr(session, attribute) or Decimal('0.00')) for session in sessions
            ))
            for name, attribute in fields.items()
        })
        return self.respond(
            request,
            rows=sessions,
            period=canonical_datetime_range(start, end),
            summary=summary,
        )


def _withdrawal_summary_json(summary, *, include_groups=True):
    result = {'count': summary['count'], 'amount': decimal_string(summary['amount'])}
    if include_groups:
        result['by_category'] = [
            {
                'category': row['withdrawal_category'],
                'count': row['count'],
                'amount': decimal_string(row['amount']),
            }
            for row in summary['by_category']
        ]
    return result


class WithdrawalsReportView(BaseReportView):
    required_permission = 'reports.view_withdrawals'
    query_serializer_class = WithdrawalsReportQuerySerializer
    row_serializer_class = WithdrawalReportSerializer
    csv_filename = 'relatorio-sangrias.csv'
    csv_headers = (
        'id', 'created_at', 'amount', 'category', 'category_label', 'beneficiary',
        'operator', 'cash_register', 'result_effect', 'reason',
    )

    def get(self, request):
        filters, start, end = self.parse_query(request)
        rows = filtered_withdrawals(
            branch=request.branch_context, start=start, end=end, filters=filters
        )
        return self.respond(
            request,
            rows=rows,
            period=canonical_datetime_range(start, end),
            summary=_withdrawal_summary_json(withdrawal_summary(rows)),
        )


class InventoryMovementsReportView(BaseReportView):
    required_permission = 'reports.view_inventory'
    query_serializer_class = InventoryReportQuerySerializer
    row_serializer_class = InventoryMovementReportSerializer
    csv_filename = 'relatorio-movimentacoes-estoque.csv'
    csv_headers = (
        'id', 'created_at', 'movement_type', 'nature', 'operation_reference', 'product', 'previous_quantity', 'quantity',
        'final_quantity', 'reason', 'user', 'sale',
    )

    def get(self, request):
        filters, start, end = self.parse_query(request)
        rows = filtered_inventory_movements(
            branch=request.branch_context, start=start, end=end, filters=filters
        )
        totals = rows.aggregate(
            count=Count('id'),
            quantity=Coalesce(
                Sum('quantity'),
                Decimal('0.000'),
                output_field=DecimalField(max_digits=20, decimal_places=3),
            ),
        )
        return self.respond(
            request,
            rows=rows,
            period=canonical_datetime_range(start, end),
            summary={'count': totals['count'], 'quantity': decimal_string(totals['quantity'], 3)},
        )


class StockConsumptionReportView(BaseReportView):
    required_permission = 'reports.view_stock_consumption'
    query_serializer_class = StockConsumptionReportQuerySerializer
    row_serializer_class = StockConsumptionMovementSerializer
    csv_filename = 'relatorio-consumo-fisico.csv'
    csv_headers = (
        'id', 'created_at', 'origin', 'movement_type', 'nature', 'operation_reference', 'product', 'quantity',
        'reason', 'user', 'sale',
    )

    def serialize_rows(self, rows, request):
        return self.row_serializer_class(rows, many=True, context={'request': request}).data

    def get(self, request):
        filters, start, end = self.parse_query(request)
        rows, summary_rows = stock_consumption_report(
            branch=request.branch_context, start=start, end=end, filters=filters,
        )
        include_cost = user_has_code(request, 'inventory.view_stock_costs')
        summary = {
            'products': StockConsumptionSummarySerializer(
                summary_rows, many=True, context={'include_cost': include_cost}
            ).data,
            'count': rows.count(),
            'gross_quantity': decimal_string(sum((row['gross_quantity'] for row in summary_rows), Decimal('0.000')), 3),
            'returned_quantity': decimal_string(sum((row['returned_quantity'] for row in summary_rows), Decimal('0.000')), 3),
            'net_quantity': decimal_string(sum((row['net_quantity'] for row in summary_rows), Decimal('0.000')), 3),
        }
        if include_cost:
            summary['estimated_cost'] = decimal_string(sum((row['estimated_cost'] for row in summary_rows), Decimal('0.00')))
        return self.respond(
            request, rows=rows, period=canonical_datetime_range(start, end), summary=summary,
        )
