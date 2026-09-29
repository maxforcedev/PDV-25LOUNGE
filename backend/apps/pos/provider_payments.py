"""Operational provider-payment helpers for the POS Quick Sale endpoints."""

from decimal import Decimal, InvalidOperation

from apps.companies.models import Status
from apps.payment_integrations.models import (
    PaymentProvider, PaymentProviderConnection, PaymentProviderIntegrationType,
    PaymentTerminal,
)
from apps.payment_integrations.services import PaymentIntegrationConflict


CIELO_CALLBACK_URL = 'corepdv://cielo-payment-response'
_CIELO_PAYMENT_METHODS = {
    'credit_card', 'debit_card', 'pix', 'food_voucher', 'meal_voucher',
}


def resolve_provider_resources(*, checkout, provider_code):
    """Choose exactly one active connection and POS-bound terminal for a checkout."""
    provider = PaymentProvider.objects.filter(
        code=provider_code, status=Status.ACTIVE,
        integration_type=PaymentProviderIntegrationType.LOCAL_DEEP_LINK,
    ).first()
    if not provider:
        raise PaymentIntegrationConflict(
            'payment_provider_unavailable', 'O provedor de pagamento não está disponível.',
        )
    connections = PaymentProviderConnection.objects.filter(
        company=checkout.company, provider=provider, status=Status.ACTIVE,
    )
    branch_connections = list(connections.filter(branch=checkout.branch).order_by('id'))
    company_connections = list(connections.filter(branch__isnull=True).order_by('id'))
    candidates = branch_connections or company_connections
    if len(candidates) != 1:
        code = (
            'payment_provider_connection_ambiguous'
            if len(candidates) > 1 else 'payment_provider_connection_unavailable'
        )
        raise PaymentIntegrationConflict(code, 'A conexão de pagamento não está disponível de forma única.')
    connection = candidates[0]
    terminals = list(PaymentTerminal.objects.filter(
        connection=connection, branch=checkout.branch, pos_device=checkout.pos_device,
        status=Status.ACTIVE,
    ).order_by('id'))
    if len(terminals) != 1:
        raise PaymentIntegrationConflict(
            'payment_provider_terminal_unavailable',
            'Não há terminal de pagamento ativo vinculado a este POS.',
        )
    return connection, terminals[0]


def cielo_capture_available(*, checkout):
    try:
        resolve_provider_resources(checkout=checkout, provider_code='cielo')
    except PaymentIntegrationConflict:
        return False
    return True


def cielo_supports_payment_method(code):
    return code in _CIELO_PAYMENT_METHODS


def cielo_items_from_quick_checkout(checkout):
    """Build Cielo items solely from immutable checkout snapshots."""
    rows = []
    for item in checkout.items.all().order_by('id'):
        snapshot = item.snapshot.get('preview') if isinstance(item.snapshot, dict) else None
        if not isinstance(snapshot, dict):
            raise PaymentIntegrationConflict('cielo_items_invalid', 'O snapshot de um item do checkout é inválido.')
        try:
            quantity = Decimal(str(snapshot['quantity']))
            unit_price = Decimal(str(snapshot['unit_price']))
            cents = unit_price * 100
        except (InvalidOperation, KeyError, TypeError, ValueError) as error:
            raise PaymentIntegrationConflict('cielo_items_invalid', 'O snapshot de um item do checkout é inválido.') from error
        name = str(snapshot.get('product_name') or '').strip()
        sku = str(snapshot.get('internal_code') or f'produto-{item.product_id}').strip()
        unit = str(snapshot.get('unit') or '').strip()
        if (
            not name or not sku or not unit or quantity <= 0 or unit_price <= 0
            or cents != cents.to_integral_value()
        ):
            raise PaymentIntegrationConflict('cielo_items_invalid', 'Um item do checkout não pode ser convertido para a Cielo.')
        rows.append({
            'name': name,
            'quantity': str(quantity),
            'sku': sku,
            'unitOfMeasure': unit,
            'unitPrice': int(cents),
        })
    if not rows:
        raise PaymentIntegrationConflict('cielo_items_invalid', 'A Cielo exige itens persistidos no checkout.')
    return rows
