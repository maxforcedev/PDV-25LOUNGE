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
from apps.cash.models import CashRegister, WithdrawalCategory
from apps.companies.selectors import branch_permission_codes
from apps.inventory.models import MovementType
from apps.products.models import Category, Product
from apps.sales.models import OperationType, PaymentMethod, SaleStatus
from apps.sales.serializers import readable_user_name

from .permissions import ReportsPermission
from .selectors import (
    commercial_summary,
    consumption_summary,
    current_cash_sessions,
    filtered_cash_sessions,
    filtered_inventory_movements,
    filtered_sales,
    filtered_withdrawals,
    inventory_kpis,
    payment_totals,
    sale_rankings,
    sale_rows,
    withdrawal_summary,
)
from .serializers import (
    CashReportQuerySerializer,
    CashSessionReportSerializer,
    ConsumptionsReportQuerySerializer,
    InventoryMovementReportSerializer,
    InventoryReportQuerySerializer,
    ReportSaleSerializer,
    SalesReportQuerySerializer,
    WithdrawalReportSerializer,
    WithdrawalsReportQuerySerializer,
)


def decimal_string(value, places=2):
    value = value if isinstance(value, Decimal) else Decimal(value or 0)
    return f'{value:.{places}f}'


def user_has_code(request, code):
    return request.user.is_superuser or code in branch_permission_codes(
        request.user, request.branch_context.pk
    )


def safe_csv_cell(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    value = str(value)
    if value.startswith(('=', '+', '-', '@')):
        value = "'" + value
    return value


def csv_response(filename, headers, rows):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(headers)
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
        products = Product.objects.filter(company_id=branch.company_id).order_by('name', 'id')
        categories = Category.objects.filter(company_id=branch.company_id).order_by(
            'sort_order', 'name', 'id'
        )
        payment_methods = PaymentMethod.objects.filter(
            company_id=branch.company_id
        ).order_by('name', 'id')
        registers = CashRegister.objects.filter(branch=branch).order_by('name', 'id')
        user_options = [
            {'id': user.pk, 'name': readable_user_name(user)} for user in users
        ]
        return Response({
            'operators': user_options,
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

        if user_has_code(request, 'sales.view'):
            sales = filtered_sales(
                branch=branch,
                start=start,
                end=end,
                operation_type=OperationType.SALE,
                filters={'status': SaleStatus.FINALIZED},
            )
            summary, _ = commercial_summary(sales)
            products, categories = sale_rankings(sales)
            response['sales'] = {
                'revenue': decimal_string(summary['revenue']),
                'count': summary['count'],
                'average': decimal_string(summary['average']),
                'manual_discount': decimal_string(summary['manual_discount']),
                'promotion_discount': decimal_string(summary['promotion_discount']),
                'total_discount': decimal_string(summary['total_discount']),
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
                'latest_sales': ReportSaleSerializer(
                    sale_rows(sales)[:10], many=True, context={'request': request}
                ).data,
            }

        if user_has_code(request, 'sales.view_consumption'):
            consumptions = filtered_sales(
                branch=branch,
                start=start,
                end=end,
                operation_type=OperationType.CONSUMPTION,
                filters={'status': SaleStatus.FINALIZED},
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
        return Response(response)


class SalesReportView(BaseReportView):
    required_permission = 'reports.view_sales'
    query_serializer_class = SalesReportQuerySerializer
    row_serializer_class = ReportSaleSerializer
    csv_filename = 'sales-report.csv'
    csv_headers = (
        'id', 'sale_number', 'status', 'operator', 'subtotal',
        'promotion_discount_total', 'discount', 'total', 'created_at', 'cancelled_at',
        'items', 'payments',
    )

    def get(self, request):
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
        result = {
            'revenue': decimal_string(summary['revenue']),
            'count': summary['count'],
            'average': decimal_string(summary['average']),
            'discount': decimal_string(summary['manual_discount']),
            'manual_discount': decimal_string(summary['manual_discount']),
            'promotion_discount': decimal_string(summary['promotion_discount']),
            'total_discount': decimal_string(summary['total_discount']),
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
        }
        return self.respond(
            request,
            rows=sale_rows(sales),
            period=canonical_datetime_range(start, end),
            summary=result,
        )


class ConsumptionsReportView(BaseReportView):
    required_permission = 'reports.view_consumptions'
    query_serializer_class = ConsumptionsReportQuerySerializer
    row_serializer_class = ReportSaleSerializer
    csv_filename = 'consumptions-report.csv'
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
    csv_filename = 'cash-report.csv'
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
    csv_filename = 'withdrawals-report.csv'
    csv_headers = (
        'id', 'created_at', 'amount', 'category', 'category_label', 'beneficiary',
        'operator', 'cash_register', 'reason',
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
    csv_filename = 'inventory-movements-report.csv'
    csv_headers = (
        'id', 'created_at', 'movement_type', 'product', 'previous_quantity', 'quantity',
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
