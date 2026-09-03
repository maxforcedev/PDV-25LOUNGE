import csv
import io
import json
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db.models import (
    Case, Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When,
)
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.base.datetimes import canonical_datetime_range, parse_datetime_range
from apps.base.export_labels import (
    export_label, export_value, promotion_discount_type_label,
    promotion_discount_value_label,
)
from apps.base.audit import audit_log
from apps.base.models import AuditLog
from apps.base.report_exports import render_report_export, report_key_value_rows
from apps.base.pagination import StandardPagination
from apps.cash.models import (
    CashMovement, CashMovementType, CashRegister, CashSession, WithdrawalCategory,
)
from apps.cash.services import build_session_operational_summary
from apps.companies.models import Customer
from apps.companies.rbac import OPERATING_PERMISSION_CODES
from apps.companies.selectors import branch_permission_codes, eligible_branch_users, user_has_company_permission
from apps.commands.models import (
    Command, CommandOperation, CommandOperationType, CommandPayment,
    CommandPaymentStatus, CommandStatus, OrderItem, OrderItemStatus, Table,
)
from apps.inventory.content import exact_sum
from apps.inventory.models import (
    InventoryCount,
    InventoryCountItem,
    MovementType,
    TransferDivergence,
    TransferDivergenceStatus,
    StockTransferItem,
    StockTransfer,
)
from apps.products.models import Category, Product
from apps.purchases.models import (
    PayableInstallment,
    PayableInstallmentStatus,
    PurchaseOrder,
    PurchaseOrderStatus,
)
from apps.sales.models import OperationType, Payment, PaymentMethod, Promotion, Sale, SaleItem, SaleStatus
from apps.sales.serializers import readable_user_name
from apps.suppliers.models import Supplier

