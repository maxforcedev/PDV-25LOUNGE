import csv
import io
import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db.models import Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.base.datetimes import canonical_datetime_range, parse_datetime_range
from apps.base.export_labels import export_label, export_value
from apps.base.audit import audit_log
from apps.base.report_exports import render_report_export, report_key_value_rows
from apps.base.pagination import StandardPagination
from apps.cash.models import (
    CashMovement, CashMovementType, CashRegister, CashSession, WithdrawalCategory,
)
from apps.cash.services import build_session_operational_summary
from apps.companies.rbac import OPERATING_PERMISSION_CODES
from apps.companies.selectors import branch_permission_codes, eligible_branch_users, user_has_company_permission
from apps.inventory.content import exact_sum
from apps.inventory.models import MovementType
from apps.products.models import Category, Product
from apps.sales.models import OperationType, PaymentMethod, Sale, SaleStatus
from apps.sales.serializers import readable_user_name

from .permissions import ReportsPermission
from .financials import FinancialAggregator
from .selectors import (
    _financial_sales,
    _scoped_sale_values,
    commercial_summary,
    cancellation_summary,
    consumption_groupings,
    consumption_summary,
    current_cash_sessions,
    dashboard_time_analysis,
    event_rows,
    filtered_cash_sessions,
    filtered_inventory_movements,
    filtered_sales,
    period_event_sales,
    stock_consumption_report,
    filtered_withdrawals,
    inventory_kpis,
    hourly_sales,
    operational_result,
    period_end_exclusive,
    receipt_summary,
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
    quantum = Decimal(1).scaleb(-places)
    return f'{value.quantize(quantum, rounding=ROUND_HALF_UP):.{places}f}'


def payment_distribution(rows, total_received):
    total_received = Decimal(total_received or 0)
    result = []
    for row in rows:
        amount = Decimal(row.get('payment_total', row.get('net_received', row.get('amount', 0))))
        result.append({
            'code': row.get('code', row.get('payment_method_code')),
            'name': row.get('name', row.get('payment_method_name')),
            'payment_total': decimal_string(amount),
            'percentage': decimal_string(
                amount * Decimal('100') / total_received
                if total_received > 0 else 0
            ),
            'amount': decimal_string(amount),
        })
    return result


def operational_result_data(request, summary, *, extra_keys=()):
    keys = (
        'sales_revenue', 'consumption_charged', 'effective_revenue', 'service_fee',
        'total_received', 'payment_total', 'reconciliation_delta',
        'costs_and_expenses', 'estimated_result', 'result', 'margin',
        'sales_revenue_inflows', 'sales_revenue_reversals',
        'consumption_charged_inflows', 'consumption_charged_reversals',
        'service_fee_inflows', 'service_fee_reversals',
        'payment_total_inflows', 'payment_total_reversals',
    ) + tuple(extra_keys)
    data = {
        key: decimal_string(summary[key]) if summary[key] is not None else None
        for key in keys if key in summary
    }
    if 'event_accounting' in summary:
        data['event_accounting'] = summary['event_accounting']
    for key in (
        'sales_inflow_count', 'sales_reversal_count',
        'consumption_inflow_count', 'consumption_reversal_count',
    ):
        if key in summary:
            data[key] = summary[key]
    can_view_commission = user_has_code(request, 'commissions.view')
    can_view_costs = user_has_code(request, 'inventory.view_stock_costs')
    if can_view_commission and 'commission' in summary:
        for key in ('commission', 'commission_inflows', 'commission_reversals'):
            if key in summary:
                data[key] = decimal_string(summary[key])
    if can_view_costs:
        for key in (
            'historical_sales_cogs', 'historical_sales_cogs_inflows',
            'historical_sales_cogs_reversals', 'historical_consumption_cogs',
            'historical_consumption_cogs_inflows',
            'historical_consumption_cogs_reversals',
        ):
            if key in summary:
                data[key] = decimal_string(summary[key])
    if can_view_commission and can_view_costs:
        for key in ('operating_expenses', 'fixed_cost'):
            if key in summary:
                data[key] = decimal_string(summary[key])
    return data


def user_has_code(request, code):
    if code not in OPERATING_PERMISSION_CODES:
        return request.user.is_superuser or user_has_company_permission(
            request.user, request.branch_context.company_id, code
        )
    return request.user.is_superuser or code in branch_permission_codes(
        request.user, request.branch_context.pk
    )


def safe_csv_cell(value):
    if value is None:
        return ''
    value = export_value(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    value = str(value)
    is_signed_number = False
    if value.startswith(('+', '-')):
        try:
            Decimal(value)
            is_signed_number = True
        except InvalidOperation:
            pass
    if value.startswith(('=', '+', '-', '@')) and not is_signed_number:
        value = "'" + value
    return value


def csv_response(filename, headers, rows):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(export_label(header) for header in headers)
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
        can_view_team = user_has_code(request, 'reports.view_team')
        can_view_sellers = can_view_team or (
            request.query_params.get('scope') == 'commissions'
            and user_has_code(request, 'commissions.view')
        )
        can_view_consumptions = any(user_has_code(request, code) for code in (
            'reports.view_consumptions', 'sales.view_consumption',
        ))
        can_view_withdrawals = user_has_code(request, 'reports.view_withdrawals')
        can_view_cash = user_has_code(request, 'reports.view_cash')
        can_view_result = user_has_code(request, 'reports.view_operational_result')
        can_view_inventory = any(user_has_code(request, code) for code in (
            'reports.view_inventory', 'reports.view_stock_consumption',
        ))
        can_view_sales_data = any(user_has_code(request, code) for code in (
            'reports.view_sales', 'reports.view_products', 'reports.view_receipts',
            'reports.view_discounts', 'reports.view_cancellations', 'dashboard.view',
            'reports.view_team', 'reports.view_prices', 'commissions.view',
        ))
        can_view_payment_data = any(user_has_code(request, code) for code in (
            'reports.view_sales', 'reports.view_receipts', 'reports.view_discounts',
            'reports.view_cancellations', 'dashboard.view', 'reports.view_team',
            'commissions.view',
        ))
        can_view_products = (
            can_view_sales_data or can_view_consumptions or can_view_inventory
        )
        users = User.objects.filter(
            is_active=True,
            archived_at__isnull=True,
            company_accesses__company_id=branch.company_id,
            company_accesses__is_active=True,
        ).distinct().order_by('first_name', 'last_name', 'id') if (
            can_view_consumptions or can_view_withdrawals
        ) else User.objects.none()
        operators = User.objects.filter(
            is_active=True,
            archived_at__isnull=True,
            branch_accesses__branch=branch,
            branch_accesses__is_active=True,
        ).distinct().order_by('first_name', 'last_name', 'id') if can_view_team else User.objects.none()
        products = Product.objects.filter(company_id=branch.company_id).order_by(
            'name', 'id'
        ) if can_view_products else Product.objects.none()
        categories = Category.objects.filter(company_id=branch.company_id).order_by(
            'sort_order', 'name', 'id'
        ) if can_view_products else Category.objects.none()
        payment_methods = PaymentMethod.objects.filter(
            company_id=branch.company_id
        ).order_by('name', 'id') if can_view_payment_data else PaymentMethod.objects.none()
        registers = CashRegister.objects.filter(branch=branch).order_by(
            'name', 'id'
        ) if (
            can_view_cash or can_view_withdrawals or can_view_result
        ) else CashRegister.objects.none()
        sessions = CashSession.objects.filter(branch=branch).select_related(
            'cash_register'
        ).order_by('-opened_at', '-id') if (
            can_view_cash or can_view_result
        ) else CashSession.objects.none()
        eligible_seller_ids = eligible_branch_users(
            branch, 'sales.create'
        ).values_list('id', flat=True)
        historical_seller_ids = Sale.objects.filter(
            branch=branch, seller_user__isnull=False
        ).values_list('seller_user_id', flat=True)
        sellers = User.objects.filter(
            Q(id__in=eligible_seller_ids) | Q(id__in=historical_seller_ids)
        ).distinct().order_by('first_name', 'last_name', 'id') if can_view_sellers else User.objects.none()
        return Response({
            'operators': [
                {'id': user.pk, 'name': readable_user_name(user)} for user in operators
            ],
            'sellers': [
                {'id': user.pk, 'name': readable_user_name(user)}
                for user in sellers
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
            ] if can_view_inventory else [],
            'withdrawal_categories': [
                {'value': value, 'label': label}
                for value, label in WithdrawalCategory.choices
            ] if can_view_withdrawals else [],
            'user_types': [
                {'value': value, 'label': label} for value, label in User.UserType.choices
            ] if can_view_consumptions else [],
            'sale_statuses': [
                {'value': value, 'label': label} for value, label in SaleStatus.choices
            ] if (can_view_sales_data or can_view_consumptions) else [],
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
        if request.query_params.get('export') in ('csv', 'xlsx', 'pdf'):
            data = self.serialize_rows(rows, request)
            headers = self.csv_headers
            if not user_has_code(request, 'commissions.view'):
                headers = tuple(
                    header for header in headers
                    if header not in ('commission', 'commission_amount')
                )
                summary = {
                    key: value for key, value in (summary or {}).items()
                    if key not in ('commission', 'commission_amount')
                }
            return self.export_response(
                request, headers=headers, rows=data, period=period, summary=summary,
            )
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

    def export_response(self, request, *, headers, rows, period=None, summary=None, filename=None, title=None):
        response = render_report_export(
            request, filename=filename or self.csv_filename,
            title=title or self.csv_filename.rsplit('.', 1)[0].replace('-', ' ').title(),
            headers=headers, rows=rows, period=period, summary=summary,
        )
        audit_log(
            actor=request.user, action='report.export', company=request.branch_context.company,
            branch=request.branch_context,
            metadata={'report': self.__class__.__name__, 'format': request.query_params['export']},
        )
        return response


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
        if request.query_params.get('export') in ('csv', 'xlsx', 'pdf') and not user_has_code(request, 'reports.export'):
            raise PermissionDenied('Você não possui permissão para exportar relatórios.')
        start, end = parse_datetime_range(request.query_params, default_today=True)
        branch = request.branch_context
        response = {'period': canonical_datetime_range(start, end)}
        try:
            latest_sales_page = int(request.query_params.get('latest_sales_page', 1))
        except (TypeError, ValueError):
            raise ValidationError({'latest_sales_page': 'Informe uma página válida.'})
        if latest_sales_page < 1:
            latest_sales_page = 1
        category = None
        if request.query_params.get('category'):
            try:
                category = int(request.query_params['category'])
            except (TypeError, ValueError):
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'category': 'Informe uma categoria válida.'})
            if not Category.objects.filter(pk=category, company_id=branch.company_id).exists():
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'category': 'Categoria fora da filial atual.'})
        response['filters'] = {
            'category': category,
            'categories': list(Category.objects.filter(
                company_id=branch.company_id, status='active'
            ).values('id', 'name').order_by('sort_order', 'name')),
        }

        can_view_consumptions = user_has_code(request, 'sales.view_consumption')
        item_filters = {'category': category} if category else {}
        sales = None
        dashboard_consumption_graph = None
        dashboard_consumption_reversals = None
        if user_has_code(request, 'sales.view'):
            sales = filtered_sales(
                branch=branch,
                start=start,
                end=end,
                operation_type=OperationType.SALE,
                filters={'category': category} if category else {},
            )
            sales_graph, sales_reversals = period_event_sales(
                branch=branch, start=start, end=end, filters=item_filters,
                operation_types=(OperationType.SALE,),
            )
            summary, _ = commercial_summary(
                sales_graph, item_filters, reversals=sales_reversals,
            )
            products, categories = sale_rankings(
                sales_graph, limit=10, filters=item_filters,
                reversals=sales_reversals,
            )
            can_view_team = user_has_code(request, 'reports.view_team')
            operator_groups = (
                sale_user_groups(
                    sales_graph, 'created_by', item_filters, sales_reversals,
                )
                if can_view_team else []
            )
            seller_groups = (
                sale_user_groups(
                    sales_graph, 'seller_user', item_filters, sales_reversals,
                )
                if can_view_team else []
            )
            _cancelled_rows, cancellations = cancellation_summary(
                branch=branch, start=start, end=end, filters=item_filters,
            )
            discount_count = summary['manual_discount_count']
            heatmap, current_comparison, previous_comparison = dashboard_time_analysis(
                sales_graph, branch=branch, start=start, end=end, category=category,
                reversals=sales_reversals,
            )
            if can_view_consumptions:
                (
                    dashboard_consumption_graph,
                    dashboard_consumption_reversals,
                ) = period_event_sales(
                    branch=branch,
                    start=start,
                    end=end,
                    filters={'category': category} if category else {},
                    operation_types=(OperationType.CONSUMPTION,),
                )
            dashboard_receipts = receipt_summary(
                branch=branch, start=start, end=end,
                filters={'category': category} if category else {},
                inflow_sales=sales_graph + (dashboard_consumption_graph or []),
                operation_types=(
                    (OperationType.SALE, OperationType.CONSUMPTION)
                    if can_view_consumptions else (OperationType.SALE,)
                ),
            )
            latest_count = sales.count()
            latest_total_pages = (latest_count + 9) // 10
            latest_sales_page = min(
                latest_sales_page, latest_total_pages or 1
            )
            latest_offset = (latest_sales_page - 1) * 10
            latest_rows = list(sale_rows(sales)[latest_offset:latest_offset + 10])
            distribution = payment_distribution(
                dashboard_receipts['payment_methods'], dashboard_receipts['total_received']
            )
            response['sales'] = {
                'event_accounting': dashboard_receipts['event_accounting'],
                'sales_revenue': decimal_string(dashboard_receipts['sales_revenue']),
                'consumption_charged': decimal_string(
                    dashboard_receipts['consumption_charged']
                ),
                'effective_revenue': decimal_string(
                    dashboard_receipts['effective_revenue']
                ),
                'total_received': decimal_string(dashboard_receipts['total_received']),
                'payment_total': decimal_string(dashboard_receipts['payment_total']),
                'reconciliation_delta': decimal_string(
                    dashboard_receipts['reconciliation_delta']
                ),
                'revenue': decimal_string(summary['sales_revenue']),
                'gross': decimal_string(summary['gross']),
                'count': summary['count'],
                'inflow_count': summary['inflow_count'],
                'reversal_count': summary['reversal_count'],
                'average': decimal_string(summary['average']),
                'ticket_average': decimal_string(summary['average']),
                'account_discount': decimal_string(summary['account_discount']),
                'item_discount': decimal_string(summary['item_discount']),
                'manual_discount': decimal_string(summary['manual_discount']),
                'manual_discount_count': discount_count,
                'promotion_discount': decimal_string(summary['promotion_discount']),
                'total_discount': decimal_string(summary['total_discount']),
                'service_fee': decimal_string(dashboard_receipts['service_fee']),
                'commission': decimal_string(summary['commission']),
                'customer_total': decimal_string(summary['customer_total']),
                'total_received_sales': decimal_string(summary['total_received_sales']),
                'payment_reconciliation_delta': decimal_string(
                    summary['payment_reconciliation_delta']
                ),
                'cancellations': {
                    'count': cancellations['count'],
                    'value': decimal_string(cancellations['value']),
                },
                'hourly_sales': [
                    {
                        'hour': row['hour'],
                        'count': row['count'],
                        'sales_revenue': decimal_string(row['sales_revenue']),
                        'effective_revenue': decimal_string(row['effective_revenue']),
                        'service_fee': decimal_string(row['service_fee']),
                        'total_received': decimal_string(row['total_received']),
                    }
                    for row in hourly_sales(
                        sales_graph, item_filters, sales_reversals,
                    )
                ],
                'payment_distribution': distribution,
                'payment_distribution_scope': (
                    'operational' if can_view_consumptions else 'sales_only'
                ),
                'top_products': [
                    {
                        **row, 'quantity': decimal_string(row['quantity'], 3),
                        'sales_revenue': decimal_string(row['sales_revenue']),
                        'revenue': decimal_string(row['sales_revenue']),
                    }
                    for row in products
                ],
                'top_categories': [
                    {
                        **row, 'quantity': decimal_string(row['quantity'], 3),
                        'sales_revenue': decimal_string(row['sales_revenue']),
                        'revenue': decimal_string(row['sales_revenue']),
                    }
                    for row in categories
                ],
                'top_sellers': [_group_json(row) for row in seller_groups[:10]],
                'top_operators': [_group_json(row) for row in operator_groups[:10]],
                'heatmap': [
                    {
                        **row, 'sales_revenue': decimal_string(row['sales_revenue']),
                        'revenue': decimal_string(row['sales_revenue']),
                        'average': decimal_string(row['average']),
                    }
                    for row in heatmap
                ],
                'weekly_comparison': {
                    'current': [{**row, 'sales_revenue': decimal_string(row['sales_revenue']), 'revenue': decimal_string(row['sales_revenue'])} for row in current_comparison],
                    'previous': [{**row, 'sales_revenue': decimal_string(row['sales_revenue']), 'revenue': decimal_string(row['sales_revenue'])} for row in previous_comparison],
                },
                'latest_sales': {
                    'count': latest_count,
                    'page': latest_sales_page,
                    'page_size': 10,
                    'total_pages': latest_total_pages,
                    'next_page': (
                        latest_sales_page + 1
                        if latest_offset + 10 < latest_count else None
                    ),
                    'previous_page': latest_sales_page - 1 if latest_sales_page > 1 else None,
                    'ordering': ('-created_at', '-id'),
                    'results': ReportSaleSerializer(
                        latest_rows, many=True, context={'request': request}
                    ).data,
                },
            }
            response['sales']['total_received_operational'] = decimal_string(
                dashboard_receipts['total_received']
            )
            response['sales']['operational_reconciliation_delta'] = decimal_string(
                dashboard_receipts['reconciliation_delta']
            )
            if not user_has_code(request, 'commissions.view'):
                response['sales'].pop('commission', None)
                for group in response['sales']['top_sellers'] + response['sales']['top_operators']:
                    for key in ('commission', 'commission_sale_count'):
                        group.pop(key, None)

        if can_view_consumptions:
            if dashboard_consumption_graph is None:
                (
                    dashboard_consumption_graph,
                    dashboard_consumption_reversals,
                ) = period_event_sales(
                    branch=branch,
                    start=start,
                    end=end,
                    filters={'category': category} if category else {},
                    operation_types=(OperationType.CONSUMPTION,),
                )
            summary = consumption_summary(dashboard_consumption_graph, filters={
                'category': category
            } if category else {}, reversals=dashboard_consumption_reversals)
            consumption_cancellations = FinancialAggregator(
                dashboard_consumption_reversals,
                {'category': category} if category else {},
            ).cancellations(operation_type=OperationType.CONSUMPTION)
            response['consumptions'] = {
                'event_accounting': summary['event_accounting'],
                'count': summary['count'],
                'inflow_count': summary['inflow_count'],
                'reversal_count': summary['reversal_count'],
                'reference': decimal_string(summary['reference']),
                'charged': decimal_string(summary['charged']),
                'sales_revenue': decimal_string(summary['sales_revenue']),
                'consumption_charged': decimal_string(summary['consumption_charged']),
                'effective_revenue': decimal_string(summary['effective_revenue']),
                'service_fee': decimal_string(summary['service_fee']),
                'total_received': decimal_string(summary['total_received']),
                'payment_total': decimal_string(summary['payment_total']),
                'reconciliation_delta': decimal_string(summary['reconciliation_delta']),
                'subsidy': decimal_string(summary['subsidy']),
                'cancellations': {
                    'count': consumption_cancellations['count'],
                    'reversed_total_received': decimal_string(
                        consumption_cancellations['reversed_total_received']
                    ),
                    'reversed_payment_total': decimal_string(
                        consumption_cancellations['reversed_payment_total']
                    ),
                },
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
            stock = inventory_kpis(
                branch, include_value=include_value, category=category,
            )
            if include_value:
                stock['inventory_value'] = decimal_string(stock['inventory_value'])
            response['inventory'] = stock
        if user_has_code(request, 'reports.view_operational_result'):
            result_sales = sales if sales is not None else filtered_sales(
                branch=branch,
                start=start,
                end=end,
                operation_type=OperationType.SALE,
                filters=item_filters,
            )
            result = operational_result(
                branch=branch, start=start, end=end, sales=result_sales,
                filters=item_filters,
            )
            response['operational_result'] = operational_result_data(request, result)
            if category is not None:
                for key in (
                    'result', 'estimated_result', 'margin', 'costs_and_expenses',
                    'historical_sales_cogs', 'historical_consumption_cogs',
                    'historical_sales_cogs_inflows',
                    'historical_sales_cogs_reversals',
                    'historical_consumption_cogs_inflows',
                    'historical_consumption_cogs_reversals',
                    'commission', 'commission_inflows', 'commission_reversals',
                    'operating_expenses', 'fixed_cost',
                ):
                    response['operational_result'].pop(key, None)
        if request.query_params.get('export') in ('csv', 'xlsx', 'pdf'):
            export = render_report_export(
                request, filename='dashboard.csv', title='Dashboard',
                headers=('indicator', 'value'), rows=report_key_value_rows(response),
                period=response['period'], summary=None,
            )
            audit_log(actor=request.user, action='report.export', company=branch.company, branch=branch,
                      metadata={'report': 'DashboardView', 'format': request.query_params['export']})
            return export
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
        'operation_id', 'operation_type', 'operation_key', 'event_type', 'event_at', 'event_sign', 'sale_number', 'channel', 'status',
        'operator', 'seller', 'subtotal',
        'promotion_discount_total', 'item_discount_total', 'discount',
        'sales_revenue', 'consumption_charged', 'effective_revenue', 'service_fee',
        'total_received', 'payment_total', 'reconciliation_delta', 'commission_amount',
        'created_at', 'cancelled_at',
        'items', 'payments',
    )

    def get(self, request):
        scope = request.query_params.get('scope', 'sales')
        filters, start, end = self.parse_query(request)
        can_view_team = user_has_code(request, 'reports.view_team')
        can_view_sellers = can_view_team or (
            scope == 'commissions' and user_has_code(request, 'commissions.view')
        )
        if not can_view_team and filters.get('operator') is not None:
            raise PermissionDenied(
                'Você não possui permissão para filtrar desempenho de operadores.'
            )
        if not can_view_sellers and filters.get('seller') is not None:
            raise PermissionDenied(
                'Você não possui permissão para filtrar desempenho de atendentes.'
            )
        sales_graph, sales_reversals = period_event_sales(
            branch=request.branch_context, start=start, end=end, filters=filters,
            operation_types=(OperationType.SALE,),
        )
        summary, _ = commercial_summary(
            sales_graph, filters, reversals=sales_reversals,
        )
        _cancelled_rows, cancellations = cancellation_summary(
            branch=request.branch_context,
            start=start,
            end=end,
            filters=filters,
        )
        products, categories = sale_rankings(
            sales_graph, limit=None if scope == 'products' else 10, filters=filters,
            reversals=sales_reversals,
        )
        operator_groups = (
            sale_user_groups(
                sales_graph, 'created_by', filters, sales_reversals,
            ) if can_view_team else []
        )
        seller_groups = (
            sale_user_groups(
                sales_graph, 'seller_user', filters, sales_reversals,
            ) if can_view_sellers else []
        )
        sales_receipts = receipt_summary(
            branch=request.branch_context, start=start, end=end, filters=filters,
            inflow_sales=sales_graph, operation_types=(OperationType.SALE,),
        )
        result = {
            'event_accounting': summary['event_accounting'],
            'gross': decimal_string(summary['gross']),
            'sales_revenue': decimal_string(summary['sales_revenue']),
            'consumption_charged': decimal_string(summary['consumption_charged']),
            'effective_revenue': decimal_string(summary['effective_revenue']),
            'total_received': decimal_string(summary['total_received']),
            'payment_total': decimal_string(summary['payment_total']),
            'reconciliation_delta': decimal_string(summary['reconciliation_delta']),
            'count': summary['count'],
            'inflow_count': summary['inflow_count'],
            'reversal_count': summary['reversal_count'],
            'average': decimal_string(summary['average']),
            'ticket_average': decimal_string(summary['average']),
            'account_discount': decimal_string(summary['account_discount']),
            'item_discount': decimal_string(summary['item_discount']),
            'manual_discount': decimal_string(summary['manual_discount']),
            'promotion_discount': decimal_string(summary['promotion_discount']),
            'total_discount': decimal_string(summary['total_discount']),
            'service_fee': decimal_string(summary['service_fee']),
            'commission': decimal_string(summary['commission']),
            'customer_total': decimal_string(summary['customer_total']),
            'total_received_sales': decimal_string(summary['total_received_sales']),
            'payment_reconciliation_delta': decimal_string(
                summary['payment_reconciliation_delta']
            ),
            'discount_reconstruction_delta': decimal_string(
                summary['discount_reconstruction_delta']
            ),
            'received_reconstruction_delta': decimal_string(
                summary['received_reconstruction_delta']
            ),
            'commission_sale_count': summary['commission_sale_count'],
            'commission_attendant_count': summary['commission_attendant_count'],
            'cancellations': {
                'count': cancellations['count'],
                'value': decimal_string(cancellations['value']),
                'reversed_effective_revenue': decimal_string(
                    cancellations['reversed_effective_revenue']
                ),
                'reversed_sales_revenue': decimal_string(
                    cancellations['reversed_sales_revenue']
                ),
                'reversed_consumption_charged': decimal_string(
                    cancellations['reversed_consumption_charged']
                ),
                'reversed_service_fee': decimal_string(
                    cancellations['reversed_service_fee']
                ),
                'reversed_total_received': decimal_string(
                    cancellations['reversed_total_received']
                ),
                'reversed_payment_total': decimal_string(
                    cancellations['reversed_payment_total']
                ),
                'reconciliation_delta': decimal_string(
                    cancellations['reconciliation_delta']
                ),
            },
            'payment_totals': [
                {
                    'code': row['code'],
                    'name': row['name'],
                    'payment_total': decimal_string(row['payment_total']),
                    'amount': decimal_string(row['payment_total']),
                }
                for row in sales_receipts['payment_methods']
            ],
            'product_ranking': [
                {
                    **row, 'quantity': decimal_string(row['quantity'], 3),
                    'sales_revenue': decimal_string(row['sales_revenue']),
                    'revenue': decimal_string(row['sales_revenue']),
                }
                for row in products
            ],
            'category_ranking': [
                {
                    **row, 'quantity': decimal_string(row['quantity'], 3),
                    'sales_revenue': decimal_string(row['sales_revenue']),
                    'revenue': decimal_string(row['sales_revenue']),
                }
                for row in categories
            ],
            'operator_groups': [_group_json(row) for row in operator_groups],
            'seller_groups': [_group_json(row) for row in seller_groups],
        }
        if scope == 'discounts':
            item_filters = {
                key: filters[key] for key in ('category', 'product') if filters.get(key)
            }
            discounted_graph = [
                sale for sale in sales_graph
                if _scoped_sale_values(sale, item_filters)['total_discount'] > 0
            ]
            discounted_reversals = [
                sale for sale in sales_reversals
                if _scoped_sale_values(sale, item_filters)['total_discount'] > 0
            ]
            discount_summary, _ = commercial_summary(
                discounted_graph, filters, reversals=discounted_reversals,
            )
            result.update({
                'count': discount_summary['discounted_count'],
                'inflow_count': discount_summary['inflow_count'],
                'reversal_count': discount_summary['reversal_count'],
                'gross': decimal_string(discount_summary['gross']),
                'account_discount': decimal_string(discount_summary['account_discount']),
                'item_discount': decimal_string(discount_summary['item_discount']),
                'manual_discount': decimal_string(discount_summary['manual_discount']),
                'promotion_discount': decimal_string(discount_summary['promotion_discount']),
                'total_discount': decimal_string(discount_summary['total_discount']),
                'sales_revenue': decimal_string(discount_summary['sales_revenue']),
                'consumption_charged': decimal_string(
                    discount_summary['consumption_charged']
                ),
                'effective_revenue': decimal_string(discount_summary['effective_revenue']),
                'service_fee': decimal_string(discount_summary['service_fee']),
                'total_received': decimal_string(discount_summary['total_received']),
                'payment_total': decimal_string(discount_summary['payment_total']),
                'reconciliation_delta': decimal_string(
                    discount_summary['reconciliation_delta']
                ),
                'total_received_sales': decimal_string(
                    discount_summary['total_received_sales']
                ),
                'customer_total': decimal_string(discount_summary['customer_total']),
                'discount_reconstruction_delta': decimal_string(
                    discount_summary['discount_reconstruction_delta']
                ),
                'received_reconstruction_delta': decimal_string(
                    discount_summary['received_reconstruction_delta']
                ),
            })
        if scope == 'receipts':
            receipts = receipt_summary(
                branch=request.branch_context, start=start, end=end, filters=filters,
            )
            result = {
                key: (
                    decimal_string(value) if isinstance(value, Decimal) else value
                )
                for key, value in receipts.items()
                if key != 'payment_methods'
            }
            result['payment_totals'] = [
                {
                    **row,
                    **{
                        key: decimal_string(row[key])
                        for key in (
                            'commercial_received', 'consumption_received',
                            'gross_received', 'reversals', 'net_received',
                            'sales_payment_total', 'consumption_payment_total',
                            'payment_total_before_reversals',
                            'reversal_payment_total', 'payment_total',
                        )
                    },
                }
                for row in receipts['payment_methods']
            ]
            if result.get('filtered_payment_method'):
                for key in ('subtotal', 'payment_total'):
                    result['filtered_payment_method'][key] = decimal_string(
                        result['filtered_payment_method'][key]
                    )
        if not user_has_code(request, 'commissions.view'):
            for key in (
                'commission', 'commission_sale_count', 'commission_attendant_count',
            ):
                result.pop(key, None)
            for group in result.get('operator_groups', []) + result.get('seller_groups', []):
                for key in ('commission', 'commission_sale_count'):
                    group.pop(key, None)
        if not can_view_team:
            result.pop('operator_groups', None)
        if not can_view_sellers:
            result.pop('seller_groups', None)
        summary_keys = {
            'products': {'product_ranking', 'category_ranking'},
            'receipts': set(result),
            'operators': {'operator_groups'},
            'sellers': {'seller_groups'},
            'commissions': {
                'seller_groups', 'commission', 'commission_sale_count',
                'commission_attendant_count', 'sales_revenue', 'effective_revenue',
                'service_fee', 'total_received', 'payment_total',
                'reconciliation_delta', 'inflow_count', 'reversal_count',
            },
            'discounts': {
                'account_discount', 'item_discount', 'manual_discount',
                'promotion_discount', 'total_discount', 'gross', 'count',
                'sales_revenue', 'effective_revenue', 'service_fee',
                'total_received', 'payment_total', 'reconciliation_delta',
                'discount_reconstruction_delta', 'inflow_count', 'reversal_count',
                'received_reconstruction_delta',
            },
        }.get(scope)
        if summary_keys is not None:
            result = {key: value for key, value in result.items() if key in summary_keys}
        if request.query_params.get('export') in ('csv', 'xlsx', 'pdf'):
            if scope == 'products':
                ranking_rows = [
                    {
                        'ranking_type': 'Produto',
                        'name': row['product_name'],
                        'internal_code': row['internal_code'],
                        'quantity': row['quantity'],
                        'sales_revenue': row['sales_revenue'],
                    }
                    for row in result.get('product_ranking', [])
                ] + [
                    {
                        'ranking_type': 'Categoria',
                        'name': row['category_name'],
                        'internal_code': '',
                        'quantity': row['quantity'],
                        'sales_revenue': row['sales_revenue'],
                    }
                    for row in result.get('category_ranking', [])
                ]
                return self.export_response(
                    request, filename='relatorio-produtos.csv', title='Relatório de produtos',
                    headers=('ranking_type', 'name', 'internal_code', 'quantity', 'sales_revenue'),
                    rows=ranking_rows, period=canonical_datetime_range(start, end), summary=result,
                )
            if scope == 'receipts':
                filtered_method = result.get('filtered_payment_method') or {}
                export_rows = [{
                    'row_type': 'reconciliation',
                    'name': 'Reconciliação do período',
                    'sales_revenue': result.get('sales_revenue'),
                    'consumption_charged': result.get('consumption_charged'),
                    'effective_revenue': result.get('effective_revenue'),
                    'service_fee': result.get('service_fee'),
                    'total_received': result.get('total_received'),
                    'payment_total': result.get('payment_total'),
                    'reconciliation_delta': result.get('reconciliation_delta'),
                }] + [
                    {
                        'row_type': 'payment_method',
                        **row,
                        'is_filtered_method': (
                            row['code'] == filtered_method.get('code')
                            if filtered_method else ''
                        ),
                        'filtered_subtotal_is_integral_revenue': (
                            False if row['code'] == filtered_method.get('code') else ''
                        ),
                    }
                    for row in result.get('payment_totals', [])
                ]
                return self.export_response(
                    request, filename='relatorio-recebimentos.csv', title='Relatório de recebimentos',
                    headers=(
                        'row_type', 'code', 'name', 'sales_revenue',
                        'consumption_charged', 'effective_revenue', 'service_fee',
                        'total_received', 'reconciliation_delta',
                        'sales_payment_total',
                        'consumption_payment_total', 'payment_total_before_reversals',
                        'reversal_payment_total', 'payment_total', 'is_filtered_method',
                        'filtered_subtotal_is_integral_revenue',
                    ),
                    rows=export_rows, period=canonical_datetime_range(start, end), summary=result,
                )
            if scope in ('operators', 'sellers', 'commissions'):
                key = 'operator_groups' if scope == 'operators' else 'seller_groups'
                group_rows = [
                    {**row, 'name': row.get('user', {}).get('name', '')}
                    for row in result.get(key, [])
                ]
                headers = (
                    'name', 'count', 'inflow_count', 'reversal_count',
                    'gross', 'sales_revenue', 'effective_revenue',
                    'service_fee', 'total_received', 'payment_total',
                    'reconciliation_delta',
                    'cancellation_count', 'cancellation_value',
                )
                if scope == 'commissions':
                    headers += ('commission',)
                return self.export_response(
                    request, filename=f'relatorio-{scope}.csv', title=f'Relatório {scope}',
                    headers=headers, rows=group_rows, period=canonical_datetime_range(start, end), summary=result,
                )
        if scope == 'discounts':
            detail_rows = event_rows(discounted_graph, discounted_reversals)
        else:
            detail_rows = (
                event_rows(sales_graph, sales_reversals)
                if scope in ('overview', 'sales') else []
            )
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
        if not user_has_code(request, 'reports.view_team') and any(
            filters.get(key) is not None for key in ('operator', 'seller')
        ):
            raise PermissionDenied(
                'Você não possui permissão para filtrar desempenho da equipe.'
            )
        rows, totals = cancellation_summary(
            branch=request.branch_context, start=start, end=end, filters=filters,
        )
        detail_rows = rows.select_related(
            'created_by', 'seller_user', 'discount_approved_by', 'beneficiary_user'
        ).prefetch_related('items__product__category', 'payments').order_by(
            '-cancelled_at', '-id'
        )
        detail_rows = event_rows([], list(detail_rows))
        return self.respond(
            request, rows=detail_rows, period=canonical_datetime_range(start, end),
            summary={
                'count': totals['count'],
                'value': decimal_string(totals['value']),
                'reversed_sales_revenue': decimal_string(
                    totals['reversed_sales_revenue']
                ),
                'reversed_consumption_charged': decimal_string(
                    totals['reversed_consumption_charged']
                ),
                'reversed_effective_revenue': decimal_string(
                    totals['reversed_effective_revenue']
                ),
                'reversed_service_fee': decimal_string(totals['reversed_service_fee']),
                'reversed_total_received': decimal_string(
                    totals['reversed_total_received']
                ),
                'reversed_payment_total': decimal_string(
                    totals['reversed_payment_total']
                ),
                'reconciliation_delta': decimal_string(totals['reconciliation_delta']),
            },
        )


