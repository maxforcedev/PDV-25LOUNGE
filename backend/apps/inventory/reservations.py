from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Q
from django.db.models import Sum
from django.utils import timezone

from apps.base.exceptions import DomainValidationError
from apps.products.models import FractionableProductConfig

from .models import (
    Stock, StockReservation, StockReservationRequirement, StockReservationStatus,
)


QUICK_SALE_CHECKOUT_SOURCE = 'QUICK_SALE_CHECKOUT'


class StockReservationConflict(DomainValidationError):
    def __init__(self, message='Estoque indisponível para reservar.'):
        self.message = message
        super().__init__(code='stock_reserved', message=message)
        self.status_code = 409


def reservation_ttl():
    return timedelta(seconds=getattr(settings, 'STOCK_RESERVATION_TTL_SECONDS', 900))


def _active_requirements(*, stock_ids=None, exclude_reservation=None):
    now = timezone.now()
    queryset = StockReservationRequirement.objects.filter(
        reservation__status=StockReservationStatus.ACTIVE,
    ).filter(
        Q(reservation__expires_at__isnull=True) | Q(reservation__expires_at__gt=now)
    )
    if stock_ids is not None:
        queryset = queryset.filter(stock_id__in=stock_ids)
    if exclude_reservation is not None:
        queryset = queryset.exclude(reservation_id=exclude_reservation.pk)
    return queryset


def reserved_totals(*, stock_ids, exclude_reservation=None):
    return {
        row['stock_id']: (row['quantity'] or Decimal('0'), row['content_quantity'] or Decimal('0'))
        for row in _active_requirements(
            stock_ids=stock_ids, exclude_reservation=exclude_reservation,
        ).values('stock_id').annotate(
            quantity=Sum('quantity'), content_quantity=Sum('content_quantity'),
        )
    }


def assert_stock_outflow_available(*, stock, final_quantity, final_content,
                                   reservation=None):
    reserved_quantity, reserved_content = reserved_totals(
        stock_ids=(stock.pk,), exclude_reservation=reservation,
    ).get(stock.pk, (Decimal('0'), Decimal('0')))
    if final_quantity < reserved_quantity:
        raise StockReservationConflict(
            f'Estoque reservado impede a saída de {stock.product.name}.'
        )
    if final_content is not None and final_content < reserved_content:
        raise StockReservationConflict(
            f'Conteúdo reservado impede a saída de {stock.product.name}.'
        )


def checkout_requirements(checkout):
    """Use the same requirement pipeline used by the sale finalization."""
    from apps.products.models import SalesChannel
    from apps.sales.services import prepare_sale_products

    raw_items = [item.snapshot['raw'] for item in checkout.items.order_by('id')]
    _snapshots, quantities, contents, _subtotal = prepare_sale_products(
        checkout.company, raw_items, branch=checkout.branch,
        channel=SalesChannel.COUNTER, lock=False,
    )
    return quantities, contents


def _lock_requirement_stocks(branch, quantities, contents):
    product_ids = sorted(quantities)
    stocks = {
        stock.product_id: stock
        for stock in Stock.objects.select_for_update(of=('self',)).select_related('product').filter(
            branch=branch, product_id__in=product_ids,
        ).order_by('product_id', 'pk')
    }
    missing = [product_id for product_id in product_ids if product_id not in stocks]
    if missing:
        raise StockReservationConflict('Estoque não materializado para um dos itens.')
    fractions = {
        config.product_id: config
        for config in FractionableProductConfig.objects.filter(
            product_id__in=product_ids, tracking_active=True,
        )
    }
    requirements = {}
    for product_id in product_ids:
        quantity = quantities[product_id]
        content = contents.get(product_id)
        if content is None and product_id in fractions:
            content = (quantity * fractions[product_id].package_content).quantize(
                Decimal('0.000000001')
            )
        requirements[stocks[product_id].pk] = (quantity, content)
    return stocks, requirements


def _expire_if_due(reservation):
    if (
        reservation.status == StockReservationStatus.ACTIVE
        and reservation.expires_at is not None
        and reservation.expires_at <= timezone.now()
    ):
        reservation.status = StockReservationStatus.EXPIRED
        reservation.save(update_fields=('status', 'updated_at'))
    return reservation


