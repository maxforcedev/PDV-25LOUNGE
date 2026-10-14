from decimal import Decimal
from datetime import datetime
from urllib.parse import urlencode

from django.utils import timezone

from apps.attendance.models import AttendanceCommand, AttendanceCommandStatus, AttendancePaymentStatus
from apps.attendance.services import command_financial_status
from apps.companies.features import branch_feature_enabled
from apps.companies.selectors import user_has_branch_permission
from apps.inventory.models import Stock
from apps.products.selectors import inventory_products
from apps.production.models import PrintJob, PrintJobStatus

from .selectors import receipt_summary


SEVERITY_ORDER = {'critical': 0, 'attention': 1, 'informational': 2}
VALID_CATEGORIES = {'inventory', 'financial', 'commands', 'printing'}
VALID_SEVERITIES = set(SEVERITY_ORDER)


def _can(user, branch, code):
    return user.is_superuser or user_has_branch_permission(user, branch.pk, code)


def _alert(*, branch, identity, category, title, description, severity, reference,
           occurred_at, entity, recommended_action, route=None):
    return {
        'identity': identity,
        'category': category,
        'title': title,
        'description': description,
        'severity': severity,
        'state': 'active',
        'reference': reference,
        'occurred_at': timezone.localtime(occurred_at).isoformat() if occurred_at else None,
        'entity': entity,
        'context': {
            'company_id': branch.company_id,
            'company_name': branch.company.trade_name,
            'branch_id': branch.pk,
            'branch_name': branch.name,
        },
        'recommended_action': recommended_action,
        # The API only emits a route after applying the same existing permission
        # that protects the destination. The destination remains authoritative.
        'route': route,
    }


def inventory_attention(branch):
    stocks = Stock.objects.select_related('product', 'product__fraction_config').filter(
        branch=branch,
        product_id__in=inventory_products(branch).values('pk'),
    ).order_by('product__name', 'pk')
    alerts = []
    for stock in stocks:
        quantity = stock.equivalent_quantity()
        if quantity < 0:
            condition, severity, title, description, route = (
                'negative', 'critical',
                f'Estoque negativo: {stock.product.name}',
                f'O saldo atual e {quantity}. Revise as movimentacoes antes de continuar a operacao.',
                '/estoque?state=negative',
            )
        elif quantity == 0:
            condition, severity, title, description, route = (
                'zero', 'attention',
                f'Estoque zerado: {stock.product.name}',
                'O produto nao possui saldo disponivel nesta filial.',
                '/estoque?state=zero',
            )
        elif quantity < stock.minimum_quantity:
            condition, severity, title, description, route = (
                'below_minimum', 'attention',
                f'Estoque abaixo do minimo: {stock.product.name}',
                f'Saldo atual {quantity}; minimo configurado {stock.minimum_quantity}.',
                '/estoque?state=below_minimum',
            )
        else:
            continue
        alerts.append(_alert(
            branch=branch, identity=f'inventory:{condition}:{stock.pk}', category='inventory',
            title=title, description=description, severity=severity, reference='current',
            occurred_at=stock.updated_at,
            entity={
                'type': 'stock', 'id': stock.pk, 'name': stock.product.name,
                'branch_id': branch.pk,
            },
            recommended_action='Revise o saldo e registre a reposicao ou regularizacao cabivel.',
            route=route,
        ))
    return alerts


def command_attention(branch):
    commands = AttendanceCommand.objects.filter(
        branch=branch,
        status=AttendanceCommandStatus.OPEN,
        payments__status=AttendancePaymentStatus.APPLIED,
    ).distinct().order_by('-created_at', '-id')
    alerts = []
    for command in commands:
        status = command_financial_status(command)
        if status['state'] != 'REGULARIZATION_REQUIRED':
            continue
        label = command.identifier or command.number
        alerts.append(_alert(
            branch=branch, identity=f'commands:financial_regularization:{command.pk}', category='commands',
            title=f'Regularizacao financeira pendente: {label}',
            description=status['message'], severity='attention', reference='current',
            occurred_at=command.created_at,
            entity={
                'type': 'attendance_command', 'id': command.pk, 'name': label,
                'branch_id': branch.pk,
            },
            recommended_action='Consulte as evidencias historicas e regularize somente os dados comprovados.',
            route='/comandas/regularizacoes-financeiras/',
        ))
    return alerts


def printing_attention(branch):
    jobs = PrintJob.objects.select_related('printer_device').filter(
        branch=branch, status=PrintJobStatus.FAILED,
    ).order_by('-updated_at', '-id')
    alerts = []
    for job in jobs:
        retryable = job.physical_dispatch_started_at is None
        alerts.append(_alert(
            branch=branch, identity=f'printing:failed:{job.pk}', category='printing',
            title=f'Falha de impressao: {job.printer_device.name}',
            description=job.last_error or 'O trabalho de impressao falhou e exige conferência.',
            severity='attention', reference='current', occurred_at=job.updated_at,
            entity={
                'type': 'print_job', 'id': job.pk,
                'name': f'Impressao #{job.pk}', 'branch_id': branch.pk,
            },
            recommended_action=(
                'Revise a falha e tente novamente antes do envio físico.' if retryable
                else 'Revise a falha e solicite uma reimpressao explícita se necessário.'
            ),
            route='/producao/falhas',
        ))
    return alerts