def _group_json(row):
    return {
        **row,
        **{
            field: decimal_string(row[field])
            for field in (
                'gross', 'manual_discount', 'promotion_discount', 'total_discount',
                'sales_revenue', 'consumption_charged', 'effective_revenue',
                'service_fee', 'commission', 'customer_total', 'total_received',
                'payment_total', 'reconciliation_delta',
                'payment_reconciliation_delta', 'average',
                'cancellation_value',
            )
            if field in row
        },
    }


def _consumption_group_json(row):
    return {
        **row,
        **{
            key: decimal_string(row[key])
            for key in (
                'reference', 'charged', 'benefit', 'sales_revenue',
                'consumption_charged', 'effective_revenue', 'service_fee',
                'total_received',
            )
        },
    }


def _remove_commission_fields(data):
    data.pop('commission', None)
    return data


def _sum_operational(rows, *path):
    total = Decimal('0.00')
    for row in rows:
        value = row.get('operational_summary', {})
        for key in path:
            value = value.get(key, {}) if isinstance(value, dict) else {}
        if value not in ({}, None, ''):
            total += Decimal(value)
    return decimal_string(total)


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
        data = operational_result_data(
            request, summary,
            extra_keys=(
                'gross', 'promotion_discount', 'item_discount', 'account_discount',
                'manual_discount', 'discounts', 'sales_revenue_inflows',
                'sales_revenue_reversals', 'consumption_charged_inflows',
                'consumption_charged_reversals', 'service_fee_inflows',
                'service_fee_reversals', 'payment_total_inflows',
                'payment_total_reversals',
            ),
        )
        for key in (
            'sales_inflow_count', 'sales_reversal_count',
            'consumption_inflow_count', 'consumption_reversal_count',
        ):
            data[key] = summary[key]
        data['unclassified_withdrawals'] = {
            'count': summary['unclassified_withdrawals']['count'],
            'amount': decimal_string(summary['unclassified_withdrawals']['amount']),
        }
        data['cash_session'] = session.pk if session else None
        data['event_accounting'] = summary['event_accounting']
        data['notice'] = (
            'Entradas pela criação e reversões pela data do cancelamento. '
            'Estimativa operacional; não constitui DRE contábil.'
        )
        if request.query_params.get('export') in ('csv', 'xlsx', 'pdf'):
            labels = {
                'sales_inflow_count': 'Vendas - entradas',
                'sales_reversal_count': 'Vendas - reversões',
                'consumption_inflow_count': 'Consumações - entradas',
                'consumption_reversal_count': 'Consumações - reversões',
                'gross': 'Valor bruto a preço de tabela',
                'promotion_discount': '(-) Descontos promocionais',
                'item_discount': '(-) Descontos manuais por item',
                'account_discount': '(-) Descontos manuais na conta',
                'sales_revenue_inflows': 'Faturamento de vendas - entradas',
                'sales_revenue_reversals': 'Faturamento de vendas - reversões',
                'sales_revenue': '= Faturamento de vendas',
                'consumption_charged_inflows': 'Consumações cobradas - entradas',
                'consumption_charged_reversals': 'Consumações cobradas - reversões',
                'consumption_charged': '(+) Consumações cobradas',
                'effective_revenue': '= Faturamento efetivo',
                'service_fee_inflows': 'Taxa de serviço - entradas',
                'service_fee_reversals': 'Taxa de serviço - reversões',
                'service_fee': 'Taxa de serviço',
                'total_received': '= Total recebido',
                'payment_total_inflows': 'Pagamentos - entradas',
                'payment_total_reversals': 'Pagamentos - reversões',
                'payment_total': 'Total dos pagamentos',
                'reconciliation_delta': 'Delta de reconciliação',
                'historical_sales_cogs_inflows': 'CMV histórico de vendas - entradas',
                'historical_sales_cogs_reversals': 'CMV histórico de vendas - reversões',
                'historical_sales_cogs': '(-) CMV histórico de vendas',
                'historical_consumption_cogs_inflows': 'CMV histórico de consumações - entradas',
                'historical_consumption_cogs_reversals': 'CMV histórico de consumações - reversões',
                'historical_consumption_cogs': '(-) CMV histórico de consumações',
                'commission_inflows': 'Comissões - entradas',
                'commission_reversals': 'Comissões - reversões',
                'commission': '(-) Comissões',
                'operating_expenses': '(-) Despesas operacionais',
                'fixed_cost': '(-) Custo fixo rateado',
                'costs_and_expenses': '(-) Custos e despesas',
                'estimated_result': '= Resultado estimado',
                'margin': 'Margem estimada (%)',
            }
            rows = [
                {'statement': label, 'value': data[key]}
                for key, label in labels.items() if key in data
            ]
            rows.append({'statement': 'Observação', 'value': data['notice']})
            return self.export_response(
                request, headers=('statement', 'value'), rows=rows,
                period=canonical_datetime_range(start, end), summary=data,
            )
        return self.respond(
            request,
            rows=[],
            period=canonical_datetime_range(start, end),
            summary=data,
        )