def acquire_checkout_reservation(checkout, *, renew=True):
    """Create or atomically replace the checkout's active commitment."""
    quantities, contents = checkout_requirements(checkout)
    reservation = StockReservation.objects.select_for_update().filter(
        branch=checkout.branch, source_type=QUICK_SALE_CHECKOUT_SOURCE,
        source_reference=str(checkout.pk),
    ).first()
    if reservation:
        reservation = _expire_if_due(reservation)
        if reservation.status in (StockReservationStatus.CONSUMED, StockReservationStatus.RELEASED):
            raise StockReservationConflict('A reserva do checkout não está mais disponível.')
    stocks, requirements = _lock_requirement_stocks(checkout.branch, quantities, contents)
    stocks_by_id = {stock.pk: stock for stock in stocks.values()}
    own = reservation if reservation and reservation.status == StockReservationStatus.ACTIVE else None
    totals = reserved_totals(stock_ids=requirements, exclude_reservation=own)
    for stock_id, (quantity, content) in requirements.items():
        stock = stocks_by_id[stock_id]
        reserved_quantity, reserved_content = totals.get(stock_id, (Decimal('0'), Decimal('0')))
        if stock.current_quantity - reserved_quantity < quantity:
            raise StockReservationConflict(f'Estoque insuficiente para {stock.product.name}.')
        if content is not None and (
            stock.current_content is None or stock.current_content - reserved_content < content
        ):
            raise StockReservationConflict(f'Conteúdo insuficiente para {stock.product.name}.')
    if reservation is None:
        reservation = StockReservation.objects.create(
            branch=checkout.branch, source_type=QUICK_SALE_CHECKOUT_SOURCE,
            source_reference=str(checkout.pk),
            expires_at=timezone.now() + reservation_ttl(),
        )
    else:
        StockReservationRequirement.objects.filter(reservation=reservation).delete()
        reservation.status = StockReservationStatus.ACTIVE
        reservation.expires_at = timezone.now() + reservation_ttl() if renew else None
        reservation.save(update_fields=('status', 'expires_at', 'updated_at'))
    StockReservationRequirement.objects.bulk_create([
        StockReservationRequirement(
            reservation=reservation, stock_id=stock_id, quantity=quantity,
            content_quantity=content,
        )
        for stock_id, (quantity, content) in requirements.items()
    ])
    return reservation


def validate_checkout_reservation(checkout, *, paid=False, renew_if_unpaid=False):
    reservation = StockReservation.objects.select_for_update().filter(
        branch=checkout.branch, source_type=QUICK_SALE_CHECKOUT_SOURCE,
        source_reference=str(checkout.pk),
    ).first()
    if not reservation:
        raise StockReservationConflict('A reserva do checkout não está ativa.')
    reservation = _expire_if_due(reservation)
    if reservation.status != StockReservationStatus.ACTIVE:
        if reservation.status == StockReservationStatus.EXPIRED and renew_if_unpaid:
            reservation = acquire_checkout_reservation(checkout)
        elif reservation.status == StockReservationStatus.EXPIRED:
            raise StockReservationConflict(
                'A reserva do checkout expirou e não pode ser renovada após pagamento. '
                'Estorne os pagamentos antes de tentar novamente.'
            )
        else:
            raise StockReservationConflict('A reserva do checkout não está ativa.')
    quantities, contents = checkout_requirements(checkout)
    stocks, expected = _lock_requirement_stocks(checkout.branch, quantities, contents)
    stocks_by_id = {stock.pk: stock for stock in stocks.values()}
    persisted = {
        row.stock_id: (row.quantity, row.content_quantity)
        for row in reservation.requirements.select_for_update().order_by('stock_id')
    }
    if persisted != expected:
        raise StockReservationConflict('Os itens do checkout não correspondem à reserva.')
    for stock_id, (quantity, content) in expected.items():
        stock = stocks_by_id[stock_id]
        assert_stock_outflow_available(
            stock=stock, final_quantity=stock.current_quantity - quantity,
            final_content=(stock.current_content - content) if content is not None else None,
            reservation=reservation,
        )
    if paid and reservation.expires_at is not None:
        reservation.expires_at = None
        reservation.save(update_fields=('expires_at', 'updated_at'))
    return reservation


def release_checkout_reservation(checkout):
    reservation = StockReservation.objects.select_for_update().filter(
        branch=checkout.branch, source_type=QUICK_SALE_CHECKOUT_SOURCE,
        source_reference=str(checkout.pk),
    ).first()
    if reservation and reservation.status == StockReservationStatus.ACTIVE:
        reservation.status = StockReservationStatus.RELEASED
        reservation.save(update_fields=('status', 'updated_at'))
    return reservation


def restore_checkout_reservation_expiry(checkout):
    reservation = StockReservation.objects.select_for_update().filter(
        branch=checkout.branch, source_type=QUICK_SALE_CHECKOUT_SOURCE,
        source_reference=str(checkout.pk), status=StockReservationStatus.ACTIVE,
    ).first()
    if reservation and reservation.expires_at is None:
        reservation.expires_at = timezone.now() + reservation_ttl()
        reservation.save(update_fields=('expires_at', 'updated_at'))
    return reservation


def consume_checkout_reservation(reservation):
    if reservation.status != StockReservationStatus.ACTIVE:
        raise StockReservationConflict('A reserva do checkout não está ativa.')
    reservation.status = StockReservationStatus.CONSUMED
    reservation.expires_at = None
    reservation.save(update_fields=('status', 'expires_at', 'updated_at'))
    return reservation
