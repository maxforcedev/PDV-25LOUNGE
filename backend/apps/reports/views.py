import csv
import io
import json
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.base.datetimes import canonical_datetime_range, parse_datetime_range
from apps.base.export_labels import export_label, export_value
from apps.base.pagination import StandardPagination
from apps.cash.models import (
    CashMovement, CashMovementType, CashRegister, CashSession, WithdrawalCategory,
)
from apps.cash.services import build_session_operational_summary
from apps.companies.rbac import OPERATING_PERMISSION_CODES
from apps.companies.selectors import branch_permission_codes, eligible_branch_users, user_has_company_permission
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
    filtered_cash_sessions,
    filtered_inventory_movements,
    filtered_sales,
    stock_consumption_report,
    filtered_withdrawals,
    inventory_kpis,
    hourly_sales,
    operational_result,
    payment_totals,
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
    if value.startswith(('=', '+', '-', '@')):
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
        eligible_seller_ids = eligible_branch_users(
            branch, 'sales.create'
        ).values_list('id', flat=True)
        historical_seller_ids = Sale.objects.filter(
            branch=branch, seller_user__isnull=False
        ).values_list('seller_user_id', flat=True)
        sellers = User.objects.filter(
            Q(id__in=eligible_seller_ids) | Q(id__in=historical_seller_ids)
        ).distinct().order_by('first_name', 'last_name', 'id')
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
        dashboard_consumption_graph = None
        if user_has_code(request, 'sales.view'):
            sales = filtered_sales(
                branch=branch,
                start=start,
                end=end,
                operation_type=OperationType.SALE,
                filters={'category': category} if category else {},
            )
            sales_graph = list(_financial_sales(sales))
            item_filters = {'category': category} if category else {}
            summary, _ = commercial_summary(sales_graph, item_filters)
            products, categories = sale_rankings(sales_graph, limit=10, filters=item_filters)
            operator_groups = sale_user_groups(sales_graph, 'created_by', item_filters)
            seller_groups = sale_user_groups(sales_graph, 'seller_user', item_filters)
            _cancelled_rows, cancellations = cancellation_summary(
                branch=branch, start=start, end=end, category=category,
            )
            discount_count = summary['manual_discount_count']
            heatmap, current_comparison, previous_comparison = dashboard_time_analysis(
                sales_graph, branch=branch, start=start, end=end, category=category,
            )
            if can_view_consumptions:
                dashboard_consumption_graph = list(_financial_sales(filtered_sales(
                    branch=branch,
                    start=start,
                    end=end,
                    operation_type=OperationType.CONSUMPTION,
                    filters={'category': category} if category else {},
                )))
            dashboard_receipts = receipt_summary(
                branch=branch, start=start, end=end,
                filters={'category': category} if category else {},
                inflow_sales=sales_graph + dashboard_consumption_graph,
            ) if can_view_consumptions else None
            response['sales'] = {
                'revenue': decimal_string(summary['effective_revenue']),
                'gross': decimal_string(summary['gross']),
                'effective_revenue': decimal_string(summary['effective_revenue']),
                'count': summary['count'],
                'average': decimal_string(summary['average']),
                'account_discount': decimal_string(summary['account_discount']),
                'item_discount': decimal_string(summary['item_discount']),
                'manual_discount': decimal_string(summary['manual_discount']),
                'manual_discount_count': discount_count,
                'promotion_discount': decimal_string(summary['promotion_discount']),
                'total_discount': decimal_string(summary['total_discount']),
                'service_fee': decimal_string(summary['service_fee']),
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
                        'effective_revenue': decimal_string(row['effective_revenue']),
                        'service_fee': decimal_string(row['service_fee']),
                        'customer_total': decimal_string(row['customer_total']),
                    }
                    for row in hourly_sales(sales_graph, item_filters)
                ],
                'payment_distribution': [
                    {
                        'code': row.get('code', row.get('payment_method_code')),
                        'name': row.get('name', row.get('payment_method_name')),
                        'amount': decimal_string(
                            row.get('net_received', row.get('amount'))
                        ),
                    }
                    for row in (
                        dashboard_receipts['payment_methods']
                        if dashboard_receipts else payment_totals(sales_graph, item_filters)
                    )
                ],
                'payment_distribution_scope': (
                    'operational' if dashboard_receipts else 'sales_only'
                ),
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
                    sorted(
                        sales_graph, key=lambda sale: (sale.created_at, sale.pk), reverse=True
                    )[:10],
                    many=True, context={'request': request}
                ).data,
            }
            if dashboard_receipts:
                response['sales']['total_received_operational'] = decimal_string(
                    dashboard_receipts['total_operational_received']
                )
                response['sales']['operational_reconciliation_delta'] = decimal_string(
                    dashboard_receipts['reconciliation_delta']
                )
            if not user_has_code(request, 'commissions.view'):
                response['sales'].pop('commission', None)
                for group in response['sales']['top_sellers'] + response['sales']['top_operators']:
                    group.pop('commission', None)

        if can_view_consumptions:
            if dashboard_consumption_graph is None:
                dashboard_consumption_graph = list(_financial_sales(filtered_sales(
                    branch=branch,
                    start=start,
                    end=end,
                    operation_type=OperationType.CONSUMPTION,
                    filters={'category': category} if category else {},
                )))
            summary = consumption_summary(dashboard_consumption_graph, filters={
                'category': category
            } if category else {})
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
            stock = inventory_kpis(
                branch, include_value=include_value, category=category,
            )
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
                if key in (
                    'result', 'estimated_result', 'margin', 'operational_received',
                    'charged_consumption', 'historical_sales_cogs',
                    'historical_consumption_cogs', 'commission',
                    'operating_expenses', 'fixed_cost',
                    'operational_reconciliation_delta',
                )
            }
            if not user_has_code(request, 'commissions.view'):
                response['operational_result'].pop('commission', None)
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
        'promotion_discount_total', 'item_discount_total', 'discount', 'service_fee_amount',
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
        summary, cancellations = commercial_summary(sales, filters)
        products, categories = sale_rankings(
            sales, limit=None if scope == 'products' else 10, filters=filters,
        )
        operator_groups = sale_user_groups(sales, 'created_by', filters)
        seller_groups = sale_user_groups(sales, 'seller_user', filters)
        result = {
            'gross': decimal_string(summary['gross']),
            'effective_revenue': decimal_string(summary['effective_revenue']),
            'count': summary['count'],
            'average': decimal_string(summary['average']),
            'ticket_average': decimal_string(summary['ticket_average_received']),
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
                'reversed_service_fee': decimal_string(
                    cancellations['reversed_service_fee']
                ),
                'reversed_total_received': decimal_string(
                    cancellations['reversed_total_received']
                ),
                'reconciliation_delta': decimal_string(
                    cancellations['reconciliation_delta']
                ),
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
        if scope == 'discounts':
            discounted = sales.filter(status=SaleStatus.FINALIZED).filter(
                Q(discount__gt=0)
                | Q(item_discount_total__gt=0)
                | Q(promotion_discount_total__gt=0)
            ).distinct()
            item_filters = {
                key: filters[key] for key in ('category', 'product') if filters.get(key)
            }
            discounted_ids = [
                sale.pk for sale in _financial_sales(discounted)
                if _scoped_sale_values(sale, item_filters)['total_discount'] > 0
            ]
            discounted = discounted.filter(pk__in=discounted_ids)
            discount_summary, _ = commercial_summary(discounted, filters)
            result.update({
                'count': discount_summary['discounted_count'],
                'gross': decimal_string(discount_summary['gross']),
                'account_discount': decimal_string(discount_summary['account_discount']),
                'item_discount': decimal_string(discount_summary['item_discount']),
                'manual_discount': decimal_string(discount_summary['manual_discount']),
                'promotion_discount': decimal_string(discount_summary['promotion_discount']),
                'total_discount': decimal_string(discount_summary['total_discount']),
                'effective_revenue': decimal_string(discount_summary['effective_revenue']),
                'service_fee': decimal_string(discount_summary['service_fee']),
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
                        )
                    },
                }
                for row in receipts['payment_methods']
            ]
            if result.get('filtered_payment_method'):
                result['filtered_payment_method']['subtotal'] = decimal_string(
                    result['filtered_payment_method']['subtotal']
                )
        if not user_has_code(request, 'commissions.view'):
            result.pop('commission', None)
            for group in result.get('operator_groups', []) + result.get('seller_groups', []):
                group.pop('commission', None)
        summary_keys = {
            'products': {'product_ranking', 'category_ranking'},
            'receipts': set(result),
            'operators': {'operator_groups'},
            'sellers': {'seller_groups'},
            'commissions': {
                'seller_groups', 'commission', 'commission_sale_count',
                'commission_attendant_count',
            },
            'discounts': {
                'account_discount', 'item_discount', 'manual_discount',
                'promotion_discount', 'total_discount', 'gross', 'count',
                'effective_revenue', 'service_fee', 'total_received_sales',
                'customer_total', 'discount_reconstruction_delta',
                'received_reconstruction_delta',
            },
        }.get(scope)
        if summary_keys is not None:
            result = {key: value for key, value in result.items() if key in summary_keys}
        if request.query_params.get('export') == 'csv':
            if scope == 'products':
                ranking_rows = [
                    {
                        'ranking_type': 'Produto',
                        'name': row['product_name'],
                        'internal_code': row['internal_code'],
                        'quantity': row['quantity'],
                        'revenue': row['revenue'],
                    }
                    for row in result.get('product_ranking', [])
                ] + [
                    {
                        'ranking_type': 'Categoria',
                        'name': row['category_name'],
                        'internal_code': '',
                        'quantity': row['quantity'],
                        'revenue': row['revenue'],
                    }
                    for row in result.get('category_ranking', [])
                ]
                return csv_response(
                    'relatorio-produtos.csv',
                    ('ranking_type', 'name', 'internal_code', 'quantity', 'revenue'),
                    ranking_rows,
                )
            if scope == 'receipts':
                filtered_method = result.get('filtered_payment_method') or {}
                export_rows = [
                    {
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
                return csv_response(
                    'relatorio-recebimentos.csv',
                    (
                        'code', 'name', 'commercial_received',
                        'consumption_received', 'gross_received', 'reversals',
                        'net_received', 'is_filtered_method',
                        'filtered_subtotal_is_integral_revenue',
                    ),
                    export_rows,
                )
            if scope in ('operators', 'sellers', 'commissions'):
                key = 'operator_groups' if scope == 'operators' else 'seller_groups'
                group_rows = [
                    {**row, 'name': row.get('user', {}).get('name', '')}
                    for row in result.get(key, [])
                ]
                headers = (
                    'name', 'count', 'gross', 'effective_revenue', 'service_fee',
                    'customer_total', 'total_received', 'payment_reconciliation_delta',
                    'cancellation_count', 'cancellation_value',
                )
                if scope == 'commissions':
                    headers += ('commission',)
                return csv_response(f'relatorio-{scope}.csv', headers, group_rows)
        if scope == 'discounts':
            detail_rows = sale_rows(discounted)
        else:
            detail_rows = sale_rows(sales) if scope in ('overview', 'sales') else []
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
            category=filters.get('category'), product=filters.get('product'),
        )
        if filters.get('operator'):
            rows = rows.filter(created_by_id=filters['operator'])
        if filters.get('seller'):
            rows = rows.filter(seller_user_id=filters['seller'])
        if filters.get('payment_method'):
            rows = rows.filter(payments__payment_method_id=filters['payment_method'])
        if filters.get('payment_method_code'):
            rows = rows.filter(
                payments__payment_method_code=filters['payment_method_code']
            )
        rows = rows.distinct()
        if any(filters.get(key) for key in (
            'operator', 'seller', 'payment_method', 'payment_method_code',
        )):
            item_filters = {
                key: filters[key] for key in ('category', 'product') if filters.get(key)
            }
            totals = FinancialAggregator(
                _financial_sales(rows), item_filters
            ).cancellations()
        detail_rows = rows.select_related(
            'created_by', 'seller_user', 'discount_approved_by', 'beneficiary_user'
        ).prefetch_related('items__product__category', 'payments').order_by(
            '-cancelled_at', '-id'
        )
        return self.respond(
            request, rows=detail_rows, period=canonical_datetime_range(start, end),
            summary={
                'count': totals['count'],
                'value': decimal_string(totals['value']),
                'reversed_effective_revenue': decimal_string(
                    totals['reversed_effective_revenue']
                ),
                'reversed_service_fee': decimal_string(totals['reversed_service_fee']),
                'reversed_total_received': decimal_string(
                    totals['reversed_total_received']
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
                'effective_revenue', 'service_fee', 'commission', 'customer_total',
                'total_received', 'payment_reconciliation_delta', 'average',
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
            for key in ('reference', 'charged', 'benefit')
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
        statement_keys = (
            'gross', 'promotion_discount', 'item_discount', 'account_discount',
            'manual_discount', 'discounts', 'effective_revenue', 'service_fee',
            'customer_total', 'total_received_sales', 'payment_reconciliation_delta',
            'charged_consumption', 'operational_received', 'historical_sales_cogs',
            'historical_consumption_cogs', 'commission', 'operating_expenses',
            'fixed_cost', 'estimated_result', 'result', 'margin',
            'operational_reconciliation_delta',
        )
        data = {
            key: decimal_string(summary[key]) for key in statement_keys
        }
        data['unclassified_withdrawals'] = {
            'count': summary['unclassified_withdrawals']['count'],
            'amount': decimal_string(summary['unclassified_withdrawals']['amount']),
        }
        if not user_has_code(request, 'commissions.view'):
            data.pop('commission', None)
        data['cash_session'] = session.pk if session else None
        data['notice'] = 'Estimativa operacional; não constitui DRE contábil.'
        if request.query_params.get('export') == 'csv':
            labels = {
                'gross': 'Valor bruto a preço de tabela',
                'promotion_discount': '(-) Descontos promocionais',
                'item_discount': '(-) Descontos manuais por item',
                'account_discount': '(-) Descontos manuais na conta',
                'effective_revenue': '= Faturamento efetivo',
                'service_fee': 'Taxa de serviço',
                'customer_total': 'Total cobrado',
                'total_received_sales': 'Total comercial recebido',
                'payment_reconciliation_delta': 'Delta de pagamentos comerciais',
                'charged_consumption': '(+) Consumações cobradas',
                'operational_received': '= Recebimento operacional',
                'historical_sales_cogs': '(-) CMV histórico de vendas',
                'historical_consumption_cogs': '(-) CMV histórico de consumações',
                'commission': '(-) Comissões',
                'operating_expenses': '(-) Despesas operacionais',
                'fixed_cost': '(-) Custo fixo rateado',
                'estimated_result': '= Resultado estimado',
                'margin': 'Margem estimada (%)',
                'operational_reconciliation_delta': 'Delta de reconciliação operacional',
            }
            rows = [
                {'statement': label, 'value': data[key]}
                for key, label in labels.items() if key in data
            ]
            rows.append({'statement': 'Observação', 'value': data['notice']})
            return csv_response(
                self.csv_filename, ('statement', 'value'), rows,
            )
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
            'benefit': decimal_string(summary['benefit']),
            'quantity': decimal_string(summary['quantity'], 3),
            'payment_totals': [
                {**row, 'amount': decimal_string(row['amount'])}
                for row in summary['payments']
            ],
            'payment_reconciliation_delta': decimal_string(
                summary['payment_reconciliation_delta']
            ),
        }
        if include_cost:
            data['historical_cost'] = decimal_string(summary['historical_cost'])
            data['historical_consumption_cogs'] = data['historical_cost']
        beneficiary_groups, user_type_groups = consumption_groupings(sales, filters)
        data['beneficiary_groups'] = [
            _consumption_group_json(row) for row in beneficiary_groups
        ]
        data['user_type_groups'] = [
            _consumption_group_json(row) for row in user_type_groups
        ]
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
            'effective_revenue': decimal_string(clipped['effective_revenue']),
            'service_fee': decimal_string(clipped['service_fee']),
            'sales_received': decimal_string(clipped['sales_received']),
            'consumption_charged': decimal_string(clipped['consumption_charged']),
            'operational_received': decimal_string(clipped['total_operational_received']),
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
                    )
                },
            }
            for row in clipped['payment_methods']
        ]
        if user_has_code(request, 'commissions.view'):
            clipped_sales = [
                sale for sale in session_sales
                if (
                    start <= sale.created_at < end_exclusive
                    and sale.status == SaleStatus.FINALIZED
                )
            ]
            summary['commission'] = decimal_string(
                FinancialAggregator(clipped_sales).commercial()['commission']
            )
        if request.query_params.get('export') == 'csv':
            export_rows = []
            for row in serialized:
                operational = row.get('operational_summary', {})
                sales_summary = operational.get('sales', {})
                consumption = operational.get('consumptions', {})
                export_row = {
                    **{key: row.get(key) for key in self.csv_headers},
                    'sales_count': sales_summary.get('count', 0),
                    'gross': sales_summary.get('gross', '0.00'),
                    'promotion_discount': sales_summary.get('promotion_discount', '0.00'),
                    'item_discount': sales_summary.get('item_discount', '0.00'),
                    'account_discount': sales_summary.get('account_discount', '0.00'),
                    'effective_revenue': sales_summary.get('effective_revenue', '0.00'),
                    'service_fee': sales_summary.get('service_fee', '0.00'),
                    'customer_total': sales_summary.get('customer_total', '0.00'),
                    'sales_cancellation_count': sales_summary.get('cancellations', {}).get('count', 0),
                    'sales_cancellation_value': sales_summary.get('cancellations', {}).get('value', '0.00'),
                    'consumption_count': consumption.get('count', 0),
                    'consumption_reference': consumption.get('reference', '0.00'),
                    'consumption_charged': consumption.get('charged', '0.00'),
                    'consumption_benefit': consumption.get('benefit', '0.00'),
                    'consumption_cancellation_count': consumption.get('cancellations', {}).get('count', 0),
                    'consumption_cancellation_value': consumption.get('cancellations', {}).get('value', '0.00'),
                    'payment_totals': operational.get('payment_totals', []),
                }
                if 'commission' in sales_summary:
                    export_row['commission'] = sales_summary['commission']
                export_rows.append(export_row)
            headers = self.csv_headers + (
                'sales_count', 'gross', 'promotion_discount', 'item_discount',
                'account_discount', 'effective_revenue', 'service_fee',
                'customer_total', 'sales_cancellation_count', 'sales_cancellation_value',
                'consumption_count', 'consumption_reference', 'consumption_charged',
                'consumption_benefit', 'consumption_cancellation_count',
                'consumption_cancellation_value', 'payment_totals',
            )
            if user_has_code(request, 'commissions.view'):
                headers += ('commission',)
            return csv_response(self.csv_filename, headers, export_rows)
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
        if request.query_params.get('export') == 'csv':
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
                'movement_count',
            )
            if include_cost:
                headers += ('estimated_cost',)
            return csv_response(self.csv_filename, headers, export_rows)
        return self.respond(
            request, rows=rows, period=canonical_datetime_range(start, end), summary=summary,
        )