class ConsumptionsReportView(BaseReportView):
    required_permission = 'reports.view_consumptions'
    query_serializer_class = ConsumptionsReportQuerySerializer
    row_serializer_class = ReportSaleSerializer
    csv_filename = 'relatorio-consumacoes.csv'
    csv_headers = (
        'id', 'event_type', 'event_at', 'event_sign', 'sale_number', 'channel', 'status',
        'beneficiary', 'subtotal',
        'sales_revenue', 'consumption_charged', 'effective_revenue', 'service_fee',
        'total_received', 'payment_total', 'reconciliation_delta',
        'created_at', 'cancelled_at', 'items', 'payments',
    )

    def get(self, request):
        filters, start, end = self.parse_query(request)
        consumption_graph, consumption_reversals = period_event_sales(
            branch=request.branch_context, start=start, end=end, filters=filters,
            operation_types=(OperationType.CONSUMPTION,),
        )
        include_cost = user_has_code(request, 'inventory.view_stock_costs')
        summary = consumption_summary(
            consumption_graph, include_cost=include_cost, filters=filters,
            reversals=consumption_reversals,
        )
        consumption_cancellations = FinancialAggregator(
            consumption_reversals, filters
        ).cancellations(operation_type=OperationType.CONSUMPTION)
        data = {
            'event_accounting': summary['event_accounting'],
            'count': summary['count'],
            'inflow_count': summary['inflow_count'],
            'reversal_count': summary['reversal_count'],
            'reference': decimal_string(summary['reference']),
            'charged': decimal_string(summary['charged']),
            'sales_revenue': decimal_string(summary['sales_revenue']),
            'consumption_charged': decimal_string(summary['consumption_charged']),
            'effective_revenue': decimal_string(summary['effective_revenue']),
            'service_fee': decimal_string(summary['service_fee']),
            'total_received': decimal_string(summary['total_received']),
            'payment_total': decimal_string(summary['payment_total']),
            'reconciliation_delta': decimal_string(summary['reconciliation_delta']),
            'subsidy': decimal_string(summary['subsidy']),
            'benefit': decimal_string(summary['benefit']),
            'quantity': decimal_string(summary['quantity'], 3),
            'payment_totals': [
                {
                    **row,
                    'payment_total': decimal_string(row['amount']),
                    'amount': decimal_string(row['amount']),
                }
                for row in summary['payments']
            ],
            'payment_reconciliation_delta': decimal_string(
                summary['payment_reconciliation_delta']
            ),
            'cancellations': {
                'count': consumption_cancellations['count'],
                'reversed_consumption_charged': decimal_string(
                    consumption_cancellations['reversed_consumption_charged']
                ),
                'reversed_total_received': decimal_string(
                    consumption_cancellations['reversed_total_received']
                ),
                'reversed_payment_total': decimal_string(
                    consumption_cancellations['reversed_payment_total']
                ),
                'reconciliation_delta': decimal_string(
                    consumption_cancellations['reconciliation_delta']
                ),
            },
        }
        if include_cost:
            data['historical_cost'] = decimal_string(summary['historical_cost'])
            data['historical_consumption_cogs'] = data['historical_cost']
        beneficiary_groups, user_type_groups = consumption_groupings(
            consumption_graph, filters, consumption_reversals,
        )
        data['beneficiary_groups'] = [
            _consumption_group_json(row) for row in beneficiary_groups
        ]
        data['user_type_groups'] = [
            _consumption_group_json(row) for row in user_type_groups
        ]
        return self.respond(
            request,
            rows=event_rows(consumption_graph, consumption_reversals),
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
        'manual_entries', 'sale_cash', 'consumption_cash', 'cash_reversals',
        'cash_cancellations', 'cash_payments', 'withdrawals', 'expected', 'informed',
        'difference',
    )

    def get(self, request):
        filters, start, end = self.parse_query(request)
        sessions = list(filtered_cash_sessions(
            branch=request.branch_context, start=start, end=end, filters=filters
        ))
        session_ids = [session.pk for session in sessions]
        session_sales = list(_financial_sales(
            Sale.objects.filter(cash_session_id__in=session_ids)
        ))
        sales_by_session = {}
        for sale in session_sales:
            sales_by_session.setdefault(sale.cash_session_id, []).append(sale)
        for session in sessions:
            session._report_operational_summary = build_session_operational_summary(
                session, sales_by_session.get(session.pk, [])
            )
        fields = {
            'opening': 'opening_amount',
            'manual_entries': 'manual_entries',
            'sale_cash': 'sale_cash',
            'consumption_cash': 'consumption_cash',
            'cash_reversals': 'cash_reversals',
            'cash_payments': 'cash_payments',
            'withdrawals': 'withdrawals',
            'expected': 'expected',
            'informed': 'closing_amount_informed',
            'difference': 'closing_difference',
        }
        complete_session_totals = {
            name: decimal_string(sum(
                (getattr(session, attribute) or Decimal('0.00')) for session in sessions
            ))
            for name, attribute in fields.items()
        }
        serialized = self.serialize_rows(sessions, request)
        end_exclusive = period_end_exclusive(end)
        clipped = receipt_summary(
            branch=request.branch_context, start=start, end=end, filters={},
            cash_session_ids=session_ids,
            inflow_sales=[
                sale for sale in session_sales
                if start <= sale.created_at < end_exclusive
            ],
        )
        clipped_movements = CashMovement.objects.filter(
            cash_session_id__in=session_ids,
            created_at__gte=start,
            created_at__lt=end_exclusive,
        ).aggregate(
            manual_entries=Coalesce(
                Sum('amount', filter=Q(movement_type=CashMovementType.MANUAL_ENTRY)),
                Decimal('0.00'), output_field=DecimalField(max_digits=20, decimal_places=2),
            ),
            withdrawals=Coalesce(
                Sum('amount', filter=Q(movement_type=CashMovementType.WITHDRAWAL)),
                Decimal('0.00'), output_field=DecimalField(max_digits=20, decimal_places=2),
            ),
        )
        summary = {
            'count': len(sessions),
            'session_rows_scope': 'complete_session',
            'top_summary_scope': 'requested_period_events',
            'complete_session_totals': complete_session_totals,
            'sales_count': clipped['sales_count'],
            'consumption_count': clipped['consumption_count'],
            'sales_revenue': decimal_string(clipped['sales_revenue']),
            'consumption_charged': decimal_string(clipped['consumption_charged']),
            'effective_revenue': decimal_string(clipped['effective_revenue']),
            'service_fee': decimal_string(clipped['service_fee']),
            'total_received': decimal_string(clipped['total_received']),
            'payment_total': decimal_string(clipped['payment_total']),
            'sales_received': decimal_string(clipped['sales_received']),
            'operational_received': decimal_string(clipped['total_received']),
            'reversals': decimal_string(clipped['reversals']),
            'reconciliation_delta': decimal_string(clipped['reconciliation_delta']),
            'manual_entries': decimal_string(clipped_movements['manual_entries']),
            'withdrawals': decimal_string(clipped_movements['withdrawals']),
            'opening': complete_session_totals['opening'],
            'expected': complete_session_totals['expected'],
            'informed': complete_session_totals['informed'],
            'difference': complete_session_totals['difference'],
        }
        summary['payment_totals'] = [
            {
                **row,
                **{
                    key: decimal_string(row[key])
                    for key in (
                        'commercial_received', 'consumption_received',
                        'gross_received', 'reversals', 'net_received',
                        'sales_payment_total', 'consumption_payment_total',
                        'payment_total_before_reversals',
                        'reversal_payment_total', 'payment_total',
                    )
                },
            }
            for row in clipped['payment_methods']
        ]
        if user_has_code(request, 'commissions.view'):
            clipped_sales = [
                sale for sale in session_sales
                if start <= sale.created_at < end_exclusive
            ]
            clipped_reversals = [
                sale for sale in session_sales
                if (
                    sale.status == SaleStatus.CANCELLED
                    and sale.cancelled_at
                    and start <= sale.cancelled_at < end_exclusive
                )
            ]
            summary['commission'] = decimal_string(
                FinancialAggregator(clipped_sales).operational_statement(
                    reversal_sales=clipped_reversals
                )['commission']
            )
        if request.query_params.get('export') in ('csv', 'xlsx', 'pdf'):
            export_rows = [{
                'scope': 'requested_period',
                'period_start': start,
                'period_end': end,
                'period_sales_count': summary['sales_count'],
                'period_sales_revenue': summary['sales_revenue'],
                'period_consumption_charged': summary['consumption_charged'],
                'period_effective_revenue': summary['effective_revenue'],
                'period_service_fee': summary['service_fee'],
                'period_total_received': summary['total_received'],
                'period_payment_total': summary['payment_total'],
                'period_reconciliation_delta': summary['reconciliation_delta'],
                'period_consumption_count': summary['consumption_count'],
                'period_reversals': summary['reversals'],
                'period_manual_entries': summary['manual_entries'],
                'period_withdrawals': summary['withdrawals'],
                'period_payment_totals': summary['payment_totals'],
                'period_commission': summary.get('commission'),
            }]
            for row in serialized:
                operational = row.get('operational_summary', {})
                sales_summary = operational.get('sales', {})
                consumption = operational.get('consumptions', {})
                export_row = {
                    'scope': 'complete_session_values',
                    'session_id': row.get('id'),
                    'session_opened_at': row.get('opened_at'),
                    'session_closed_at': row.get('closed_at'),
                    'session_status': row.get('status'),
                    'session_register': row.get('register'),
                    'session_operator': row.get('operator'),
                    'complete_session_opening': row.get('opening'),
                    'complete_session_manual_entries': row.get('manual_entries'),
                    'complete_session_sale_cash': row.get('sale_cash'),
                    'complete_session_consumption_cash': row.get('consumption_cash'),
                    'complete_session_cash_reversals': row.get('cash_reversals'),
                    'complete_session_withdrawals': row.get('withdrawals'),
                    'complete_session_expected': row.get('expected'),
                    'complete_session_informed': row.get('informed'),
                    'complete_session_difference': row.get('difference'),
                    'complete_session_sales_count': sales_summary.get('count', 0),
                    'complete_session_sales_revenue': operational.get('sales_revenue', '0.00'),
                    'complete_session_consumption_charged': operational.get('consumption_charged', '0.00'),
                    'complete_session_effective_revenue': operational.get('effective_revenue', '0.00'),
                    'complete_session_service_fee': operational.get('service_fee', '0.00'),
                    'complete_session_total_received': operational.get('total_received', '0.00'),
                    'complete_session_payment_total': operational.get('payment_total', '0.00'),
                    'complete_session_reconciliation_delta': operational.get('reconciliation_delta', '0.00'),
                    'complete_session_consumption_count': consumption.get('count', 0),
                    'complete_session_payment_totals': operational.get('payment_totals', []),
                    'complete_session_commission': sales_summary.get('commission'),
                }
                export_rows.append(export_row)
            headers = (
                'scope', 'period_start', 'period_end', 'period_sales_count',
                'period_sales_revenue', 'period_consumption_charged',
                'period_effective_revenue', 'period_service_fee',
                'period_total_received', 'period_payment_total',
                'period_reconciliation_delta', 'period_consumption_count',
                'period_reversals', 'period_manual_entries',
                'period_withdrawals', 'period_payment_totals',
                'session_id', 'session_opened_at', 'session_closed_at',
                'session_status', 'session_register', 'session_operator',
                'complete_session_opening', 'complete_session_manual_entries',
                'complete_session_sale_cash', 'complete_session_consumption_cash',
                'complete_session_cash_reversals', 'complete_session_withdrawals',
                'complete_session_expected', 'complete_session_informed',
                'complete_session_difference', 'complete_session_sales_count',
                'complete_session_sales_revenue',
                'complete_session_consumption_charged',
                'complete_session_effective_revenue', 'complete_session_service_fee',
                'complete_session_total_received', 'complete_session_payment_total',
                'complete_session_reconciliation_delta',
                'complete_session_consumption_count',
                'complete_session_payment_totals',
            )
            if user_has_code(request, 'commissions.view'):
                headers += ('period_commission', 'complete_session_commission')
            return self.export_response(
                request, headers=headers, rows=export_rows,
                period=canonical_datetime_range(start, end), summary=summary,
            )
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
                'category_label': WithdrawalCategory(row['withdrawal_category']).label,
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
        'id', 'created_at', 'amount', 'category_label', 'beneficiary',
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
        'final_quantity', 'equivalent_quantity', 'legacy_equivalent_quantity',
        'exact_content_equivalent_quantity', 'previous_content', 'content_quantity',
        'final_content', 'package_content', 'content_unit', 'complete_packages',
        'residual_content', 'reason', 'user', 'sale',
    )

    def get(self, request):
        filters, start, end = self.parse_query(request)
        rows = filtered_inventory_movements(
            branch=request.branch_context, start=start, end=end, filters=filters
        )
        movements = list(rows)
        equivalent_quantity = exact_sum(
            movement.equivalent_quantity() for movement in movements
        )
        legacy_equivalent_quantity = exact_sum(
            quantity
            for movement in movements
            if (quantity := movement.legacy_equivalent_quantity()) is not None
        )
        exact_content_equivalent_quantity = exact_sum(
            quantity
            for movement in movements
            if (quantity := movement.exact_content_equivalent_quantity()) is not None
        )
        content_by_unit = {}
        for movement in movements:
            if movement.content_quantity is None:
                continue
            unit = movement.stock.product.fraction_config.content_unit
            content_by_unit[unit] = (
                content_by_unit.get(unit, Decimal('0')) + movement.content_quantity
            )
        return self.respond(
            request,
            rows=movements,
            period=canonical_datetime_range(start, end),
            summary={
                'count': len(movements),
                'quantity': format(equivalent_quantity, 'f'),
                'equivalent_quantity': format(equivalent_quantity, 'f'),
                'legacy_equivalent_quantity': format(
                    legacy_equivalent_quantity, 'f'
                ),
                'exact_content_equivalent_quantity': format(
                    exact_content_equivalent_quantity, 'f'
                ),
                'combined_exact_equivalent_total': format(
                    equivalent_quantity, 'f'
                ),
                'content_by_unit': {
                    unit: format(value, 'f')
                    for unit, value in sorted(content_by_unit.items())
                },
            },
        )