def financial_attention(branch, start, end, *, include_consumptions=False):
    operation_types = None if include_consumptions else ('sale',)
    receipts = receipt_summary(
        branch=branch, start=start, end=end, filters={}, operation_types=operation_types,
    )
    delta = receipts['reconciliation_delta']
    if delta == Decimal('0.00'):
        return []
    return [_alert(
        branch=branch, identity=f'financial:reconciliation:{start.isoformat()}:{end.isoformat()}',
        category='financial', title='Divergencia de conciliacao de recebimentos',
        description=f'Diferenca de {abs(delta):.2f} entre pagamentos e o total operacional do periodo.',
        severity='critical', reference='period', occurred_at=end,
        entity={'type': 'receipt_reconciliation', 'id': None, 'name': 'Recebimentos do periodo', 'branch_id': branch.pk},
        recommended_action='Revise os pagamentos e estornos registrados no periodo selecionado.',
        route='/relatorios/recebimentos?' + urlencode({
            'start_datetime': start.isoformat(), 'end_datetime': end.isoformat(),
        }),
    )]


def active_attention(*, branch, user, start, end, categories=None, severities=None):
    """Evaluate current operational conditions; no derived alert is persisted."""
    categories = set(categories or VALID_CATEGORIES) & VALID_CATEGORIES
    severities = set(severities or VALID_SEVERITIES) & VALID_SEVERITIES
    alerts = []
    if (
        'inventory' in categories
        and branch_feature_enabled(branch, 'inventory')
        and _can(user, branch, 'inventory.view')
        and _can(user, branch, 'inventory.view_stock_kpis')
    ):
        alerts.extend(inventory_attention(branch))
    if (
        'financial' in categories
        and branch_feature_enabled(branch, 'financial')
        and _can(user, branch, 'reports.view_receipts')
    ):
        alerts.extend(financial_attention(
            branch, start, end,
            include_consumptions=_can(user, branch, 'sales.view_consumption'),
        ))
    if (
        'commands' in categories
        and branch_feature_enabled(branch, 'commands')
        and _can(user, branch, 'commands.view')
    ):
        alerts.extend(command_attention(branch))
    if (
        'printing' in categories
        and branch_feature_enabled(branch, 'production')
        and _can(user, branch, 'print_jobs.view')
    ):
        alerts.extend(printing_attention(branch))
    alerts = [alert for alert in alerts if alert['severity'] in severities]
    # Every source has a stable identity. Keep it as a last tie-breaker so a
    # refresh cannot move equal alerts between pages.
    unique_alerts = {alert['identity']: alert for alert in alerts}
    return sorted(unique_alerts.values(), key=lambda alert: (
        SEVERITY_ORDER[alert['severity']],
        -(datetime.fromisoformat(alert['occurred_at']).timestamp()
          if alert['occurred_at'] else 0),
        alert['identity'],
    ))


def attention_summary(alerts):
    by_severity = {severity: 0 for severity in SEVERITY_ORDER}
    by_category = {category: 0 for category in sorted(VALID_CATEGORIES)}
    for alert in alerts:
        by_severity[alert['severity']] += 1
        by_category[alert['category']] += 1
    return {
        'active_count': len(alerts),
        'by_severity': by_severity,
        'by_category': by_category,
    }


def dashboard_attention_summary(*, branch, user, inventory=None, reconciliation_delta=None):
    """Summarize facts already calculated by DashboardView without rerunning them."""
    alerts = []
    if (
        branch_feature_enabled(branch, 'inventory')
        and _can(user, branch, 'inventory.view')
        and _can(user, branch, 'inventory.view_stock_kpis')
    ):
        for condition, severity, key in (
            ('negative', 'critical', 'negative_count'),
            ('zero', 'attention', 'zero_count'),
            ('below_minimum', 'attention', 'below_minimum_count'),
        ):
            for index in range(int((inventory or {}).get(key, 0))):
                alerts.append({
                    'identity': f'inventory:{condition}:dashboard:{index}',
                    'category': 'inventory', 'severity': severity,
                })
    if (
        branch_feature_enabled(branch, 'financial')
        and _can(user, branch, 'reports.view_receipts')
        and reconciliation_delta is not None
        and reconciliation_delta != Decimal('0.00')
    ):
        alerts.append({
            'identity': 'financial:reconciliation:dashboard',
            'category': 'financial', 'severity': 'critical',
        })
    if branch_feature_enabled(branch, 'commands') and _can(user, branch, 'commands.view'):
        alerts.extend({
            'identity': f'commands:financial_regularization:{alert["entity"]["id"]}',
            'category': 'commands', 'severity': 'attention',
        } for alert in command_attention(branch))
    if branch_feature_enabled(branch, 'production') and _can(user, branch, 'print_jobs.view'):
        alerts.extend({
            'identity': f'printing:failed:{alert["entity"]["id"]}',
            'category': 'printing', 'severity': 'attention',
        } for alert in printing_attention(branch))
    return attention_summary(alerts)


def available_attention_categories(*, branch, user):
    categories = []
    if (
        branch_feature_enabled(branch, 'inventory')
        and _can(user, branch, 'inventory.view')
        and _can(user, branch, 'inventory.view_stock_kpis')
    ):
        categories.append('inventory')
    if (
        branch_feature_enabled(branch, 'financial')
        and _can(user, branch, 'reports.view_receipts')
    ):
        categories.append('financial')
    if branch_feature_enabled(branch, 'commands') and _can(user, branch, 'commands.view'):
        categories.append('commands')
    if branch_feature_enabled(branch, 'production') and _can(user, branch, 'print_jobs.view'):
        categories.append('printing')
    return categories