from .permissions import ReportsPermission
from .financials import FinancialAggregator
from .selectors import (
    _financial_sales,
    _scoped_sale_values,
    commercial_summary,
    cancellation_summary,
    consumption_groupings,
    consumption_item_groupings,
    consumption_summary,
    current_cash_sessions,
    dashboard_time_analysis,
    event_rows,
    filtered_cash_sessions,
    filtered_inventory_counts,
    filtered_inventory_movements,
    filtered_sales,
    filtered_stock_transfers,
    period_event_sales,
    stock_consumption_report,
    stock_position_report,
    filtered_withdrawals,
    inventory_kpis,
    hourly_sales,
    operational_result,
    period_end_exclusive,
    product_commercial_breakdowns,
    receipt_event_rows,
    receipt_event_summary,
    receipt_summary,
    sale_rankings,
    sale_rows,
    sale_user_groups,
    withdrawal_summary,
)
from .serializers import (
    CashReportQuerySerializer,
    CashMovementReportSerializer,
    CashSessionReportSerializer,
    CancellationReportSerializer,
    CommandsReportQuerySerializer,
    CommercialComplementsReportQuerySerializer,
    ConsumptionsReportQuerySerializer,
    InventoryCountReportSerializer,
    InventoryCountsReportQuerySerializer,
    InventoryMovementReportSerializer,
    InventoryReportQuerySerializer,
    OperationalResultQuerySerializer,
    PaymentEventReportSerializer,
    PayablesReportQuerySerializer,
    PurchaseReportQuerySerializer,
    ReportSaleSerializer,
    SalesReportQuerySerializer,
    SupplierReportQuerySerializer,
    StockConsumptionMovementSerializer,
    StockConsumptionReportQuerySerializer,
    StockConsumptionSummarySerializer,
    StockPositionReportQuerySerializer,
    StockPositionReportSerializer,
    StockTransferReportSerializer,
    StockTransfersReportQuerySerializer,
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


def overview_comparison_data(request, *, start, end, filters):
    def numeric_decimal(value):
        if isinstance(value, bool) or not isinstance(value, (Decimal, int, float)):
            return None
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        return decimal_value if decimal_value.is_finite() else None

    def period_values(period_start, period_end):
        sales, reversals = period_event_sales(
            branch=request.branch_context, start=period_start, end=period_end,
            filters=filters, operation_types=(OperationType.SALE,),
        )
        commercial, _ = commercial_summary(sales, filters, reversals=reversals)
        _rows, cancellations = cancellation_summary(
            branch=request.branch_context, start=period_start, end=period_end,
            filters=filters,
        )
        values = {
            'gross_revenue': commercial['gross'],
            'net_revenue': commercial['sales_revenue'],
            'sales_count': Decimal(commercial['count']),
            'ticket_average': commercial['average'],
            'total_received': commercial['total_received'],
            'discounts': commercial['total_discount'],
            'service_fee': commercial['service_fee'],
            'cancellations': cancellations['value'],
        }
        if any(user_has_code(request, code) for code in (
            'reports.view_consumptions', 'sales.view_consumption',
        )):
            consumptions, consumption_reversals = period_event_sales(
                branch=request.branch_context, start=period_start, end=period_end,
                filters=filters, operation_types=(OperationType.CONSUMPTION,),
            )
            consumption = consumption_summary(
                consumptions, filters=filters, reversals=consumption_reversals,
            )
            values['consumptions_courtesies'] = consumption['subsidy']
        can_view_result = all((
            user_has_code(request, 'reports.view_operational_result'),
            user_has_code(request, 'inventory.view_stock_costs'),
            user_has_code(request, 'commissions.view'),
        ))
        if can_view_result:
            result_sales = filtered_sales(
                branch=request.branch_context, start=period_start, end=period_end,
                operation_type=OperationType.SALE, filters=filters,
            )
            statement = operational_result(
                branch=request.branch_context, start=period_start, end=period_end,
                sales=result_sales, filters=filters,
            )
            values['estimated_result'] = statement['estimated_result']
            values['estimated_margin'] = statement['margin']
        return values

    current_end = period_end_exclusive(end)
    duration = current_end - start
    previous_start = start - duration
    previous_end = start - timedelta(microseconds=1)
    current = period_values(start, end)
    previous = period_values(previous_start, previous_end)
    deltas = {}
    for key, current_value in current.items():
        previous_value = previous.get(key)
        current_number = numeric_decimal(current_value)
        previous_number = numeric_decimal(previous_value)
        if current_number is None or previous_number is None:
            deltas[key] = {
                'amount': None,
                'percentage': None,
                'direction': None,
                'comparable': False,
            }
            continue
        difference = current_number - previous_number
        percentage = (
            difference * Decimal('100') / abs(previous_number)
            if previous_number else None
        )
        deltas[key] = {
            'amount': decimal_string(difference),
            'percentage': decimal_string(percentage) if percentage is not None else None,
            'direction': 'up' if difference > 0 else 'down' if difference < 0 else 'stable',
            'comparable': True,
        }

    def serialize(values):
        result = {}
        for key, value in values.items():
            numeric_value = numeric_decimal(value)
            result[key] = (
                None if numeric_value is None else
                int(numeric_value) if key == 'sales_count' else
                decimal_string(numeric_value)
            )
        return result

    return {
        'current_period': canonical_datetime_range(start, end),
        'previous_period': canonical_datetime_range(previous_start, previous_end),
        'current': serialize(current),
        'previous': serialize(previous),
        'deltas': deltas,
    }


def operational_result_data(request, summary, *, extra_keys=()):
    keys = (
        'sales_revenue', 'consumption_charged', 'effective_revenue', 'service_fee',
        'total_received', 'payment_total', 'reconciliation_delta',
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
        for key in (
            'operating_expenses', 'fixed_cost', 'costs_and_expenses',
            'estimated_result', 'result', 'margin',
        ):
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
        start, end = parse_datetime_range(request.query_params)
        period_filter = {}
        cancellation_filter = {}
        if start and end:
            period_filter = {
                'created_at__gte': start,
                'created_at__lt': period_end_exclusive(end),
            }
            cancellation_filter = {
                'cancelled_at__gte': start,
                'cancelled_at__lt': period_end_exclusive(end),
            }
        historical_sales = Sale.objects.filter(branch=branch).filter(
            Q(**period_filter) | Q(**cancellation_filter)
        ) if period_filter else Sale.objects.none()
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
        can_view_phase_two = user_has_code(request, 'inventory.report.view')
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
            or can_view_phase_two
        )
        historical_beneficiary_ids = historical_sales.filter(
            operation_type=OperationType.CONSUMPTION,
            beneficiary_user__isnull=False,
        ).values_list('beneficiary_user_id', flat=True)
        users = User.objects.filter(
            Q(
                is_active=True,
                archived_at__isnull=True,
                company_accesses__company_id=branch.company_id,
                company_accesses__is_active=True,
            ) | Q(pk__in=historical_beneficiary_ids)
        ).distinct().order_by('first_name', 'last_name', 'id') if (
            can_view_consumptions or can_view_withdrawals
        ) else User.objects.none()
        historical_operator_ids = set(historical_sales.values_list('created_by_id', flat=True))
        historical_operator_ids.update(
            historical_sales.exclude(cancelled_by_id=None).values_list('cancelled_by_id', flat=True)
        )
        operators = User.objects.filter(
            Q(
                is_active=True,
                archived_at__isnull=True,
                branch_accesses__branch=branch,
                branch_accesses__is_active=True,
            ) | Q(pk__in=historical_operator_ids)
        ).distinct().order_by('first_name', 'last_name', 'id') if can_view_team else User.objects.none()
        historical_items = SaleItem.objects.filter(sale__in=historical_sales)
        historical_product_ids = historical_items.values_list('product_id', flat=True)
        historical_category_ids = historical_items.exclude(
            category_id_snapshot=None
        ).values_list('category_id_snapshot', flat=True)
        products = Product.objects.filter(company_id=branch.company_id).filter(
            Q(status='active', archived_at__isnull=True)
            | Q(pk__in=historical_product_ids)
        ).order_by(
            'name', 'id'
        ) if can_view_products else Product.objects.none()
        categories = Category.objects.filter(branch=branch).filter(
            Q(status='active', deleted_at__isnull=True)
            | Q(pk__in=historical_category_ids)
        ).order_by(
            'sort_order', 'name', 'id'
        ) if can_view_products else Category.objects.none()
        historical_payment_method_ids = Payment.objects.filter(
            sale__in=historical_sales,
        ).values_list('payment_method_id', flat=True)
        payment_methods = PaymentMethod.objects.filter(
            company_id=branch.company_id,
        ).filter(
            Q(status='active') | Q(pk__in=historical_payment_method_ids)
        ).order_by('name', 'id') if can_view_payment_data else PaymentMethod.objects.none()
        historical_register_ids = CashSession.objects.filter(
            branch=branch, **period_filter,
        ).values_list('cash_register_id', flat=True) if period_filter else []
        registers = CashRegister.objects.filter(branch=branch).filter(
            Q(status='active') | Q(pk__in=historical_register_ids)
        ).order_by(
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
        historical_seller_ids = historical_sales.filter(
            seller_user__isnull=False
        ).values_list('seller_user_id', flat=True)
        sellers = User.objects.filter(
            Q(id__in=eligible_seller_ids) | Q(id__in=historical_seller_ids)
        ).distinct().order_by('first_name', 'last_name', 'id') if can_view_sellers else User.objects.none()
        historical_inventory_user_ids = set()
        if period_filter:
            historical_inventory_user_ids.update(InventoryCount.objects.filter(
                branch=branch, **period_filter,
            ).values_list('created_by_id', flat=True))
            historical_inventory_user_ids.update(StockTransfer.objects.filter(
                Q(origin_branch=branch) | Q(destination_branch=branch),
                **period_filter,
            ).values_list('created_by_id', flat=True))
        inventory_users = User.objects.filter(
            Q(
                is_active=True,
                archived_at__isnull=True,
                company_accesses__company_id=branch.company_id,
                company_accesses__is_active=True,
            ) | Q(pk__in=historical_inventory_user_ids)
        ).distinct().order_by('first_name', 'last_name', 'id') if can_view_phase_two else User.objects.none()
        return Response({
            'operators': [
                {
                    'id': user.pk,
                    'name': readable_user_name(user),
                    'historical': user.pk in historical_operator_ids and (
                        not user.is_active or user.archived_at is not None
                    ),
                } for user in operators
            ],
            'sellers': [
                {
                    'id': user.pk,
                    'name': readable_user_name(user),
                    'historical': not user.is_active or user.archived_at is not None,
                }
                for user in sellers
            ],
            'beneficiaries': [
                {
                    'id': user.pk,
                    'name': readable_user_name(user),
                    'user_type': user.user_type,
                    'historical': user.pk in historical_beneficiary_ids and (
                        not user.is_active or user.archived_at is not None
                    ),
                }
                for user in users
            ],
            'inventory_users': [
                {
                    'id': user.pk,
                    'name': readable_user_name(user),
                    'historical': user.pk in historical_inventory_user_ids and (
                        not user.is_active or user.archived_at is not None
                    ),
                }
                for user in inventory_users
            ],
            'customers': [
                {
                    'id': customer.pk,
                    'name': customer.name,
                    'status': customer.status,
                    'historical': customer.status != 'active',
                }
                for customer in (
                    Customer.objects.filter(company_id=branch.company_id).filter(
                        Q(status='active') | Q(sales__in=historical_sales)
                    ).distinct().order_by('name', 'id') if can_view_sales_data else []
                )
            ],
            'products': [
                {
                    'id': product.pk,
                    'name': product.name,
                    'internal_code': product.internal_code,
                    'status': product.status,
                    'historical': product.archived_at is not None,
                }
                for product in products
            ],
            'categories': [
                {
                    'id': category.pk,
                    'name': category.name,
                    'status': category.status,
                    'historical': category.deleted_at is not None,
                }
                for category in categories
            ],
            'payment_methods': [
                {
                    'id': method.pk,
                    'name': method.name,
                    'code': method.code,
                    'status': method.status,
                    'historical': method.status != 'active',
                }
                for method in payment_methods
            ],
            'cash_registers': [
                {
                    'id': register.pk,
                    'name': register.name,
                    'status': register.status,
                    'historical': register.status != 'active',
                }
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

    def export_headers(self, request):
        return self.csv_headers

    def respond(self, request, *, rows, period, summary):
        if request.query_params.get('export') in ('csv', 'xlsx', 'pdf'):
            data = self.serialize_rows(rows, request)
            headers = self.export_headers(request)
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
        'commands.view',
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
            if not Category.objects.filter(pk=category, branch=branch).exists():
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'category': 'Categoria fora da filial atual.'})
        response['filters'] = {
            'category': category,
            'categories': list(Category.objects.filter(
                branch=branch, status='active', deleted_at__isnull=True,
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
                reversals=sales_reversals, product_order='revenue',
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
                sales_graph, branch=branch, start=start, end=end, filters=item_filters,
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

        if user_has_code(request, 'commands.view'):
            response['commands'] = Command.objects.filter(
                branch=branch,
                status=CommandStatus.OPEN,
            ).aggregate(
                open_count=Count('id'),
                open_table_count=Count('table_id', distinct=True),
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

    def serialize_rows(self, rows, request):
        scope = request.query_params.get('scope', 'sales')
        if scope == 'receipts':
            return PaymentEventReportSerializer(rows, many=True).data
        if scope == 'products':
            return rows
        return super().serialize_rows(rows, request)

    def get(self, request):
        scope = request.query_params.get('scope', 'sales')
        receipt_detail_rows = []
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
        modifier_rows, promotion_rows = product_commercial_breakdowns(
            sales_graph, filters, sales_reversals,
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
        if can_view_team:
            operator_by_id = {
                row['user']['id']: row for row in operator_groups
            }
            sessions_by_operator = {}
            for session in filtered_cash_sessions(
                branch=request.branch_context, start=start, end=end, filters={},
            ):
                metrics = sessions_by_operator.setdefault(session.opened_by_id, {
                    'cash_session_count': 0,
                    'cash_difference': Decimal('0.00'),
                })
                metrics['cash_session_count'] += 1
                metrics['cash_difference'] += session.closing_difference or Decimal('0.00')
            authorization_counts = {}
            for sale in sales_graph:
                if sale.discount_approved_by_id:
                    authorization_counts[sale.discount_approved_by_id] = (
                        authorization_counts.get(sale.discount_approved_by_id, 0) + 1
                    )
                for item in sale.items.all():
                    if item.discount_approved_by_id:
                        authorization_counts[item.discount_approved_by_id] = (
                            authorization_counts.get(item.discount_approved_by_id, 0) + 1
                        )
            cancellation_actor_counts = {}
            for sale in sales_reversals:
                if sale.cancelled_by_id:
                    cancellation_actor_counts[sale.cancelled_by_id] = (
                        cancellation_actor_counts.get(sale.cancelled_by_id, 0) + 1
                    )
            command_reversals = CommandPayment.objects.filter(
                branch=request.branch_context,
                status=CommandPaymentStatus.REVERSED,
                created_at__gte=start,
                created_at__lt=period_end_exclusive(end),
            ).values('operator_id').annotate(count=Count('id'))
            reversal_counts = {
                row['operator_id']: row['count'] for row in command_reversals
            }
            activity_ids = (
                set(sessions_by_operator) | set(authorization_counts)
                | set(cancellation_actor_counts) | set(reversal_counts)
            )
            missing_users = User.objects.filter(
                pk__in=activity_ids - set(operator_by_id)
            )
            for user in missing_users:
                row = {
                    'user': {'id': user.pk, 'name': readable_user_name(user)},
                    'count': 0,
                    'inflow_count': 0,
                    'reversal_count': 0,
                    'cancellation_count': 0,
                    'service_fee_waiver_count': 0,
                }
                operator_groups.append(row)
                operator_by_id[user.pk] = row
            for user_id, row in operator_by_id.items():
                row.update(sessions_by_operator.get(user_id, {
                    'cash_session_count': 0, 'cash_difference': Decimal('0.00'),
                }))
                row['authorized_discount_count'] = authorization_counts.get(user_id, 0)
                row['actor_cancellation_count'] = cancellation_actor_counts.get(user_id, 0)
                row['payment_reversal_count'] = reversal_counts.get(user_id, 0)
            operator_groups.sort(
                key=lambda row: (
                    -row.get('total_received', Decimal('0.00')),
                    row['user']['name'],
                )
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
            'product_ranking': [_ranking_json(row) for row in products],
            'category_ranking': [_ranking_json(row) for row in categories],
            'modifier_ranking': [
                {
                    **row,
                    'quantity': decimal_string(row['quantity'], 3),
                    'additional_revenue': decimal_string(row['additional_revenue']),
                    'ticket_average': decimal_string(row['ticket_average']),
                }
                for row in modifier_rows
            ],
            'promotion_ranking': [
                {
                    **row,
                    'discount': decimal_string(row['discount']),
                    'net_revenue': decimal_string(row['net_revenue']),
                }
                for row in promotion_rows
            ],
            'operator_groups': [_group_json(row) for row in operator_groups],
            'seller_groups': [_group_json(row) for row in seller_groups],
        }
        if scope in ('overview', 'sales'):
            heatmap, current_comparison, previous_comparison = dashboard_time_analysis(
                sales_graph,
                branch=request.branch_context,
                start=start,
                end=end,
                filters=filters,
                reversals=sales_reversals,
            )
            result['heatmap'] = [
                {
                    **row,
                    'sales_revenue': decimal_string(row['sales_revenue']),
                    'revenue': decimal_string(row['sales_revenue']),
                    'average': decimal_string(row['average']),
                }
                for row in heatmap
            ]
            result['hourly_sales'] = [
                {
                    **row,
                    'sales_revenue': decimal_string(row['sales_revenue']),
                    'effective_revenue': decimal_string(row['effective_revenue']),
                    'service_fee': decimal_string(row['service_fee']),
                    'total_received': decimal_string(row['total_received']),
                }
                for row in hourly_sales(sales_graph, filters, sales_reversals)
            ]
        if scope == 'overview':
            result['weekly_comparison'] = {
                'current': [
                    {
                        **row,
                        'sales_revenue': decimal_string(row['sales_revenue']),
                        'revenue': decimal_string(row['sales_revenue']),
                    }
                    for row in current_comparison
                ],
                'previous': [
                    {
                        **row,
                        'sales_revenue': decimal_string(row['sales_revenue']),
                        'revenue': decimal_string(row['sales_revenue']),
                    }
                    for row in previous_comparison
                ],
            }
            result['period_comparison'] = overview_comparison_data(
                request, start=start, end=end, filters=filters,
            )
            result['kpis'] = result['period_comparison']['current']
        if scope == 'products':
            result['quantity'] = decimal_string(sum(
                (row['quantity'] for row in products), Decimal('0.000')
            ), 3)
            result['product_count'] = len(products)
            result['category_count'] = len(categories)
            result['has_costs'] = user_has_code(
                request, 'inventory.view_stock_costs'
            )
            result['discounts'] = decimal_string(sum(
                (row['discounts'] for row in products), Decimal('0.00')
            ))
            if user_has_code(request, 'inventory.view_stock_costs'):
                result['cost'] = decimal_string(sum(
                    (row['cost'] for row in products), Decimal('0.00')
                ))
                result['margin'] = decimal_string(sum(
                    (row['margin'] for row in products), Decimal('0.00')
                ))
            else:
                for row in result['product_ranking'] + result['category_ranking']:
                    for key in ('cost', 'margin', 'margin_percent'):
                        row.pop(key, None)
        if scope == 'discounts':
            item_filters = {
                key: filters[key] for key in ('category', 'product') if filters.get(key)
            }
            discounted_graph = [
                sale for sale in sales_graph
                if (
                    _scoped_sale_values(sale, item_filters)['total_discount'] > 0
                    or sale.service_fee_waived
                )
            ]
            discounted_reversals = [
                sale for sale in sales_reversals
                if (
                    _scoped_sale_values(sale, item_filters)['total_discount'] > 0
                    or sale.service_fee_waived
                )
            ]
            discount_summary, _ = commercial_summary(
                discounted_graph, filters, reversals=discounted_reversals,
            )
            result.update({
                'count': len(discounted_graph) - len(discounted_reversals),
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
                'service_fee_waiver_count': sum(
                    sale.service_fee_waived for sale in discounted_graph
                ) - sum(sale.service_fee_waived for sale in discounted_reversals),
                'discount_average': decimal_string(
                    discount_summary['total_discount'] / discount_summary['discounted_count']
                    if discount_summary['discounted_count'] else Decimal('0.00')
                ),
            })
        if scope == 'receipts':
            reconciliation = receipt_summary(
                branch=request.branch_context, start=start, end=end, filters=filters,
            )
            receipt_detail_rows = receipt_event_rows(
                branch=request.branch_context, start=start, end=end, filters=filters,
            )
            receipts = receipt_event_summary(receipt_detail_rows)
            result = {
                key: (
                    decimal_string(value) if isinstance(value, Decimal) else value
                )
                for key, value in receipts.items()
                if key != 'payment_methods'
            }
            result['reconciliation'] = {
                key: decimal_string(reconciliation[key])
                for key in (
                    'sales_revenue', 'consumption_charged', 'effective_revenue',
                    'service_fee', 'total_received', 'payment_total',
                    'reconciliation_delta',
                )
            }
            for key in (
                'sales_revenue', 'consumption_charged', 'effective_revenue',
                'service_fee',
            ):
                result[key] = decimal_string(reconciliation[key])
            result['reconciliation_delta'] = decimal_string(
                receipts['payment_total'] - reconciliation['total_received']
            )
            result['payment_totals'] = [
                {
                    **row,
                    **{
                        key: decimal_string(row[key])
                        for key in (
                            'applied_total', 'received_total', 'change_total',
                            'reversals', 'percentage',
                        )
                    },
                }
                for row in receipts['payment_methods']
            ]
            result['summary_basis'] = 'payment_occurred_at'
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
            'products': {
                'product_ranking', 'category_ranking', 'modifier_ranking',
                'promotion_ranking', 'quantity', 'product_count', 'category_count',
                'has_costs', 'sales_revenue', 'discounts', 'cost', 'margin',
            },
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
                'service_fee_waiver_count',
                'discount_average',
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
                        'discounts': row['discounts'],
                        'sale_count': row['sale_count'],
                        'ticket_average': row['ticket_average'],
                        'cost': row.get('cost'),
                        'margin': row.get('margin'),
                        'margin_percent': row.get('margin_percent'),
                    }
                    for row in result.get('product_ranking', [])
                ] + [
                    {
                        'ranking_type': 'Categoria',
                        'name': row['category_name'],
                        'internal_code': '',
                        'quantity': row['quantity'],
                        'sales_revenue': row['sales_revenue'],
                        'discounts': row['discounts'],
                        'sale_count': row['sale_count'],
                        'ticket_average': row['ticket_average'],
                        'cost': row.get('cost'),
                        'margin': row.get('margin'),
                        'margin_percent': row.get('margin_percent'),
                    }
                    for row in result.get('category_ranking', [])
                ]
                return self.export_response(
                    request, filename='relatorio-produtos.csv', title='Relatório de produtos',
                    headers=(
                        'ranking_type', 'name', 'internal_code', 'quantity',
                        'sale_count', 'sales_revenue', 'discounts', 'ticket_average',
                    ) + ((
                        'cost', 'margin', 'margin_percent',
                    ) if user_has_code(request, 'inventory.view_stock_costs') else ()),
                    rows=ranking_rows, period=canonical_datetime_range(start, end), summary=result,
                )
            if scope == 'receipts':
                export_rows = self.serialize_rows(receipt_detail_rows, request)
                return self.export_response(
                    request, filename='relatorio-recebimentos.csv', title='Relatório de recebimentos',
                    headers=(
                        'event_id', 'occurred_at', 'sale', 'command', 'payment_method',
                        'applied_amount', 'received_amount', 'change_amount', 'origin',
                        'operator', 'cash_session', 'cash_register', 'status',
                        'reversal_reason',
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
                    headers += ('commission_base', 'commission_rate', 'commission')
                elif scope == 'sellers':
                    headers += (
                        'item_quantity', 'discounts', 'service_fee_waiver_count',
                    )
                elif scope == 'operators':
                    headers += (
                        'cash_session_count', 'authorized_discount_count',
                        'actor_cancellation_count', 'payment_reversal_count',
                        'cash_difference',
                    )
                return self.export_response(
                    request, filename=f'relatorio-{scope}.csv', title=f'Relatório {scope}',
                    headers=headers, rows=group_rows, period=canonical_datetime_range(start, end), summary=result,
                )
        if scope == 'discounts':
            detail_rows = event_rows(discounted_graph, discounted_reversals)
        else:
            detail_rows = list(sale_rows(filtered_sales(
                branch=request.branch_context, start=start, end=end,
                operation_type=OperationType.SALE, filters=filters,
            ))) if scope in (
                'overview', 'sales', 'operators', 'sellers', 'commissions',
            ) else []
            if scope == 'commissions':
                detail_rows = [
                    sale for sale in detail_rows if sale.commission_amount > 0
                ]
        if scope == 'receipts':
            detail_rows = receipt_detail_rows
        if scope == 'products':
            detail_rows = result.pop('product_ranking', [])
        return self.respond(
            request,
            rows=detail_rows,
            period=canonical_datetime_range(start, end),
            summary=result,
        )


class CancellationsReportView(BaseReportView):
    required_permission = 'reports.view_cancellations'
    query_serializer_class = SalesReportQuerySerializer
    row_serializer_class = CancellationReportSerializer
    csv_filename = 'relatorio-cancelamentos.csv'
    csv_headers = (
        'event_id', 'event_type', 'cancelled_at', 'operation_id',
        'operation_number', 'operation_type', 'product', 'quantity',
        'cancellation_actor', 'reason', 'financial_impact', 'stock_impact',
    )

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
        sale_rows_list = list(rows.select_related(
            'created_by', 'seller_user', 'discount_approved_by', 'beneficiary_user',
            'service_fee_waived_by', 'cancelled_by', 'customer',
            'cash_session__cash_register',
        ).prefetch_related(
            'items__product__category', 'items__discount_approved_by',
            'payments__payment_method', 'payments__source_command_payment__operator',
        ).order_by(
            '-cancelled_at', '-id'
        ))
        end_exclusive = period_end_exclusive(end)
        order_items = OrderItem.objects.filter(
            order__command__branch=request.branch_context,
            status=OrderItemStatus.CANCELLED,
            cancelled_at__gte=start,
            cancelled_at__lt=end_exclusive,
        ).select_related(
            'order__command__table', 'product', 'cancelled_by',
        )
        payments = CommandPayment.objects.filter(
            branch=request.branch_context,
            status=CommandPaymentStatus.REVERSED,
            created_at__gte=start,
            created_at__lt=end_exclusive,
        ).select_related(
            'command__table', 'payment_method', 'operator', 'reversal_of',
        )
        if filters.get('operator') is not None:
            order_items = order_items.filter(cancelled_by_id=filters['operator'])
            payments = payments.filter(operator_id=filters['operator'])
        if filters.get('product') is not None:
            order_items = order_items.filter(product_id=filters['product'])
            payments = payments.none()
        if filters.get('category') is not None:
            order_items = order_items.filter(
                product__branch_configs__branch=request.branch_context,
                product__branch_configs__category_id=filters['category'],
            )
            payments = payments.none()
        if filters.get('payment_method') is not None:
            order_items = order_items.none()
            payments = payments.filter(payment_method_id=filters['payment_method'])
        if filters.get('seller') is not None:
            order_items = order_items.none()
            payments = payments.none()
        if filters.get('customer') is not None:
            order_items = order_items.filter(
                order__command__customer_id=filters['customer']
            )
            payments = payments.filter(command__customer_id=filters['customer'])
        if filters.get('number'):
            order_items = order_items.filter(
                order__command__command_number__icontains=filters['number']
            )
            payments = payments.filter(
                command__command_number__icontains=filters['number']
            )
        order_items = list(order_items.order_by('-cancelled_at', '-id'))
        payments = list(payments.order_by('-created_at', '-id'))
        detail_rows = sale_rows_list + order_items + payments
        detail_rows.sort(
            key=lambda row: (
                row.cancelled_at if isinstance(row, (Sale, OrderItem)) else row.created_at,
                row.pk,
            ),
            reverse=True,
        )
        total_impact = totals['reversed_total_received'] + sum(
            (item.quantity * item.unit_price for item in order_items), Decimal('0.00')
        )
        handled = FinancialAggregator(
            period_event_sales(
                branch=request.branch_context, start=start, end=end,
                filters=filters, operation_types=(OperationType.SALE,),
            )[0],
            {key: filters[key] for key in ('product', 'category') if filters.get(key)},
        ).commercial()['total_received']
        return self.respond(
            request, rows=detail_rows, period=canonical_datetime_range(start, end),
            summary={
                'count': len(detail_rows),
                'sale_cancellation_count': len(sale_rows_list),
                'item_cancellation_count': len(order_items),
                'payment_reversal_count': len(payments),
                'value': decimal_string(totals['value']),
                'financial_impact': decimal_string(total_impact),
                'cancellation_percentage': decimal_string(
                    total_impact * Decimal('100') / (handled + total_impact)
                    if handled + total_impact else Decimal('0.00')
                ),
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
    result = {
        **row,
        **{
            field: decimal_string(row[field])
            for field in (
                'gross', 'manual_discount', 'promotion_discount', 'total_discount',
                'sales_revenue', 'consumption_charged', 'effective_revenue',
                'service_fee', 'commission', 'customer_total', 'total_received',
                'payment_total', 'reconciliation_delta',
                'payment_reconciliation_delta', 'average',
                'cancellation_value', 'item_quantity', 'discounts',
                'commission_base', 'commission_rate', 'cash_difference',
            )
            if field in row
        },
    }
    result['top_products'] = [
        {
            **item,
            'quantity': decimal_string(item['quantity'], 3),
            'sales_revenue': decimal_string(item['sales_revenue']),
        }
        for item in row.get('top_products', [])
    ]
    return result


def _ranking_json(row):
    return {
        **row,
        'quantity': decimal_string(row['quantity'], 3),
        **{
            key: decimal_string(row[key])
            for key in (
                'sales_revenue', 'revenue', 'discounts', 'cost', 'margin',
                'margin_percent', 'ticket_average',
            )
            if key in row
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
        product_groups, category_groups = consumption_item_groupings(
            consumption_graph, filters, consumption_reversals,
        )
        def consumption_item_json(row):
            return {
                **row,
                'quantity': decimal_string(row['quantity'], 3),
                **{
                    key: decimal_string(row[key])
                    for key in ('reference', 'charged', 'benefit')
                },
                **({
                    'historical_cost': decimal_string(row['historical_cost'])
                } if include_cost else {}),
            }
        data['product_groups'] = [consumption_item_json(row) for row in product_groups]
        data['category_groups'] = [consumption_item_json(row) for row in category_groups]
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
    movement_csv_headers = (
        'id', 'created_at', 'movement_type', 'cash_register', 'cash_session',
        'operator', 'reason', 'amount',
    )

    def serialize_rows(self, rows, request):
        if request.query_params.get('section') == 'movements':
            return CashMovementReportSerializer(
                rows, many=True, context={'request': request}
            ).data
        return super().serialize_rows(rows, request)

    def export_headers(self, request):
        if request.query_params.get('section') == 'movements':
            return self.movement_csv_headers
        return super().export_headers(request)

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
        serialized = CashSessionReportSerializer(
            sessions, many=True, context={'request': request}
        ).data
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
        period_movements = CashMovement.objects.filter(
            cash_session_id__in=session_ids,
            created_at__gte=start,
            created_at__lt=end_exclusive,
        ).select_related(
            'cash_session__cash_register', 'user', 'beneficiary_user',
        ).order_by('-created_at', '-id')
        opened_count = sum(start <= session.opened_at < end_exclusive for session in sessions)
        closed_count = sum(
            bool(session.closed_at and start <= session.closed_at < end_exclusive)
            for session in sessions
        )
        differences = [
            session.closing_difference for session in sessions
            if session.closing_difference is not None and session.closing_difference != 0
        ]
        summary = {
            'count': len(sessions),
            'opened_count': opened_count,
            'closed_count': closed_count,
            'difference_count': len(differences),
            'difference_absolute_total': decimal_string(sum(
                (abs(value) for value in differences), Decimal('0.00')
            )),
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
        if filters.get('section') == 'movements':
            return self.respond(
                request,
                rows=period_movements,
                period=canonical_datetime_range(start, end),
                summary=summary,
            )
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
        result['by_beneficiary'] = [
            {
                'beneficiary': row['beneficiary'],
                'count': row['count'],
                'amount': decimal_string(row['amount']),
            }
            for row in summary.get('by_beneficiary', [])
        ]
        result['by_operator'] = [
            {
                'operator': row['operator'],
                'count': row['count'],
                'amount': decimal_string(row['amount']),
            }
            for row in summary.get('by_operator', [])
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
        summary = withdrawal_summary(rows)
        materialized = list(rows)
        def grouped_user(field, output_key):
            groups = {}
            for movement in materialized:
                user = getattr(movement, field)
                key = getattr(movement, f'{field}_id')
                entry = groups.setdefault(key, {
                    output_key: ({
                        'id': key, 'name': readable_user_name(user),
                    } if user else None),
                    'count': 0,
                    'amount': Decimal('0.00'),
                })
                entry['count'] += 1
                entry['amount'] += movement.amount
            return sorted(
                groups.values(),
                key=lambda item: (-item['amount'], str(item[output_key])),
            )
        summary['by_beneficiary'] = grouped_user('beneficiary_user', 'beneficiary')
        summary['by_operator'] = grouped_user('user', 'operator')
        return self.respond(
            request,
            rows=materialized,
            period=canonical_datetime_range(start, end),
            summary=_withdrawal_summary_json(summary),
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
        'residual_content', 'unit_cost_snapshot', 'cost_impact', 'reason', 'user', 'sale',
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
        entries = Decimal('0.000')
        exits = Decimal('0.000')
        historical_cost_impact = Decimal('0.00')
        for movement in movements:
            if movement.quantity > 0:
                entries += movement.equivalent_quantity()
            elif movement.quantity < 0:
                exits += abs(movement.equivalent_quantity())
            if user_has_code(request, 'inventory.view_stock_costs'):
                historical_cost_impact += (
                    (movement.unit_cost_snapshot or Decimal('0.00')) * movement.quantity
                )
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
                'entries': format(entries, 'f'),
                'exits': format(exits, 'f'),
                **({
                    'historical_cost_impact': decimal_string(historical_cost_impact),
                } if user_has_code(request, 'inventory.view_stock_costs') else {}),
            },
        )


class StockPositionReportView(BaseReportView):
    required_permission = 'inventory.report.view'
    query_serializer_class = StockPositionReportQuerySerializer
    row_serializer_class = StockPositionReportSerializer
    csv_filename = 'relatorio-posicao-estoque.csv'
    csv_headers = (
        'product', 'category', 'unit', 'current_quantity', 'minimum_quantity',
        'maximum_quantity', 'average_unit_cost', 'last_unit_cost',
        'inventory_value', 'state',
    )

    def serialize_rows(self, rows, request):
        return self.row_serializer_class(
            rows,
            many=True,
            context={
                'request': request,
                'include_cost': user_has_code(request, 'inventory.view_stock_costs'),
            },
        ).data

    def export_headers(self, request):
        if user_has_code(request, 'inventory.view_stock_costs'):
            return self.csv_headers
        return tuple(
            header for header in self.csv_headers
            if header not in (
                'average_unit_cost', 'last_unit_cost', 'inventory_value',
            )
        )

    def get(self, request):
        serializer = self.query_serializer_class(
            data=request.query_params, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        rows = stock_position_report(
            branch=request.branch_context, filters=serializer.validated_data,
        )
        active_rows = rows.filter(product__archived_at__isnull=True)
        summary = active_rows.aggregate(
            below_minimum=Count('pk', filter=Q(
                current_quantity__gt=0,
                current_quantity__lt=F('minimum_quantity'),
            )),
            zero=Count('pk', filter=Q(current_quantity=0)),
            negative=Count('pk', filter=Q(current_quantity__lt=0)),
        )
        summary['product_count'] = active_rows.count()
        if user_has_code(request, 'inventory.view_stock_costs'):
            money_field = DecimalField(max_digits=40, decimal_places=12)
            current_value = ExpressionWrapper(
                F('current_quantity') * Coalesce(
                    F('average_unit_cost'), F('product__cost'),
                    output_field=money_field,
                ),
                output_field=money_field,
            )
            summary['inventory_value'] = decimal_string(active_rows.aggregate(
                total=Coalesce(
                    Sum(Case(
                        When(current_quantity__gt=0, then=current_value),
                        default=Value(Decimal('0'), output_field=money_field),
                        output_field=money_field,
                    )),
                    Value(Decimal('0'), output_field=money_field),
                )
            )['total'])
        return self.respond(
            request,
            rows=rows,
            period={'as_of': timezone.now().isoformat()},
            summary=summary,
        )


class InventoryCountsReportView(BaseReportView):
    required_permission = 'inventory.report.view'
    query_serializer_class = InventoryCountsReportQuerySerializer
    row_serializer_class = InventoryCountReportSerializer
    csv_filename = 'relatorio-inventarios-realizados.csv'
    csv_headers = (
        'id', 'date', 'branch', 'responsible', 'status', 'mode', 'item_count',
        'correct_count', 'shortage_count', 'surplus_count', 'financial_impact',
        'items',
    )

    def serialize_rows(self, rows, request):
        return self.row_serializer_class(
            rows,
            many=True,
            context={
                'request': request,
                'include_cost': user_has_code(request, 'inventory.view_stock_costs'),
            },
        ).data

    def export_headers(self, request):
        if user_has_code(request, 'inventory.view_stock_costs'):
            return self.csv_headers
        return tuple(
            header for header in self.csv_headers if header != 'financial_impact'
        )

    def get(self, request):
        filters, start, end = self.parse_query(request)
        rows = filtered_inventory_counts(
            branch=request.branch_context, start=start, end=end, filters=filters,
        )
        item_rows = InventoryCountItem.objects.filter(
            inventory_count_id__in=rows.order_by().values('pk')
        )
        if filters.get('product') is not None:
            item_rows = item_rows.filter(product_id=filters['product'])
        if filters.get('category') is not None:
            item_rows = item_rows.filter(
                product__branch_configs__branch=request.branch_context,
                product__branch_configs__category_id=filters['category'],
            )
        summary = item_rows.aggregate(
            item_count=Count('pk'),
            divergent_count=Count('pk', filter=~Q(difference_quantity=0)),
            correct_count=Count('pk', filter=Q(difference_quantity=0)),
            shortage_count=Count('pk', filter=Q(difference_quantity__lt=0)),
            surplus_count=Count('pk', filter=Q(difference_quantity__gt=0)),
        )
        summary['inventory_count'] = rows.count()
        if user_has_code(request, 'inventory.view_stock_costs'):
            money_field = DecimalField(max_digits=40, decimal_places=12)
            summary['financial_impact'] = decimal_string(item_rows.aggregate(
                total=Coalesce(
                    Sum('cost_impact'),
                    Value(Decimal('0'), output_field=money_field),
                    output_field=money_field,
                )
            )['total'])
        return self.respond(
            request,
            rows=rows,
            period=canonical_datetime_range(start, end),
            summary=summary,
        )


class StockTransfersReportView(BaseReportView):
    required_permission = 'inventory.report.view'
    query_serializer_class = StockTransfersReportQuerySerializer
    row_serializer_class = StockTransferReportSerializer
    csv_filename = 'relatorio-transferencias-estoque.csv'
    csv_headers = (
        'id', 'origin', 'destination', 'date', 'responsible', 'status',
        'item_count', 'quantities_by_unit', 'cost_value', 'items',
    )

    def serialize_rows(self, rows, request):
        return self.row_serializer_class(
            rows,
            many=True,
            context={
                'request': request,
                'include_cost': user_has_code(request, 'inventory.view_stock_costs'),
            },
        ).data

    def export_headers(self, request):
        if user_has_code(request, 'inventory.view_stock_costs'):
            return self.csv_headers
        return tuple(header for header in self.csv_headers if header != 'cost_value')

    def get(self, request):
        filters, start, end = self.parse_query(request)
        rows = filtered_stock_transfers(
            branch=request.branch_context, start=start, end=end, filters=filters,
        )
        item_rows = StockTransferItem.objects.filter(
            transfer_id__in=rows.order_by().values('pk')
        )
        if filters.get('product') is not None:
            item_rows = item_rows.filter(product_id=filters['product'])
        divergences = TransferDivergence.objects.filter(
            transfer_item_id__in=item_rows.values('pk')
        )
        summary = {
            'transfer_count': rows.count(),
            'item_count': item_rows.count(),
            'divergent_transfer_count': divergences.values(
                'transfer_item__transfer_id'
            ).distinct().count(),
            'pending_divergence_count': divergences.filter(
                status=TransferDivergenceStatus.PENDING
            ).count(),
        }
        if user_has_code(request, 'inventory.view_stock_costs'):
            money_field = DecimalField(max_digits=40, decimal_places=12)
            cost_expression = ExpressionWrapper(
                F('dispatched_quantity') * F('origin_unit_cost_snapshot'),
                output_field=money_field,
            )
            summary['cost_value'] = decimal_string(item_rows.aggregate(
                total=Coalesce(
                    Sum(cost_expression),
                    Value(Decimal('0'), output_field=money_field),
                    output_field=money_field,
                )
            )['total'])
        return self.respond(
            request,
            rows=rows,
            period=canonical_datetime_range(start, end),
            summary=summary,
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


def _purchase_report_queryset(*, branch, start, end, filters):
    queryset = PurchaseOrder.objects.filter(
        branch=branch,
        created_at__gte=start,
        created_at__lt=period_end_exclusive(end),
    ).select_related('supplier').prefetch_related('items__receipt_items')
    for parameter, lookup in (
        ('supplier', 'supplier_id'),
        ('status', 'status'),
        ('order_type', 'order_type'),
        ('product', 'items__product_id'),
    ):
        if filters.get(parameter) is not None:
            queryset = queryset.filter(**{lookup: filters[parameter]})
    if filters.get('search'):
        value = filters['search']
        queryset = queryset.filter(
            Q(order_number__icontains=value)
            | Q(document_number__icontains=value)
            | Q(document_key__icontains=value)
            | Q(supplier__trade_name__icontains=value)
            | Q(items__product_name__icontains=value)
            | Q(items__supplier_name__icontains=value)
        )
    return queryset.distinct().order_by('-created_at', '-id')


def _purchase_supplier_name(order):
    return next(
        (
            item.supplier_name for item in order.items.all()
            if item.supplier_name
        ),
        order.supplier.trade_name,
    )


def _purchase_financials(order):
    item_values = []
    for item in sorted(order.items.all(), key=lambda row: row.pk):
        received_quantity = sum(
            (receipt_item.received_quantity for receipt_item in item.receipt_items.all()),
            Decimal('0.000000'),
        )
        received_stock_quantity = sum(
            (receipt_item.stock_quantity for receipt_item in item.receipt_items.all()),
            Decimal('0.000000'),
        )
        ordered_stock_quantity = item.ordered_quantity * item.conversion_factor
        received_ratio = min(
            received_stock_quantity / ordered_stock_quantity
            if ordered_stock_quantity else Decimal('0'),
            Decimal('1'),
        )
        received_value = (item.effective_total * received_ratio).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP,
        )
        item_values.append({
            'purchase_order_id': order.pk,
            'order_number': order.order_number,
            'item_id': item.pk,
            'line_number': item.line_number,
            'product_name': item.product_name,
            'product_internal_code': item.product_internal_code,
            'presentation': f'{item.presentation_unit_code} - {item.presentation_description}',
            'ordered_quantity': format(item.ordered_quantity, 'f'),
            'received_quantity': format(received_quantity, 'f'),
            'unreceived_quantity': format(
                max(item.ordered_quantity - received_quantity, Decimal('0')), 'f'
            ),
            'ordered_total': item.effective_total,
            'received_total': received_value,
            'unreceived_total': item.effective_total - received_value,
        })
    return {
        'ordered_total': order.payable_total,
        'received_total': sum(
            (item['received_total'] for item in item_values), Decimal('0.00')
        ),
        'unreceived_total': sum(
            (item['unreceived_total'] for item in item_values), Decimal('0.00')
        ),
        'items': item_values,
    }


def _purchase_report_row(order, *, include_cost, financials=None):
    row = {
        'id': order.pk,
        'order_number': order.order_number,
        'created_at': order.created_at,
        'document_date': order.document_date,
        'document_number': order.document_number,
        'supplier_id': order.supplier_id,
        'supplier_name': _purchase_supplier_name(order),
        'order_type': order.order_type,
        'status': order.status,
        'items_count': len(order.items.all()),
    }
    if include_cost:
        financials = financials or _purchase_financials(order)
        row.update({
            'gross_total': decimal_string(order.gross_total),
            'discount': decimal_string(order.global_discount),
            'freight_total': decimal_string(order.freight_total),
            'other_expenses_total': decimal_string(order.other_expenses_total),
            'payable_total': decimal_string(order.payable_total),
            'ordered_total': decimal_string(financials['ordered_total']),
            'received_total': decimal_string(financials['received_total']),
            'unreceived_total': decimal_string(financials['unreceived_total']),
        })
    return row


class PhaseThreeReportOptionsView(APIView):
    permission_classes = (ReportsPermission,)
    permission_by_scope = {
        'purchases': 'purchases.view',
        'suppliers': 'suppliers.view',
        'payables': 'purchases.manage_payables',
    }

    def get(self, request):
        scope = request.query_params.get('scope')
        if scope not in self.permission_by_scope:
            raise ValidationError({'scope': 'Informe um escopo de relatório válido.'})
        start, end = parse_datetime_range(request.query_params, required=True)
        if scope == 'payables':
            supplier_ids = PayableInstallment.objects.filter(
                purchase_order__branch=request.branch_context,
                due_date__gte=start.date(), due_date__lte=end.date(),
            ).values_list('supplier_id', flat=True)
        else:
            supplier_ids = PurchaseOrder.objects.filter(
                branch=request.branch_context,
                created_at__gte=start,
                created_at__lt=period_end_exclusive(end),
            ).values_list('supplier_id', flat=True)
        suppliers = Supplier.objects.filter(branch=request.branch_context).filter(
            Q(status='active', deleted_at__isnull=True) | Q(pk__in=supplier_ids)
        ).order_by('trade_name', 'id')
        return Response({
            'suppliers': [
                {
                    'id': supplier.pk,
                    'name': supplier.trade_name,
                    'status': supplier.status,
                    'historical': supplier.deleted_at is not None,
                }
                for supplier in suppliers
            ]
        })


class PurchaseReportView(BaseReportView):
    required_permission = 'purchases.view'
    query_serializer_class = PurchaseReportQuerySerializer
    csv_filename = 'relatorio-compras.csv'
    csv_headers = (
        'order_number', 'created_at', 'document_date', 'document_number',
        'supplier_name', 'order_type', 'status', 'items_count',
        'gross_total', 'discount', 'freight_total', 'other_expenses_total',
        'ordered_total', 'received_total', 'unreceived_total', 'payable_total',
    )

    def serialize_rows(self, rows, request):
        return list(rows)

    def export_headers(self, request):
        headers = super().export_headers(request)
        if not user_has_code(request, 'purchases.view_costs'):
            return tuple(header for header in headers if header not in (
                'gross_total', 'discount', 'freight_total', 'other_expenses_total',
                'ordered_total', 'received_total', 'unreceived_total', 'payable_total',
            ))
        return headers

    def get(self, request):
        filters, start, end = self.parse_query(request)
        include_cost = user_has_code(request, 'purchases.view_costs')
        orders = list(_purchase_report_queryset(
            branch=request.branch_context, start=start, end=end, filters=filters,
        ))
        financials_by_order = {
            order.pk: _purchase_financials(order) for order in orders
        } if include_cost else {}
        status_groups = {
            status: {
                'status': status,
                'count': 0,
                'ordered_total': Decimal('0.00'),
                'received_total': Decimal('0.00'),
                'unreceived_total': Decimal('0.00'),
            }
            for status in PurchaseOrderStatus.values
        }
        totals = {
            'count': len(orders),
            'items_count': sum(len(order.items.all()) for order in orders),
            'received_count': sum(
                order.status == PurchaseOrderStatus.RECEIVED for order in orders
            ),
            'partial_count': sum(
                order.status == PurchaseOrderStatus.PARTIALLY_RECEIVED for order in orders
            ),
        }
        if include_cost:
            for key in (
                'gross_total', 'global_discount', 'freight_total',
                'other_expenses_total', 'payable_total',
            ):
                totals[key] = sum(
                    (getattr(order, key) for order in orders), Decimal('0.00')
                )
            totals['ordered_total'] = sum(
                (financials['ordered_total'] for financials in financials_by_order.values()),
                Decimal('0.00'),
            )
            totals['received_total'] = sum(
                (financials['received_total'] for financials in financials_by_order.values()),
                Decimal('0.00'),
            )
            totals['unreceived_total'] = sum(
                (financials['unreceived_total'] for financials in financials_by_order.values()),
                Decimal('0.00'),
            )
        for order in orders:
            group = status_groups[order.status]
            group['count'] += 1
            if include_cost:
                financials = financials_by_order[order.pk]
                for key in ('ordered_total', 'received_total', 'unreceived_total'):
                    group[key] += financials[key]
        summary = {
            **totals,
            'status_groups': [
                {
                    'status': group['status'],
                    'count': group['count'],
                    **({
                        key: decimal_string(group[key])
                        for key in ('ordered_total', 'received_total', 'unreceived_total')
                    }
                       if include_cost else {}),
                }
                for group in status_groups.values() if group['count']
            ],
        }
        if include_cost:
            summary = {
                **summary,
                **{
                    key: decimal_string(value)
                    for key, value in totals.items()
                    if key not in ('count', 'items_count', 'received_count', 'partial_count')
                },
                'item_details': [
                    {
                        **{
                            key: value for key, value in item.items()
                            if key not in ('ordered_total', 'received_total', 'unreceived_total')
                        },
                        **{
                            key: decimal_string(item[key])
                            for key in ('ordered_total', 'received_total', 'unreceived_total')
                        },
                    }
                    for financials in financials_by_order.values()
                    for item in financials['items']
                ],
            }
        return self.respond(
            request,
            rows=[
                _purchase_report_row(
                    order,
                    include_cost=include_cost,
                    financials=financials_by_order.get(order.pk),
                )
                for order in orders
            ],
            period=canonical_datetime_range(start, end),
            summary=summary,
        )


class SupplierReportView(BaseReportView):
    required_permission = 'suppliers.view'
    query_serializer_class = SupplierReportQuerySerializer
    csv_filename = 'relatorio-fornecedores.csv'
    csv_headers = (
        'supplier_name', 'status', 'product_count', 'purchase_count',
        'received_count', 'payable_total',
    )

    def serialize_rows(self, rows, request):
        return list(rows)

    def export_headers(self, request):
        headers = super().export_headers(request)
        if not user_has_code(request, 'purchases.view_costs'):
            return tuple(header for header in headers if header != 'payable_total')
        return headers

    def get(self, request):
        filters, start, end = self.parse_query(request)
        include_cost = user_has_code(request, 'purchases.view_costs')
        can_view_purchases = user_has_code(request, 'purchases.view')
        orders = list(_purchase_report_queryset(
            branch=request.branch_context, start=start, end=end, filters={},
        )) if can_view_purchases else []
        historical_ids = {order.supplier_id for order in orders}
        suppliers = Supplier.objects.filter(branch=request.branch_context).filter(
            Q(status='active', deleted_at__isnull=True) | Q(pk__in=historical_ids)
        ).annotate(
            product_count=Count(
                'product_suppliers',
                filter=Q(product_suppliers__status='active'),
                distinct=True,
            )
        )
        if filters.get('supplier') is not None:
            suppliers = suppliers.filter(pk=filters['supplier'])
        if filters.get('status'):
            suppliers = suppliers.filter(status=filters['status'])
        if filters.get('search'):
            value = filters['search']
            suppliers = suppliers.filter(
                Q(trade_name__icontains=value)
                | Q(legal_name__icontains=value)
                | Q(tax_id__icontains=value)
            )
        grouped_orders = {}
        for order in orders:
            grouped_orders.setdefault(order.supplier_id, []).append(order)
        rows = []
        for supplier in suppliers.order_by('trade_name', 'id'):
            supplier_orders = grouped_orders.get(supplier.pk, [])
            row = {
                'supplier_id': supplier.pk,
                'supplier_name': next(
                    (_purchase_supplier_name(order) for order in supplier_orders),
                    supplier.trade_name,
                ),
                'status': supplier.status,
                'historical': supplier.deleted_at is not None,
                'product_count': supplier.product_count,
                'purchase_count': len(supplier_orders),
                'received_count': sum(
                    order.status == PurchaseOrderStatus.RECEIVED
                    for order in supplier_orders
                ),
            }
            if include_cost:
                row['payable_total'] = decimal_string(sum(
                    (order.payable_total for order in supplier_orders), Decimal('0.00')
                ))
            rows.append(row)
        summary = {
            'supplier_count': len(rows),
            'active_count': sum(row['status'] == 'active' for row in rows),
            'historical_count': sum(row['historical'] for row in rows),
            'purchase_count': sum(row['purchase_count'] for row in rows),
        }
        if include_cost:
            summary['payable_total'] = decimal_string(sum(
                (Decimal(row['payable_total']) for row in rows), Decimal('0.00')
            ))
        return self.respond(
            request, rows=rows, period=canonical_datetime_range(start, end), summary=summary,
        )


class PayablesReportView(BaseReportView):
    required_permission = 'purchases.manage_payables'
    query_serializer_class = PayablesReportQuerySerializer
    csv_filename = 'relatorio-contas-a-pagar.csv'
    csv_headers = (
        'order_number', 'supplier_name', 'installment_number', 'due_date', 'amount',
        'status', 'paid_at', 'paid_amount', 'paid_payment_method', 'cancelled_at',
        'cancellation_reason', 'notes',
    )

    def serialize_rows(self, rows, request):
        return list(rows)

    def get(self, request):
        filters, start, end = self.parse_query(request)
        queryset = PayableInstallment.objects.select_related(
            'supplier', 'purchase_order',
        ).prefetch_related('purchase_order__items').filter(
            purchase_order__branch=request.branch_context,
        )
        end_exclusive = period_end_exclusive(end)
        if filters['date_basis'] == 'settlement_date':
            queryset = queryset.filter(
                Q(paid_at__gte=start, paid_at__lt=end_exclusive)
                | Q(cancelled_at__gte=start, cancelled_at__lt=end_exclusive)
            )
        else:
            queryset = queryset.filter(
                due_date__gte=start.date(), due_date__lte=end.date(),
            )
        for parameter, lookup in (('supplier', 'supplier_id'), ('status', 'status')):
            if filters.get(parameter) is not None:
                queryset = queryset.filter(**{lookup: filters[parameter]})
        if filters.get('search'):
            value = filters['search']
            queryset = queryset.filter(
                Q(purchase_order__order_number__icontains=value)
                | Q(supplier__trade_name__icontains=value)
                | Q(purchase_order__items__supplier_name__icontains=value)
            )
        installments = list(queryset.distinct().order_by('due_date', 'installment_number', 'id'))
        groups = {
            status: {'status': status, 'count': 0, 'amount': Decimal('0.00')}
            for status in PayableInstallmentStatus.values
        }
        rows = []
        for installment in installments:
            group = groups[installment.status]
            group['count'] += 1
            group['amount'] += installment.amount
            order = installment.purchase_order
            rows.append({
                'id': installment.pk,
                'purchase_order_id': order.pk,
                'order_number': order.order_number,
                'supplier_id': installment.supplier_id,
                'supplier_name': _purchase_supplier_name(order),
                'installment_number': installment.installment_number,
                'due_date': installment.due_date,
                'amount': decimal_string(installment.amount),
                'status': installment.status,
                'paid_at': installment.paid_at,
                'paid_amount': decimal_string(installment.paid_amount)
                if installment.paid_amount is not None else None,
                'paid_payment_method': installment.paid_payment_method,
                'cancelled_at': installment.cancelled_at,
                'cancellation_reason': installment.cancellation_reason,
                'notes': installment.notes,
            })
        summary = {
            'date_basis': filters['date_basis'],
            'count': len(installments),
            'pending_total': decimal_string(groups[PayableInstallmentStatus.PENDING]['amount']),
            'paid_total': decimal_string(groups[PayableInstallmentStatus.PAID]['amount']),
            'cancelled_total': decimal_string(groups[PayableInstallmentStatus.CANCELLED]['amount']),
            'overdue_total': decimal_string(sum(
                (
                    installment.amount for installment in installments
                    if installment.status == PayableInstallmentStatus.PENDING
                    and installment.due_date < timezone.localdate()
                ),
                Decimal('0.00'),
            )),
            'status_groups': [
                {
                    'status': group['status'],
                    'count': group['count'],
                    'amount': decimal_string(group['amount']),
                }
                for group in groups.values() if group['count']
            ],
        }
        return self.respond(
            request, rows=rows, period=canonical_datetime_range(start, end), summary=summary,
        )


def _command_name(command):
    return command.command_number or str(command.pk)


def _command_table_name(command):
    return command.table_name_snapshot or (command.table.name if command.table_id else '')


def _command_customer_name(command):
    return command.customer_name_snapshot or (command.customer.name if command.customer_id else '')


def _command_operator_name(command, field):
    snapshot = getattr(command, f'{field}_name_snapshot', '')
    user = getattr(command, field, None)
    return snapshot or (readable_user_name(user) if user else '')


def _command_subtotal(command):
    return sum((
        item.quantity * item.unit_price
        for order in command.orders.all()
        for item in order.items.all()
        if item.status == OrderItemStatus.CONFIRMED
    ), Decimal('0.00'))


def _command_financials(command):
    subtotal = _command_subtotal(command)
    if command.sale_id:
        sale = command.sale
        return {
            'subtotal': sale.subtotal,
            'discount': sale.promotion_discount_total + sale.item_discount_total + sale.discount,
            'service_fee': sale.service_fee_amount,
            'total': sale.total,
            'sale_id': sale.pk,
            'sale_number': sale.sale_number,
            'sale_status': sale.status,
        }
    # Open commands have no final-sale snapshot yet. Keep the recorded checkout
    # discount, but do not recalculate promotions or service fees dynamically.
    return {
        'subtotal': subtotal,
        'discount': command.checkout_discount,
        'service_fee': Decimal('0.00'),
        'total': max(subtotal - command.checkout_discount, Decimal('0.00')),
        'sale_id': None,
        'sale_number': '',
        'sale_status': None,
    }


def _command_queryset(*, branch, filters):
    queryset = Command.objects.select_related(
        'table', 'customer', 'opened_by', 'closed_by', 'sale', 'sale__seller_user',
    ).prefetch_related('orders__items', 'sale__items').filter(branch=branch)
    if filters.get('status'):
        queryset = queryset.filter(status=filters['status'])
    if filters.get('table') is not None:
        queryset = queryset.filter(table_id=filters['table'])
    if filters.get('customer') is not None:
        queryset = queryset.filter(customer_id=filters['customer'])
    if filters.get('operator') is not None:
        queryset = queryset.filter(
            Q(opened_by_id=filters['operator'])
            | Q(closed_by_id=filters['operator'])
            | Q(sale__seller_user_id=filters['operator'])
        )
    if filters.get('payment_method') is not None:
        queryset = queryset.filter(payments__payment_method_id=filters['payment_method'])
    if filters.get('command'):
        value = filters['command']
        queryset = queryset.filter(
            Q(command_number__icontains=value) | Q(identifier__icontains=value)
        )
    return queryset.distinct()


def _command_period_queryset(queryset, start, end):
    end_exclusive = period_end_exclusive(end)
    return queryset.filter(
        Q(created_at__gte=start, created_at__lt=end_exclusive)
        | Q(closed_at__gte=start, closed_at__lt=end_exclusive)
    )


def _modifier_label(snapshot):
    labels = []
    for modifier in snapshot or []:
        group = modifier.get('group_name', '')
        option = modifier.get('option_name', '')
        labels.append(' - '.join(value for value in (group, option) if value))
    return '; '.join(label for label in labels if label)


def _command_item_sale_snapshots(command):
    confirmed = sorted((
        item for order in command.orders.all() for item in order.items.all()
        if item.status == OrderItemStatus.CONFIRMED
    ), key=lambda item: item.pk)
    sale_items = list(command.sale.items.all()) if command.sale_id else []
    return {item.pk: sale_item for item, sale_item in zip(confirmed, sale_items)}


def _operation_command_ids(operation):
    result = operation.result or {}
    source = result.get('source') or {}
    destination = result.get('destination') or {}
    return {
        value for value in (
            result.get('command_id'), result.get('source_command_id'),
            source.get('id'), destination.get('id'),
        ) if value is not None
    }


def _operation_matches_command_scope(operation, command_ids, table_id=None):
    if not (_operation_command_ids(operation) & command_ids):
        return False
    if table_id is None:
        return True
    result = operation.result or {}
    return table_id in {
        reference.get('table_id')
        for reference in (result.get('source') or {}, result.get('destination') or {})
    }


class CommandsReportOptionsView(APIView):
    permission_classes = (ReportsPermission,)
    required_permission = 'commands.view'

    def get(self, request):
        start, end = parse_datetime_range(request.query_params, required=True)
        branch = request.branch_context
        commands = _command_period_queryset(
            Command.objects.filter(branch=branch), start, end,
        )
        table_ids = commands.exclude(table_id=None).values_list('table_id', flat=True)
        customer_ids = commands.exclude(customer_id=None).values_list('customer_id', flat=True)
        operator_ids = set(commands.values_list('opened_by_id', flat=True))
        operator_ids.update(commands.exclude(closed_by_id=None).values_list('closed_by_id', flat=True))
        operator_ids.update(commands.exclude(sale__seller_user_id=None).values_list('sale__seller_user_id', flat=True))
        return Response({
            'tables': [
                {'id': table.pk, 'name': table.name, 'historical': table.status != 'active'}
                for table in Table.objects.filter(branch=branch).filter(
                    Q(status='active') | Q(pk__in=table_ids)
                ).order_by('name', 'id')
            ],
            'customers': [
                {'id': customer.pk, 'name': customer.name, 'historical': customer.status != 'active'}
                for customer in Customer.objects.filter(company=branch.company).filter(
                    Q(status='active') | Q(pk__in=customer_ids)
                ).order_by('name', 'id')
            ],
            'operators': [
                {'id': user.pk, 'name': readable_user_name(user)}
                for user in User.objects.filter(pk__in=operator_ids).order_by('first_name', 'last_name', 'email', 'id')
            ],
            'payment_methods': [
                {'id': method.pk, 'name': method.name, 'historical': method.status != 'active'}
                for method in PaymentMethod.objects.filter(company=branch.company).filter(
                    Q(status='active') | Q(command_payments__command__branch=branch)
                ).distinct().order_by('name', 'id')
            ],
        })


class CommandsReportView(BaseReportView):
    required_permission = 'commands.view'
    query_serializer_class = CommandsReportQuerySerializer
    csv_filename = 'relatorio-mesas-comandas.csv'
    csv_headers = (
        'command_number', 'table_name', 'created_at', 'closed_at', 'opened_by_name',
        'closed_by_name', 'customer_name', 'items_count', 'subtotal', 'discount',
        'service_fee', 'total', 'status',
    )

    def serialize_rows(self, rows, request):
        return list(rows)

    def export_headers(self, request):
        headers = {
            'commands': self.csv_headers,
            'items': (
                'command_number', 'table_name', 'product_name', 'internal_code',
                'category_name', 'quantity', 'modifiers', 'promotion', 'discount',
                'subtotal', 'status', 'cancelled_at', 'cancellation_reason',
            ),
            'payments': (
                'command_number', 'table_name', 'payment_method', 'amount',
                'received_amount', 'change_amount', 'command_total', 'is_partial',
                'status', 'reversal_reason', 'operator_name', 'sale_number', 'created_at',
            ),
            'cancellations': (
                'command_number', 'table_name', 'product_name', 'quantity', 'amount',
                'responsible_name', 'authorized_by_name', 'reason', 'cancelled_at',
            ),
            'operations': (
                'operation_label', 'source_command', 'source_table', 'destination_command',
                'destination_table', 'item_ids', 'responsible_name', 'created_at',
            ),
        }
        return headers[request.query_params.get('section', 'commands')]

    def _summary(self, branch, filters, start, end):
        scope = _command_queryset(branch=branch, filters=filters)
        end_exclusive = period_end_exclusive(end)
        opened = list(scope.filter(created_at__gte=start, created_at__lt=end_exclusive))
        closed = list(scope.filter(closed_at__gte=start, closed_at__lt=end_exclusive))
        finalized = [command for command in closed if command.sale_id and command.sale.status == SaleStatus.FINALIZED]
        cancellations = OrderItem.objects.filter(
            order__command__in=scope, status=OrderItemStatus.CANCELLED,
            cancelled_at__gte=start, cancelled_at__lt=end_exclusive,
        )
        operation_command_ids = set(scope.values_list('pk', flat=True))
        operations = [operation for operation in CommandOperation.objects.filter(
            branch=branch, created_at__gte=start, created_at__lt=end_exclusive,
        ) if _operation_matches_command_scope(
            operation, operation_command_ids, filters.get('table'),
        )]
        return {
            'opened_tables': len({command.table_id for command in opened if command.table_id}),
            'opened_commands': len(opened),
            'closed_commands': len(closed),
            'associated_revenue': decimal_string(sum((command.sale.total for command in finalized), Decimal('0.00'))),
            'average_ticket': decimal_string(
                sum((command.sale.total for command in finalized), Decimal('0.00')) / len(finalized)
                if finalized else Decimal('0.00')
            ),
            'average_stay_minutes': decimal_string(
                sum(((command.closed_at - command.created_at).total_seconds() / 60 for command in closed), 0)
                / len(closed) if closed else 0,
                places=1,
            ),
            'cancelled_items': cancellations.count(),
            'cancelled_value': decimal_string(sum((
                item.quantity * item.unit_price for item in cancellations
            ), Decimal('0.00'))),
            'operations_count': len(operations),
        }

    def _command_rows(self, commands):
        rows = []
        for command in commands:
            financials = _command_financials(command)
            rows.append({
                'id': command.pk,
                'command_number': _command_name(command),
                'identifier': command.identifier,
                'table_name': _command_table_name(command),
                'created_at': command.created_at,
                'closed_at': command.closed_at,
                'opened_by_name': _command_operator_name(command, 'opened_by'),
                'closed_by_name': _command_operator_name(command, 'closed_by'),
                'attendant_name': readable_user_name(command.sale.seller_user) if command.sale_id and command.sale.seller_user_id else '',
                'customer_id': command.customer_id,
                'customer_name': _command_customer_name(command),
                'items_count': sum(len(order.items.all()) for order in command.orders.all()),
                **{key: decimal_string(value) for key, value in financials.items() if key in ('subtotal', 'discount', 'service_fee', 'total')},
                **{key: value for key, value in financials.items() if key not in ('subtotal', 'discount', 'service_fee', 'total')},
                'status': command.status,
            })
        return rows

    def _item_rows(self, queryset):
        rows = []
        snapshots = {}
        for item in queryset:
            command = item.order.command
            if command.pk not in snapshots:
                snapshots[command.pk] = _command_item_sale_snapshots(command)
            sale_item = snapshots[command.pk].get(item.pk)
            rows.append({
                'id': item.pk,
                'command_id': command.pk,
                'command_number': _command_name(command),
                'table_name': _command_table_name(command),
                'product_name': item.product_name,
                'internal_code': item.internal_code,
                'category_name': item.category_name_snapshot or item.product.category.name,
                'quantity': decimal_string(item.quantity, places=3),
                'modifiers': _modifier_label(item.modifier_snapshot),
                'promotion': sale_item.promotion_name if sale_item else '',
                'discount': decimal_string(
                    (sale_item.promotion_benefit + sale_item.manual_discount) if sale_item else Decimal('0.00')
                ),
                'subtotal': decimal_string(item.quantity * item.unit_price),
                'status': item.status,
                'cancelled_at': item.cancelled_at,
                'cancellation_reason': item.cancellation_reason,
            })
        return rows

    def _payment_rows(self, queryset):
        rows = []
        for payment in queryset:
            financials = _command_financials(payment.command)
            reversed_payment = getattr(payment, 'reversal', None)
            rows.append({
                'id': payment.pk,
                'command_id': payment.command_id,
                'command_number': _command_name(payment.command),
                'table_name': _command_table_name(payment.command),
                'payment_method': payment.payment_method.name,
                'amount': decimal_string(payment.amount),
                'received_amount': decimal_string(payment.received_amount) if payment.received_amount is not None else None,
                'change_amount': decimal_string(payment.change_amount) if payment.change_amount is not None else None,
                'command_total': decimal_string(financials['total']),
                'is_partial': payment.amount < financials['total'],
                'status': 'reversed' if payment.status == CommandPaymentStatus.REVERSED or reversed_payment else payment.status,
                'reversal_reason': payment.reversal_reason or (reversed_payment.reversal_reason if reversed_payment else ''),
                'operator_name': readable_user_name(payment.operator),
                'created_at': payment.created_at,
                'sale_id': financials['sale_id'],
                'sale_number': financials['sale_number'],
            })
        return rows

    def _cancellation_rows(self, queryset):
        return [{
            'id': item.pk,
            'command_id': item.order.command_id,
            'command_number': _command_name(item.order.command),
            'table_name': _command_table_name(item.order.command),
            'product_name': item.product_name,
            'quantity': decimal_string(item.quantity, places=3),
            'amount': decimal_string(item.quantity * item.unit_price),
            'responsible_name': readable_user_name(item.cancelled_by) if item.cancelled_by_id else '',
            'authorized_by_name': '',
            'reason': item.cancellation_reason,
            'cancelled_at': item.cancelled_at,
        } for item in queryset]

    def _operation_rows(self, queryset, branch):
        operation_ids = [str(operation.pk) for operation in queryset]
        audits = AuditLog.objects.filter(
            branch=branch, metadata__operation_reference__in=operation_ids,
        ).select_related('actor')
        actors = {str(audit.metadata.get('operation_reference')): audit.actor for audit in audits}
        labels = {
            CommandOperationType.TRANSFER: 'Transferência entre mesas',
            CommandOperationType.TRANSFER_ITEMS: 'Transferência de itens',
            CommandOperationType.MERGE: 'Merge de comandas',
            CommandOperationType.SPLIT: 'Split de comanda',
        }
        rows = []
        for operation in queryset:
            result = operation.result or {}
            source = result.get('source') or {}
            destination = result.get('destination') or {}
            rows.append({
                'id': operation.pk,
                'operation_type': operation.operation_type,
                'operation_label': labels[operation.operation_type],
                'source_command': source.get('number') or result.get('source_command_id') or '',
                'source_table': source.get('table_name', ''),
                'destination_command': destination.get('number') or result.get('command_id') or '',
                'destination_table': destination.get('table_name', ''),
                'item_ids': result.get('item_ids', []),
                'responsible_name': result.get('responsible_name') or (
                    readable_user_name(actors[str(operation.pk)])
                    if actors.get(str(operation.pk)) else ''
                ),
                'created_at': operation.created_at,
            })
        return rows

    def get(self, request):
        filters, start, end = self.parse_query(request)
        section = filters['section']
        if section == 'payments' and not user_has_code(request, 'commands.payments.view'):
            raise PermissionDenied('Você não possui permissão para consultar pagamentos de comandas.')
        branch = request.branch_context
        command_scope = _command_queryset(branch=branch, filters=filters)
        end_exclusive = period_end_exclusive(end)
        summary = self._summary(branch, filters, start, end)
        if section == 'commands':
            rows = self._command_rows(_command_period_queryset(command_scope, start, end).order_by('-created_at', '-id'))
        elif section == 'items':
            rows = self._item_rows(OrderItem.objects.select_related(
                'product__category', 'order__command__table', 'order__command__customer',
                'order__command__opened_by', 'order__command__closed_by', 'order__command__sale',
            ).prefetch_related('order__command__orders__items', 'order__command__sale__items').filter(
                order__command__in=command_scope, created_at__gte=start, created_at__lt=end_exclusive,
            ).order_by('-created_at', '-id'))
        elif section == 'payments':
            rows = self._payment_rows(CommandPayment.objects.select_related(
                'command__table', 'command__customer', 'command__opened_by', 'command__closed_by',
                'command__sale', 'payment_method', 'operator', 'reversal',
            ).prefetch_related('command__orders__items').filter(
                command__in=command_scope, created_at__gte=start, created_at__lt=end_exclusive,
            ).order_by('-created_at', '-id'))
        elif section == 'cancellations':
            rows = self._cancellation_rows(OrderItem.objects.select_related(
                'order__command__table', 'order__command__customer', 'order__command__opened_by',
                'order__command__closed_by', 'cancelled_by',
            ).filter(
                order__command__in=command_scope, status=OrderItemStatus.CANCELLED,
                cancelled_at__gte=start, cancelled_at__lt=end_exclusive,
            ).order_by('-cancelled_at', '-id'))
        else:
            command_ids = set(command_scope.values_list('pk', flat=True))
            operations = [operation for operation in CommandOperation.objects.filter(
                branch=branch, created_at__gte=start, created_at__lt=end_exclusive,
            ).order_by('-created_at', '-id') if _operation_matches_command_scope(
                operation, command_ids, filters.get('table'),
            )]
            rows = self._operation_rows(operations, branch)
        return self.respond(
            request, rows=rows, period=canonical_datetime_range(start, end), summary=summary,
        )


def _phase_five_item_matches(item, filters):
    return (
        (filters.get('product') is None or item.product_id == filters['product'])
        and (
            filters.get('category') is None
            or item.category_id_snapshot == filters['category']
        )
    )


def _phase_five_events(*, branch, start, end, filters):
    sale_filters = {
        key: value for key, value in filters.items()
        if key in ('customer', 'product', 'category', 'channel', 'search')
    }
    inflows, reversals = period_event_sales(
        branch=branch, start=start, end=end, filters=sale_filters,
        operation_types=(OperationType.SALE,),
    )
    return [
        (sale, sign, sale.created_at if sign > 0 else sale.cancelled_at)
        for sales, sign in ((inflows, 1), (reversals, -1))
        for sale in sales
    ]


def _phase_five_customer_name(sale):
    return sale.customer_name_snapshot or (
        sale.customer.name if sale.customer_id else ''
    )


def _human_quantity(value):
    value = Decimal(value or 0)
    normalized = format(value.normalize(), 'f')
    if '.' not in normalized:
        return normalized
    integer, fraction = normalized.split('.', 1)
    return f'{integer},{fraction.rstrip("0")}'


def _redact_phase_five_impact(request, rows):
    can_view_sales = user_has_code(request, 'sales.view')
    can_view_team = user_has_code(request, 'reports.view_team')
    redacted = []
    for row in rows:
        row = dict(row)
        if not can_view_sales:
            row.pop('sale_id', None)
            row.pop('sale_number', None)
        if not can_view_team:
            row.pop('operator_name', None)
        redacted.append(row)
    return redacted


def _phase_five_promotion_data(events, filters):
    promotions = {}
    products = {}
    impact = []
    for sale, sign, event_at in events:
        for item in sale.items.all():
            if not item.promotion_id or not _phase_five_item_matches(item, filters):
                continue
            if filters.get('promotion') is not None and item.promotion_id != filters['promotion']:
                continue
            key = item.promotion_id
            row = promotions.setdefault(key, {
                'promotion_id': item.promotion_id,
                'promotion_name': item.promotion_name or 'Promoção sem nome',
                'promotion_type': promotion_discount_type_label(item.promotion_discount_type),
                'promotion_value': promotion_discount_value_label(
                    item.promotion_discount_type, item.promotion_discount_value,
                ),
                'promotion_value_raw': decimal_string(item.promotion_discount_value),
                'uses': 0,
                'affected_quantity': Decimal('0.000'),
                'gross_value': Decimal('0.00'),
                'discount': Decimal('0.00'),
                'net_revenue': Decimal('0.00'),
                'product_ids': set(),
                'sale_ids': set(),
                'operator_ids': set(),
            })
            row['uses'] += sign
            row['affected_quantity'] += sign * item.quantity
            row['gross_value'] += sign * item.subtotal
            row['discount'] += sign * item.promotion_benefit
            row['net_revenue'] += sign * item.net_subtotal
            row['product_ids'].add(item.product_id)
            row['sale_ids'].add(sale.pk)
            row['operator_ids'].add(sale.created_by_id)
            product_key = (item.promotion_id, item.product_id)
            product_row = products.setdefault(product_key, {
                'promotion_id': item.promotion_id,
                'promotion_name': item.promotion_name or 'Promoção sem nome',
                'product_id': item.product_id,
                'product_name': item.product_name,
                'internal_code': item.internal_code,
                'category_name': item.category_name_snapshot,
                'quantity': Decimal('0.000'),
                'gross_value': Decimal('0.00'),
                'discount': Decimal('0.00'),
                'net_revenue': Decimal('0.00'),
            })
            product_row['quantity'] += sign * item.quantity
            product_row['gross_value'] += sign * item.subtotal
            product_row['discount'] += sign * item.promotion_benefit
            product_row['net_revenue'] += sign * item.net_subtotal
            impact.append({
                'id': f'{sale.pk}-{item.pk}-{sign}', 'sale_id': sale.pk,
                'sale_number': sale.sale_number, 'event_type': 'inflow' if sign > 0 else 'reversal',
                'event_at': event_at, 'promotion_id': item.promotion_id,
                'promotion_name': item.promotion_name or 'Promoção sem nome',
                'product_name': item.product_name, 'quantity': _human_quantity(sign * item.quantity),
                'gross_value': decimal_string(sign * item.subtotal),
                'discount': decimal_string(sign * item.promotion_benefit),
                'net_revenue': decimal_string(sign * item.net_subtotal),
                'operator_name': readable_user_name(sale.created_by),
            })
    rows = []
    for row in promotions.values():
        rows.append({
            **{key: value for key, value in row.items() if key not in ('product_ids', 'sale_ids', 'operator_ids')},
            'affected_quantity': _human_quantity(row['affected_quantity']),
            'gross_value': decimal_string(row['gross_value']),
            'discount': decimal_string(row['discount']),
            'net_revenue': decimal_string(row['net_revenue']),
            'product_count': len(row['product_ids']), 'sale_count': len(row['sale_ids']),
            'operator_count': len(row['operator_ids']),
        })
    product_rows = [{
        **{key: value for key, value in row.items() if key not in ('quantity', 'gross_value', 'discount', 'net_revenue')},
        'quantity': _human_quantity(row['quantity']), 'gross_value': decimal_string(row['gross_value']),
        'discount': decimal_string(row['discount']), 'net_revenue': decimal_string(row['net_revenue']),
    } for row in products.values()]
    return sorted(rows, key=lambda row: (-row['uses'], row['promotion_name'])), sorted(
        product_rows, key=lambda row: (-Decimal(row['net_revenue']), row['promotion_name'], row['product_name'])
    ), sorted(impact, key=lambda row: (row['event_at'], row['id']), reverse=True)


def _phase_five_modifier_data(events, filters):
    modifiers = {}
    products = {}
    impact = []
    for sale, sign, event_at in events:
        for item in sale.items.all():
            if not _phase_five_item_matches(item, filters):
                continue
            for snapshot in item.modifier_snapshot or []:
                group_name = snapshot.get('group_name') or 'Grupo sem nome'
                option_name = snapshot.get('option_name') or 'Modificador sem nome'
                key = (snapshot.get('group_id') or group_name, snapshot.get('option_id') or option_name)
                selected_quantity = Decimal(str(snapshot.get('selected_quantity') or 0)) * item.quantity
                contribution = Decimal(str(snapshot.get('contribution') or 0)) * item.quantity
                row = modifiers.setdefault(key, {
                    'group_id': snapshot.get('group_id'), 'group_name': group_name,
                    'option_id': snapshot.get('option_id'), 'option_name': option_name,
                    'option_type': snapshot.get('option_type'), 'quantity': Decimal('0.000'),
                    'additional_revenue': Decimal('0.00'), 'product_ids': set(), 'sale_ids': set(),
                })
                row['quantity'] += sign * selected_quantity
                row['additional_revenue'] += sign * contribution
                row['product_ids'].add(item.product_id)
                row['sale_ids'].add(sale.pk)
                product_key = (*key, item.product_id)
                product_row = products.setdefault(product_key, {
                    'group_id': snapshot.get('group_id'), 'option_id': snapshot.get('option_id'),
                    'group_name': group_name, 'option_name': option_name, 'product_id': item.product_id,
                    'product_name': item.product_name, 'internal_code': item.internal_code,
                    'category_name': item.category_name_snapshot, 'quantity': Decimal('0.000'),
                    'additional_revenue': Decimal('0.00'),
                })
                product_row['quantity'] += sign * selected_quantity
                product_row['additional_revenue'] += sign * contribution
                impact.append({
                    'id': f'{sale.pk}-{item.pk}-{key[0]}-{key[1]}-{sign}', 'sale_id': sale.pk,
                    'sale_number': sale.sale_number, 'event_type': 'inflow' if sign > 0 else 'reversal',
                    'event_at': event_at, 'group_name': group_name, 'option_name': option_name,
                    'product_name': item.product_name, 'quantity': _human_quantity(sign * selected_quantity),
                    'additional_revenue': decimal_string(sign * contribution),
                    'operator_name': readable_user_name(sale.created_by),
                })
    rows = [{
        **{key: value for key, value in row.items() if key not in ('quantity', 'additional_revenue', 'product_ids', 'sale_ids')},
        'quantity': _human_quantity(row['quantity']),
        'additional_revenue': decimal_string(row['additional_revenue']),
        'product_count': len(row['product_ids']), 'sale_count': len(row['sale_ids']),
    } for row in modifiers.values()]
    product_rows = [{
        **{key: value for key, value in row.items() if key not in ('quantity', 'additional_revenue')},
        'quantity': _human_quantity(row['quantity']),
        'additional_revenue': decimal_string(row['additional_revenue']),
    } for row in products.values()]
    return sorted(rows, key=lambda row: (-Decimal(row['quantity']), row['group_name'], row['option_name'])), sorted(
        product_rows, key=lambda row: (-Decimal(row['additional_revenue']), row['group_name'], row['option_name'])
    ), sorted(impact, key=lambda row: (row['event_at'], row['id']), reverse=True)


class CommercialComplementsOptionsView(APIView):
    permission_classes = (ReportsPermission,)
    required_permission = 'reports.view_products'
    permission_by_scope = {
        'promotions': 'reports.view_products', 'modifiers': 'reports.view_products',
        'customers': 'reports.view_sales',
    }

    def get(self, request):
        scope = request.query_params.get('scope')
        if scope not in self.permission_by_scope:
            raise ValidationError({'scope': 'Informe um escopo de relatório válido.'})
        if scope == 'customers' and not user_has_code(request, 'customers.view'):
            raise PermissionDenied('Você não possui permissão para consultar dados de clientes.')
        start, end = parse_datetime_range(request.query_params, required=True)
        branch = request.branch_context
        end_exclusive = period_end_exclusive(end)
        sales_in_period = Sale.objects.filter(branch=branch).filter(
            Q(created_at__gte=start, created_at__lt=end_exclusive)
            | Q(cancelled_at__gte=start, cancelled_at__lt=end_exclusive)
        )
        item_history = SaleItem.objects.filter(sale__in=sales_in_period)
        historical_product_ids = item_history.values_list('product_id', flat=True)
        historical_category_ids = item_history.exclude(category_id_snapshot=None).values_list(
            'category_id_snapshot', flat=True,
        )
        response = {
            'products': list(Product.objects.filter(company=branch.company).filter(
                Q(status='active', archived_at__isnull=True) | Q(pk__in=historical_product_ids)
            ).order_by('name', 'id').values(
                'id', 'name', 'internal_code', 'status',
            )),
            'categories': list(Category.objects.filter(branch=branch).filter(
                Q(status='active', deleted_at__isnull=True) | Q(pk__in=historical_category_ids)
            ).order_by('name', 'id').values(
                'id', 'name', 'status',
            )),
        }
        if scope == 'promotions':
            promotion_ids = item_history.exclude(
                promotion_id=None,
            ).values_list('promotion_id', flat=True)
            response['promotions'] = [
                {'id': promotion.pk, 'name': promotion.name, 'historical': promotion.status != 'active'}
                for promotion in Promotion.objects.filter(company=branch.company).filter(
                    Q(status='active') | Q(pk__in=promotion_ids)
                ).order_by('name', 'id')
            ]
        if scope == 'customers':
            customer_ids = sales_in_period.exclude(customer_id=None).values_list('customer_id', flat=True)
            response['customers'] = [
                {'id': customer.pk, 'name': customer.name, 'historical': customer.status != 'active'}
                for customer in Customer.objects.filter(company=branch.company).filter(
                    Q(status='active') | Q(pk__in=customer_ids)
                ).order_by('name', 'id')
            ]
        return Response(response)


class CommercialComplementReportView(BaseReportView):
    required_permission = 'reports.view_products'
    query_serializer_class = CommercialComplementsReportQuerySerializer
    report_kind = None
    csv_filename = 'relatorio-comercial-complementar.csv'

    def serialize_rows(self, rows, request):
        return list(rows)

    def export_headers(self, request):
        headers = {
            'promotions': {
                'records': (
                    'promotion_name', 'promotion_type', 'promotion_value_raw', 'uses',
                    'affected_quantity', 'gross_value', 'discount', 'net_revenue',
                    'product_count', 'sale_count', 'operator_count',
                ),
                'products': (
                    'promotion_name', 'product_name', 'internal_code', 'category_name',
                    'quantity', 'gross_value', 'discount', 'net_revenue',
                ),
                'impact': (
                    'sale_number', 'event_type', 'event_at', 'promotion_name', 'product_name',
                    'quantity', 'gross_value', 'discount', 'net_revenue', 'operator_name',
                ),
            },
            'modifiers': {
                'records': (
                    'group_name', 'option_name', 'option_type', 'quantity',
                    'additional_revenue', 'product_count', 'sale_count', 'participation',
                ),
                'products': (
                    'group_name', 'option_name', 'product_name', 'internal_code',
                    'category_name', 'quantity', 'additional_revenue',
                ),
                'impact': (
                    'sale_number', 'event_type', 'event_at', 'group_name', 'option_name',
                    'product_name', 'quantity', 'additional_revenue', 'operator_name',
                ),
            },
        }
        headers = headers[self.report_kind][request.query_params.get('section', 'records')]
        if request.query_params.get('section') == 'impact':
            if not user_has_code(request, 'sales.view'):
                headers = tuple(header for header in headers if header != 'sale_number')
            if not user_has_code(request, 'reports.view_team'):
                headers = tuple(header for header in headers if header != 'operator_name')
        return headers

    def get(self, request):
        filters, start, end = self.parse_query(request)
        section = filters['section']
        if section not in ('records', 'products', 'impact'):
            raise ValidationError({'section': 'Informe uma aba válida para este relatório.'})
        events = _phase_five_events(
            branch=request.branch_context, start=start, end=end, filters=filters,
        )
        if self.report_kind == 'promotions':
            records, products, impact = _phase_five_promotion_data(events, filters)
            summary = {
                'uses': sum((row['uses'] for row in records), 0),
                'affected_quantity': _human_quantity(sum((
                    Decimal(row['affected_quantity'].replace(',', '.')) for row in records
                ), Decimal('0.000'))),
                'gross_value': decimal_string(sum((Decimal(row['gross_value']) for row in records), Decimal('0.00'))),
                'discount': decimal_string(sum((Decimal(row['discount']) for row in records), Decimal('0.00'))),
                'net_revenue': decimal_string(sum((Decimal(row['net_revenue']) for row in records), Decimal('0.00'))),
                'promotion_count': len(records), 'product_count': len({row['product_id'] for row in products}),
            }
        else:
            records, products, impact = _phase_five_modifier_data(events, filters)
            total_revenue = sum((sale.total * sign for sale, sign, _at in events), Decimal('0.00'))
            for row in records:
                row['participation'] = decimal_string(
                    Decimal(row['additional_revenue']) * Decimal('100') / total_revenue
                    if total_revenue else Decimal('0.00')
                )
            summary = {
                'quantity': _human_quantity(sum((
                    Decimal(row['quantity'].replace(',', '.')) for row in records
                ), Decimal('0.000'))),
                'additional_revenue': decimal_string(sum((Decimal(row['additional_revenue']) for row in records), Decimal('0.00'))),
                'modifier_count': len(records), 'group_count': len({row['group_name'] for row in records}),
                'product_count': len({row['product_id'] for row in products}),
                'participation': decimal_string(
                    sum((Decimal(row['additional_revenue']) for row in records), Decimal('0.00'))
                    * Decimal('100') / total_revenue if total_revenue else Decimal('0.00')
                ),
            }
        rows = {'records': records, 'products': products, 'impact': impact}[section]
        if section == 'impact':
            rows = _redact_phase_five_impact(request, rows)
        return self.respond(
            request, rows=rows, period=canonical_datetime_range(start, end), summary=summary,
        )


class PromotionsReportView(CommercialComplementReportView):
    report_kind = 'promotions'
    csv_filename = 'relatorio-promocoes.csv'


class ModifiersReportView(CommercialComplementReportView):
    report_kind = 'modifiers'
    csv_filename = 'relatorio-modificadores.csv'


def _phase_five_customer_data(events, filters):
    customers = {}
    products = {}
    sales = []
    sale_signs = {}
    anonymous_sales = 0
    for sale, sign, event_at in events:
        sale_signs[sale.pk] = sale_signs.get(sale.pk, 0) + sign
        if sale.customer_id is None:
            anonymous_sales += sign
            continue
        customer = customers.setdefault(sale.customer_id, {
            'customer_id': sale.customer_id, 'customer_name': _phase_five_customer_name(sale),
            'customer_status': export_value(sale.customer.status) if sale.customer_id else '', 'sales_count': 0,
            'total_purchased': Decimal('0.00'), 'last_purchase_at': None, 'sale_ids': set(),
        })
        customer['sales_count'] += sign
        customer['total_purchased'] += sign * sale.total
        customer['sale_ids'].add(sale.pk)
        if sign > 0 and (customer['last_purchase_at'] is None or sale.created_at > customer['last_purchase_at']):
            customer['last_purchase_at'] = sale.created_at
        sales.append({
            'id': f'{sale.pk}-{sign}', 'sale_id': sale.pk, 'sale_number': sale.sale_number,
            'customer_id': sale.customer_id, 'customer_name': _phase_five_customer_name(sale),
            'event_type': 'inflow' if sign > 0 else 'reversal', 'event_at': event_at,
            'channel': sale.channel, 'operator_name': readable_user_name(sale.created_by),
            'total': decimal_string(sign * sale.total),
        })
        for item in sale.items.all():
            if not _phase_five_item_matches(item, filters):
                continue
            key = (sale.customer_id, item.product_id)
            product = products.setdefault(key, {
                'customer_id': sale.customer_id, 'customer_name': _phase_five_customer_name(sale),
                'product_id': item.product_id, 'product_name': item.product_name,
                'internal_code': item.internal_code, 'category_name': item.category_name_snapshot,
                'quantity': Decimal('0.000'), 'net_revenue': Decimal('0.00'),
            })
            product['quantity'] += sign * item.quantity
            product['net_revenue'] += sign * item.net_subtotal
    customer_rows = []
    for row in customers.values():
        customer_rows.append({
            **{key: value for key, value in row.items() if key not in ('total_purchased', 'sale_ids')},
            'total_purchased': decimal_string(row['total_purchased']),
            'ticket_average': decimal_string(
                row['total_purchased'] / row['sales_count'] if row['sales_count'] else Decimal('0.00')
            ),
            'recurring': row['sales_count'] > 1,
        })
    product_rows = [{
        **{key: value for key, value in row.items() if key not in ('quantity', 'net_revenue')},
        'quantity': _human_quantity(row['quantity']), 'net_revenue': decimal_string(row['net_revenue']),
    } for row in products.values()]
    return (
        sorted(customer_rows, key=lambda row: (-Decimal(row['total_purchased']), row['customer_name'])),
        sorted(sales, key=lambda row: (row['event_at'], row['id']), reverse=True),
        sorted(product_rows, key=lambda row: (-Decimal(row['net_revenue']), row['customer_name'], row['product_name'])),
        sale_signs, anonymous_sales,
    )


class CustomersReportView(BaseReportView):
    required_permission = 'reports.view_sales'
    required_permissions_all = ('reports.view_sales', 'customers.view')
    query_serializer_class = CommercialComplementsReportQuerySerializer
    csv_filename = 'relatorio-clientes.csv'

    def serialize_rows(self, rows, request):
        return list(rows)

    def export_headers(self, request):
        headers = {
            'records': (
                'customer_name', 'customer_status', 'sales_count', 'ticket_average',
                'total_purchased', 'last_purchase_at', 'recurring',
            ),
            'sales': (
                'sale_number', 'customer_name', 'event_type', 'event_at', 'channel',
                'operator_name', 'total',
            ),
            'products': (
                'customer_name', 'product_name', 'internal_code', 'category_name',
                'quantity', 'net_revenue',
            ),
            'commands': ('command_number', 'table_name', 'customer_name', 'sale_number', 'closed_at', 'total'),
        }
        return headers[request.query_params.get('section', 'records')]

    def get(self, request):
        filters, start, end = self.parse_query(request)
        section = filters['section']
        if section not in ('records', 'sales', 'products', 'commands'):
            raise ValidationError({'section': 'Informe uma aba válida para este relatório.'})
        if section == 'commands' and not user_has_code(request, 'commands.view'):
            raise PermissionDenied('Você não possui permissão para consultar comandas relacionadas.')
        events = _phase_five_events(
            branch=request.branch_context, start=start, end=end, filters=filters,
        )
        customers, sales, products, sale_signs, anonymous_sales = _phase_five_customer_data(events, filters)
        if filters.get('search'):
            value = filters['search'].casefold()
            customers = [row for row in customers if value in row['customer_name'].casefold()]
            sales = [row for row in sales if value in row['customer_name'].casefold()]
            products = [row for row in products if value in row['customer_name'].casefold() or value in row['product_name'].casefold()]
        command_rows = []
        if section == 'commands':
            sale_ids = [sale_id for sale_id, sign in sale_signs.items() if sign]
            for command in Command.objects.select_related('sale', 'table', 'customer').filter(
                branch=request.branch_context, sale_id__in=sale_ids,
            ).order_by('-closed_at', '-id'):
                command_rows.append({
                    'id': command.pk, 'command_number': command.command_number,
                    'table_name': _command_table_name(command),
                    'customer_name': command.customer_name_snapshot or _phase_five_customer_name(command.sale),
                    'sale_id': command.sale_id, 'sale_number': command.sale.sale_number,
                    'closed_at': command.closed_at, 'total': decimal_string(command.sale.total),
                })
        summary = {
            'customer_count': len(customers),
            'recurring_count': sum(row['recurring'] for row in customers),
            'total_purchased': decimal_string(sum((Decimal(row['total_purchased']) for row in customers), Decimal('0.00'))),
            'ticket_average': decimal_string(
                sum((Decimal(row['total_purchased']) for row in customers), Decimal('0.00'))
                / sum((row['sales_count'] for row in customers), 0)
                if sum((row['sales_count'] for row in customers), 0) else Decimal('0.00')
            ),
            'anonymous_sales': anonymous_sales,
            'product_count': len({row['product_id'] for row in products}),
            'command_count': len(command_rows) if section == 'commands' else Command.objects.filter(
                branch=request.branch_context,
                sale_id__in=[sale_id for sale_id, sign in sale_signs.items() if sign],
            ).count(),
        }
        rows = {
            'records': customers, 'sales': sales, 'products': products, 'commands': command_rows,
        }[section]
        return self.respond(
            request, rows=rows, period=canonical_datetime_range(start, end), summary=summary,
        )