class StockConsumptionReportView(BaseReportView):
    required_permission = 'reports.view_stock_consumption'
    query_serializer_class = StockConsumptionReportQuerySerializer
    row_serializer_class = StockConsumptionMovementSerializer
    csv_filename = 'relatorio-consumo-fisico.csv'
    csv_headers = (
        'id', 'created_at', 'origin', 'movement_type', 'nature', 'operation_reference', 'product', 'quantity',
        'equivalent_quantity', 'legacy_equivalent_quantity',
        'exact_content_equivalent_quantity', 'content_quantity',
        'package_content', 'content_unit',
        'complete_packages', 'residual_content', 'reason', 'user', 'sale',
    )

    def serialize_rows(self, rows, request):
        return self.row_serializer_class(rows, many=True, context={'request': request}).data

    def get(self, request):
        filters, start, end = self.parse_query(request)
        rows, summary_rows = stock_consumption_report(
            branch=request.branch_context, start=start, end=end, filters=filters,
        )
        include_cost = user_has_code(request, 'inventory.view_stock_costs')
        legacy_gross = exact_sum(
            row['legacy_gross_equivalent_quantity'] for row in summary_rows
        )
        legacy_returned = exact_sum(
            row['legacy_returned_equivalent_quantity'] for row in summary_rows
        )
        legacy_net = exact_sum(
            row['legacy_net_equivalent_quantity'] for row in summary_rows
        )
        exact_gross = exact_sum(
            row['exact_gross_equivalent_quantity'] for row in summary_rows
        )
        exact_returned = exact_sum(
            row['exact_returned_equivalent_quantity'] for row in summary_rows
        )
        exact_net = exact_sum(
            row['exact_net_equivalent_quantity'] for row in summary_rows
        )
        combined_net = exact_sum(row['net_quantity'] for row in summary_rows)
        summary = {
            'products': StockConsumptionSummarySerializer(
                summary_rows, many=True, context={'include_cost': include_cost}
            ).data,
            'count': rows.count(),
            'gross_quantity': format(exact_sum(row['gross_quantity'] for row in summary_rows), 'f'),
            'returned_quantity': format(exact_sum(row['returned_quantity'] for row in summary_rows), 'f'),
            'net_quantity': format(combined_net, 'f'),
            'legacy_gross_equivalent_quantity': format(legacy_gross, 'f'),
            'legacy_returned_equivalent_quantity': format(legacy_returned, 'f'),
            'legacy_equivalent_quantity': format(legacy_net, 'f'),
            'exact_gross_equivalent_quantity': format(exact_gross, 'f'),
            'exact_returned_equivalent_quantity': format(exact_returned, 'f'),
            'exact_content_equivalent_quantity': format(exact_net, 'f'),
            'combined_exact_equivalent_total': format(combined_net, 'f'),
            'content_by_unit': {
                unit: {
                    'gross_content': format(exact_sum(
                        row['gross_content'] for row in summary_rows
                        if row['content_unit'] == unit
                    ), 'f'),
                    'returned_content': format(exact_sum(
                        row['returned_content'] for row in summary_rows
                        if row['content_unit'] == unit
                    ), 'f'),
                    'net_content': format(exact_sum(
                        row['net_content'] for row in summary_rows
                        if row['content_unit'] == unit
                    ), 'f'),
                }
                for unit in sorted({
                    row['content_unit'] for row in summary_rows if row['content_unit']
                })
            },
        }
        if include_cost:
            summary['estimated_cost'] = decimal_string(sum((row['estimated_cost'] for row in summary_rows), Decimal('0.00')))
        if request.query_params.get('export') in ('csv', 'xlsx', 'pdf'):
            product_rows = StockConsumptionSummarySerializer(
                summary_rows, many=True, context={'include_cost': include_cost}
            ).data
            export_rows = [
                {
                    'product_name': row['product']['name'],
                    'internal_code': row['product']['internal_code'],
                    'category': row['product']['category']['name'],
                    'unit': row['product']['unit'],
                    'gross_quantity': row['gross_quantity'],
                    'returned_quantity': row['returned_quantity'],
                    'net_quantity': row['net_quantity'],
                    'legacy_gross_equivalent_quantity': row['legacy_gross_equivalent_quantity'],
                    'legacy_returned_equivalent_quantity': row['legacy_returned_equivalent_quantity'],
                    'legacy_net_equivalent_quantity': row['legacy_net_equivalent_quantity'],
                    'exact_gross_equivalent_quantity': row['exact_gross_equivalent_quantity'],
                    'exact_returned_equivalent_quantity': row['exact_returned_equivalent_quantity'],
                    'exact_net_equivalent_quantity': row['exact_net_equivalent_quantity'],
                    'combined_exact_equivalent_total': row['combined_exact_equivalent_total'],
                    'gross_content': row['gross_content'],
                    'returned_content': row['returned_content'],
                    'net_content': row['net_content'],
                    'package_content': row['package_content'],
                    'content_unit': row['content_unit'],
                    'complete_packages': row['complete_packages'],
                    'residual_content': row['residual_content'],
                    'movement_count': row['movement_count'],
                    **(
                        {'estimated_cost': row['estimated_cost']}
                        if 'estimated_cost' in row else {}
                    ),
                }
                for row in product_rows
            ]
            headers = (
                'product_name', 'internal_code', 'category', 'unit',
                'gross_quantity', 'returned_quantity', 'net_quantity',
                'legacy_gross_equivalent_quantity',
                'legacy_returned_equivalent_quantity',
                'legacy_net_equivalent_quantity',
                'exact_gross_equivalent_quantity',
                'exact_returned_equivalent_quantity',
                'exact_net_equivalent_quantity',
                'combined_exact_equivalent_total',
                'gross_content', 'returned_content', 'net_content',
                'package_content', 'content_unit', 'complete_packages',
                'residual_content',
                'movement_count',
            )
            if include_cost:
                headers += ('estimated_cost',)
            return self.export_response(
                request, headers=headers, rows=export_rows,
                period=canonical_datetime_range(start, end), summary=summary,
            )
        return self.respond(
            request, rows=rows, period=canonical_datetime_range(start, end), summary=summary,
        )
