from calendar import monthrange
from datetime import datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.db.models import IntegerField
from django.db.models.functions import Cast, Substr
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.base.audit import audit_log, model_snapshot
from apps.base.exceptions import DomainValidationError
from apps.companies.models import Branch, Company, Status
from apps.companies.selectors import user_has_branch_permission
from apps.inventory.services import purchase_receipt_entry
from apps.products.models import (
    FractionableProductConfig, InventoryBehavior, Product, Unit,
)
from apps.suppliers.models import (
    ProductPurchasePresentation, ProductSupplier, ProductSupplierUnit, Supplier,
)

from .models import (
    PayableInstallment,
    PayableInstallmentStatus,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderStatus,
    PurchaseOrderType,
    PurchaseReceipt,
    PurchaseReceiptItem,
)


CENT = Decimal('0.01')
SIX_PLACES = Decimal('0.000001')
COST_PLACES = Decimal('0.000000000001')
MAX_MONEY = Decimal('99999999999999.99')


def _pk(value):
    return value.pk if hasattr(value, 'pk') else value


def strict_decimal(value, field, *, places, positive=False, nonnegative=False):
    if isinstance(value, (float, bool)) or value in ('', None):
        raise ValidationError({field: 'Informe um decimal exato como texto ou inteiro.'})
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValidationError({field: 'Informe um decimal valido.'}) from error
    if not result.is_finite() or result.as_tuple().exponent < -places:
        raise ValidationError({field: f'Use no maximo {places} casas decimais.'})
    if positive and result <= 0:
        raise ValidationError({field: 'O valor deve ser maior que zero.'})
    if nonnegative and result < 0:
        raise ValidationError({field: 'O valor nao pode ser negativo.'})
    quantizer = Decimal(1).scaleb(-places)
    return result.quantize(quantizer)


def _money(value, field, *, nonnegative=True):
    result = strict_decimal(value, field, places=2, nonnegative=nonnegative)
    if result > MAX_MONEY:
        raise ValidationError({field: 'O valor excede o limite permitido.'})
    return result


def _authorized_branch(branch, user, permission_code, *, lock=False, support_session=None):
    queryset = Branch.objects.select_related('company')
    if lock:
        queryset = queryset.select_for_update()
    try:
        branch = queryset.get(pk=_pk(branch))
    except (Branch.DoesNotExist, TypeError, ValueError) as error:
        raise PermissionDenied('Filial fora do contexto autorizado.') from error
    support_authorized = False
    if support_session is not None:
        expected_user_id = support_session.impersonated_user_id or support_session.actor_id
        support_authorized = bool(
            expected_user_id == user.pk
            and support_session.company_id == branch.company_id
            and support_session.mode == 'READ_WRITE'
            and support_session.ended_at is None
            and support_session.expires_at > timezone.now()
        )
    if not support_authorized:
        if not user.is_superuser and not user_has_branch_permission(
            user, branch.pk, permission_code
        ):
            raise PermissionDenied('Filial fora do contexto autorizado.')
    if branch.status != Status.ACTIVE or branch.company.status != Status.ACTIVE:
        raise ValidationError({'branch': 'A filial e a empresa devem estar ativas.'})
    return branch


def _next_order_number(company):
    latest = PurchaseOrder.objects.filter(
        company=company, order_number__regex=r'^C[0-9]+$'
    ).annotate(
        sequence=Cast(Substr('order_number', 2), IntegerField())
    ).aggregate(value=Max('sequence'))['value']
    return f'C{(latest or 0) + 1:06d}'


def _validate_product_supplier(unit, *, company, supplier, allow_exclusive=False):
    relation = unit.product_supplier
    product = relation.product
    errors = {}
    if unit.status != Status.ACTIVE:
        errors['product_supplier_unit'] = 'A apresentacao de compra deve estar ativa.'
    if relation.status != Status.ACTIVE:
        errors['product_supplier'] = 'A relacao com o fornecedor deve estar ativa.'
    if supplier.status != Status.ACTIVE:
        errors['supplier'] = 'O fornecedor deve estar ativo.'
    if unit.company_id != company.pk or relation.company_id != company.pk:
        errors['product_supplier_unit'] = 'A apresentacao deve pertencer a empresa da compra.'
    if relation.supplier_id != supplier.pk:
        errors['product_supplier_unit'] = 'A apresentacao nao pertence ao fornecedor da compra.'
    if product.company_id != company.pk:
        errors['product'] = 'O produto deve pertencer a empresa da compra.'
    if product.status != Status.ACTIVE:
        errors['product'] = 'O produto deve estar ativo.'
    if product.inventory_behavior != InventoryBehavior.DIRECT:
        errors['product'] = 'Somente produtos com estoque proprio podem ser comprados.'
    exclusive = ProductSupplier.objects.filter(
        product=product, status=Status.ACTIVE, is_exclusive=True
    ).first()
    if exclusive and exclusive.supplier_id != supplier.pk and not allow_exclusive:
        errors['exclusive_supplier_warning'] = _exclusive_supplier_message(
            product, exclusive.supplier, supplier
        )
    if errors:
        raise ValidationError(errors)
    return relation, product


def _exclusive_supplier_message(product, exclusive_supplier, selected_supplier):
    return (
        f'O produto {product.name} possui o fornecedor '
        f'{exclusive_supplier.trade_name} configurado como fornecedor exclusivo. '
        f'Você está realizando esta compra com {selected_supplier.trade_name}.'
    )


def _exclusive_supplier_override_details(items, supplier):
    details = []
    seen_products = set()
    for item in items:
        product = item.product
        if product.pk in seen_products:
            continue
        seen_products.add(product.pk)
        exclusive = ProductSupplier.objects.filter(
            product=product, status=Status.ACTIVE, is_exclusive=True,
        ).select_related('supplier').first()
        if exclusive and exclusive.supplier_id != supplier.pk:
            details.append({
                'product_id': product.pk,
                'product_name': product.name,
                'exclusive_supplier_id': exclusive.supplier_id,
                'exclusive_supplier_name': exclusive.supplier.trade_name,
                'selected_supplier_id': supplier.pk,
                'selected_supplier_name': supplier.trade_name,
                'override_confirmed': True,
            })
    return details


def _validate_purchase_item(item, *, company, supplier, allow_exclusive=False):
    if item.product_supplier_unit_id:
        return _validate_product_supplier(
            item.product_supplier_unit, company=company, supplier=supplier, allow_exclusive=allow_exclusive,
        )
    product = item.product
    errors = {}
    if product.company_id != company.pk:
        errors['product'] = 'O produto deve pertencer a empresa da compra.'
    if product.status != Status.ACTIVE:
        errors['product'] = 'O produto deve estar ativo.'
    if product.inventory_behavior != InventoryBehavior.DIRECT:
        errors['product'] = 'Somente produtos com estoque proprio podem ser comprados.'
    exclusive = ProductSupplier.objects.filter(
        product=product, status=Status.ACTIVE, is_exclusive=True
    ).first()
    if exclusive and exclusive.supplier_id != supplier.pk and not allow_exclusive:
        errors['exclusive_supplier_warning'] = _exclusive_supplier_message(
            product, exclusive.supplier, supplier
        )
    if errors:
        raise ValidationError(errors)
    return None, product


def _create_items(order, raw_items, *, allow_exclusive=False):
    if not isinstance(raw_items, list) or not raw_items:
        raise ValidationError({'items': 'Informe ao menos um item.'})
    unit_ids = []
    product_ids = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise ValidationError({'items': f'Item {index + 1}: formato inválido.'})
        unit_id = raw.get('product_supplier_unit')
        product_id = raw.get('product')
        if unit_id in (None, ''):
            if product_id in (None, ''):
                raise ValidationError({
                    'items': f'Item {index + 1}: informe o produto ou a apresentação do fornecedor.'
                })
            product_ids.append(int(product_id))
        else:
            unit_ids.append(int(unit_id))
    if len(unit_ids) != len(set(unit_ids)):
        raise ValidationError({'items': 'Não repita a mesma apresentação na compra.'})
    if len(product_ids) != len(set(product_ids)):
        raise ValidationError({'items': 'Não repita o mesmo produto na compra.'})

    units = {
        unit.pk: unit
        for unit in ProductSupplierUnit.objects.select_for_update(of=('self',)).select_related(
            'product_supplier__product', 'product_supplier__supplier', 'purchase_presentation'
        ).filter(pk__in=unit_ids).order_by('pk')
    } if unit_ids else {}
    if len(units) != len(unit_ids):
        raise ValidationError({'items': 'Uma apresentação informada é inválida.'})

    direct_products = {
        p.pk: p
        for p in Product.objects.select_for_update().filter(
            pk__in=product_ids, company_id=order.company_id
        )
    } if product_ids else {}
    if len(direct_products) != len(product_ids):
        raise ValidationError({'items': 'Um produto informado é inválido ou não pertence à empresa.'})

    created = []
    for index, raw in enumerate(raw_items, start=1):
        unit_id = raw.get('product_supplier_unit')
        if unit_id not in (None, ''):
            unit = units[int(unit_id)]
            relation, product = _validate_product_supplier(
                unit, company=order.company, supplier=order.supplier, allow_exclusive=allow_exclusive
            )
            supplied_product = raw.get('product')
            if supplied_product not in (None, '') and int(_pk(supplied_product)) != product.pk:
                raise ValidationError({'items': f'Item {index}: produto e apresentação divergem.'})
            presentation = unit.purchase_presentation
            if presentation is None:
                # Legacy supplier units are normalized before their first purchase snapshot.
                presentation, _created = ProductPurchasePresentation.objects.get_or_create(
                    company=order.company,
                    product=product,
                    unit_code=unit.unit_code,
                    conversion_factor=unit.conversion_factor,
                    defaults={'description': unit.description},
                )
                unit.purchase_presentation = presentation
                unit.save(update_fields=('purchase_presentation', 'updated_at'))
            if presentation.status != Status.ACTIVE:
                raise ValidationError({
                    'items': f'Item {index}: a apresentação do produto está inativa.'
                })
            conversion_factor = presentation.conversion_factor
            presentation_unit_code = presentation.unit_code
            presentation_description = presentation.description
            supplier_code = relation.supplier_code
            product_supplier = relation
            product_supplier_unit = unit
        else:
            product = direct_products[int(raw['product'])]
            temporary = type('PurchaseItemValidation', (), {
                'product_supplier_unit_id': None, 'product': product,
            })()
            _validate_purchase_item(temporary, company=order.company, supplier=order.supplier, allow_exclusive=allow_exclusive)
            relation = None
            conversion_factor = Decimal('1')
            presentation_unit_code = product.unit
            presentation_description = 'Unidade de estoque'
            supplier_code = ''
            product_supplier = None
            product_supplier_unit = None
        quantity = strict_decimal(
            raw.get('ordered_quantity', raw.get('quantity')),
            f'items.{index - 1}.ordered_quantity',
            places=6,
            positive=True,
        )
        price = strict_decimal(
            raw.get('purchase_unit_price', raw.get('unit_price')),
            f'items.{index - 1}.purchase_unit_price',
            places=6,
            nonnegative=True,
        )
        stock_quantity = quantity * conversion_factor
        if (
            product.unit == Unit.UNIT
            and stock_quantity != stock_quantity.to_integral_value()
        ):
            raise ValidationError({
                'items': f'Item {index}: produto UN deve ser comprado em embalagens inteiras.'
            })
        if stock_quantity.quantize(Decimal('0.001')) != stock_quantity:
            raise ValidationError({
                'items': (
                    f'Item {index}: a conversão para estoque deve resultar em no máximo '
                    'três casas decimais nesta versão.'
                )
            })
        gross = (quantity * price).quantize(CENT, rounding=ROUND_HALF_UP)
        item = PurchaseOrderItem.objects.create(
            purchase_order=order,
            product=product,
            product_supplier=product_supplier,
            product_supplier_unit=product_supplier_unit,
            line_number=index,
            ordered_quantity=quantity,
            product_name=product.name,
            product_internal_code=product.internal_code,
            product_stock_unit=product.unit,
            supplier_name=order.supplier.trade_name,
            supplier_tax_id=order.supplier.tax_id or '',
            supplier_product_code=supplier_code,
            presentation_unit_code=presentation_unit_code,
            presentation_description=presentation_description,
            conversion_factor=conversion_factor,
            purchase_unit_price=price,
            gross_subtotal=gross,
            allocated_discount=Decimal('0.00'),
            allocated_freight=Decimal('0.00'),
            allocated_other_expenses=Decimal('0.00'),
            effective_total=gross,
            effective_stock_unit_cost=(
                gross / stock_quantity
            ).quantize(COST_PLACES, rounding=ROUND_HALF_UP),
        )
        created.append(item)
    return created


def _proportional_allocation(items, total):
    if total == 0:
        return {item.pk: Decimal('0.00') for item in items}
    gross_total = sum((item.gross_subtotal for item in items), Decimal('0.00'))
    if gross_total == 0:
        raise ValidationError({'items': 'Nao e possivel ratear valores em itens sem valor bruto.'})
    allocated = {
        item.pk: (total * item.gross_subtotal / gross_total).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        for item in items
    }
    residual = total - sum(allocated.values(), Decimal('0.00'))
    target = min(items, key=lambda item: (-item.gross_subtotal, item.pk))
    allocated[target.pk] += residual
    if any(value < 0 for value in allocated.values()):
        raise ValidationError({'items': 'O rateio gerou valor invalido.'})
    return allocated


def _allocate_order(order, items):
    gross_total = sum((item.gross_subtotal for item in items), Decimal('0.00'))
    if order.global_discount > gross_total:
        raise ValidationError({'global_discount': 'O desconto nao pode exceder o valor bruto.'})
    discounts = _proportional_allocation(items, order.global_discount)
    freight = _proportional_allocation(items, order.freight_total)
    others = _proportional_allocation(items, order.other_expenses_total)
    for item in items:
        item.allocated_discount = discounts[item.pk]
        item.allocated_freight = freight[item.pk]
        item.allocated_other_expenses = others[item.pk]
        item.effective_total = (
            item.gross_subtotal - item.allocated_discount
            + item.allocated_freight + item.allocated_other_expenses
        )
        item.effective_stock_unit_cost = (
            item.effective_total / item.ordered_stock_quantity
        ).quantize(COST_PLACES, rounding=ROUND_HALF_UP)
        item.save(update_fields=(
            'allocated_discount', 'allocated_freight', 'allocated_other_expenses',
            'effective_total', 'effective_stock_unit_cost', 'updated_at',
        ))
    order.gross_total = gross_total
    order.payable_total = (
        gross_total - order.global_discount + order.freight_total
        + order.other_expenses_total
    )
    order.save(update_fields=(
        'gross_total', 'global_discount', 'freight_total',
        'other_expenses_total', 'payable_total', 'updated_at',
    ))


def _order_snapshot(order):
    snapshot = model_snapshot(order, (
        'order_number', 'order_type', 'status', 'company_id', 'branch_id',
        'supplier_id', 'gross_total', 'global_discount', 'freight_total',
        'other_expenses_total', 'payable_total', 'document_number', 'document_key',
        'document_series', 'document_date', 'attachment', 'notes',
        'placed_at', 'placed_by_id', 'closed_at', 'closed_by_id', 'closure_reason',
    ))
    snapshot['items'] = [
        model_snapshot(item, (
            'line_number', 'product_id', 'product_supplier_id',
            'product_supplier_unit_id', 'ordered_quantity', 'product_name',
            'supplier_name', 'presentation_description', 'conversion_factor',
            'purchase_unit_price', 'gross_subtotal', 'allocated_discount',
            'allocated_freight', 'allocated_other_expenses', 'effective_total',
            'effective_stock_unit_cost',
        ))
        for item in order.items.all()
    ]
    return snapshot


def _assert_installment_reconciliation(order):
    aggregate = order.installments.aggregate(total=Sum('amount'), count=Max('installment_number'))
    if aggregate['count'] is not None and (aggregate['total'] or Decimal('0.00')) != order.payable_total:
        raise ValidationError({
            'installments': f'A soma das parcelas deve ser {order.payable_total:.2f}.'
        })


def _installment_snapshot(installment):
    return model_snapshot(installment, (
        'purchase_order_id', 'supplier_id', 'installment_number', 'amount',
        'due_date', 'status', 'paid_at', 'paid_by_id', 'cancelled_at',
        'cancelled_by_id', 'cancellation_reason', 'notes',
    ))


def _audit_installment(*, installment, user, action, summary, before=None):
    order = installment.purchase_order
    audit_log(
        actor=user,
        action=action,
        obj=installment,
        company=order.company,
        branch=order.branch,
        before=before or {},
        after=_installment_snapshot(installment),
        metadata={'summary': summary},
    )


def _create_installments(order, installments, *, user):
    if installments in (None, []):
        return []
    if not isinstance(installments, list):
        raise ValidationError({'installments': 'Informe uma lista de parcelas.'})
    prepared = []
    total = Decimal('0.00')
    for index, raw in enumerate(installments, start=1):
        if not isinstance(raw, dict):
            raise ValidationError({'installments': f'Parcela {index} invalida.'})
        amount = _money(raw.get('amount'), f'installments.{index - 1}.amount')
        if amount <= 0:
            raise ValidationError({'installments': f'Parcela {index}: o valor deve ser positivo.'})
        if not raw.get('due_date'):
            raise ValidationError({'installments': f'Parcela {index}: informe o vencimento.'})
        total += amount
        prepared.append((amount, raw['due_date'], (raw.get('notes') or '').strip()))
    if total != order.payable_total:
        raise ValidationError({
            'installments': f'A soma das parcelas deve ser {order.payable_total:.2f}.'
        })
    due_dates = [due_date for _amount, due_date, _notes in prepared]
    if len(due_dates) != len(set(due_dates)):
        raise ValidationError({'installments': 'Não repita vencimentos na mesma compra.'})
    existing = list(order.installments.select_for_update().order_by('installment_number'))
    if existing and len(existing) != len(prepared):
        raise ValidationError({'installments': 'A edição deve manter o número de parcelas já configurado.'})
    if any(item.status != PayableInstallmentStatus.PENDING for item in existing):
        raise ValidationError({'installments': 'Parcelas pagas ou canceladas não podem ser editadas.'})
    created = []
    for index, (amount, due_date, notes) in enumerate(prepared, start=1):
        if existing:
            installment = existing[index - 1]
            installment.amount = amount
            installment.due_date = due_date
            installment.notes = notes
            installment.save(update_fields=('amount', 'due_date', 'notes', 'updated_at'))
        else:
            installment = PayableInstallment.objects.create(
                purchase_order=order, supplier=order.supplier,
                installment_number=index, amount=amount, due_date=due_date, notes=notes,
            )
        created.append(installment)
    for installment in created:
        _audit_installment(
            installment=installment,
            user=user,
            action='purchase.payable.update' if existing else 'purchase.payable.create',
            summary=(
                f'Parcela {installment.installment_number} de '
                f'{order.order_number} criada.'
            ),
        )
    return created


def _next_month(date_value, months):
    month = date_value.month - 1 + months
    year = date_value.year + month // 12
    month = month % 12 + 1
    return date_value.replace(year=year, month=month, day=min(date_value.day, monthrange(year, month)[1]))


def _automatic_installments(order, count, first_due_date):
    cents = int((order.payable_total * 100).to_integral_value())
    base, remainder = divmod(cents, count)
    return [
        {
            'amount': format(Decimal(base + (1 if index < remainder else 0)) / 100, '.2f'),
            'due_date': _next_month(first_due_date, index),
            'notes': '',
        }
        for index in range(count)
    ]


@transaction.atomic
def create_purchase_order(*, branch, supplier, order_type, items, user,
                           global_discount='0.00', freight_total='0.00',
                           other_expenses_total='0.00', installments=None,
                           installment_count=None, first_due_date=None,
                           support_session=None, exclusive_supplier_override=False, **document):
    if 'attachment_reference' in document:
        raise ValidationError({
            'attachment_reference': 'Envie anexos pelo endpoint protegido da compra.'
        })
    branch = _authorized_branch(
        branch, user, 'purchases.create', lock=True, support_session=support_session
    )
    if installments is not None or installment_count is not None:
        _authorized_branch(
            branch, user, 'purchases.manage_payables',
            support_session=support_session,
        )
    company = Company.objects.select_for_update().get(pk=branch.company_id)
    try:
        supplier = Supplier.objects.select_for_update().get(
            pk=_pk(supplier), company=company, status=Status.ACTIVE
        )
    except (Supplier.DoesNotExist, TypeError, ValueError) as error:
        raise ValidationError({'supplier': 'Fornecedor ativo invalido para esta empresa.'}) from error
    if order_type not in PurchaseOrderType.values:
        raise ValidationError({'order_type': 'Tipo de compra invalido.'})
    requested_discount = _money(global_discount, 'global_discount')
    requested_freight = _money(freight_total, 'freight_total')
    requested_other = _money(other_expenses_total, 'other_expenses_total')
    order = PurchaseOrder.objects.create(
        company=company,
        branch=branch,
        supplier=supplier,
        order_number=_next_order_number(company),
        order_type=order_type,
        status=PurchaseOrderStatus.DRAFT,
        gross_total=Decimal('0.00'),
        global_discount=Decimal('0.00'),
        freight_total=Decimal('0.00'),
        other_expenses_total=Decimal('0.00'),
        payable_total=Decimal('0.00'),
        document_number=(document.get('document_number') or '').strip(),
        document_key=(document.get('document_key') or '').strip(),
        document_series=(document.get('document_series') or '').strip(),
        document_date=document.get('document_date'),
        notes=(document.get('notes') or '').strip(),
        exclusive_supplier_override=exclusive_supplier_override,
        created_by=user,
    )
    created_items = _create_items(order, items, allow_exclusive=exclusive_supplier_override)
    order.global_discount = requested_discount
    order.freight_total = requested_freight
    order.other_expenses_total = requested_other
    _allocate_order(order, created_items)
    if installment_count is not None:
        installments = _automatic_installments(order, installment_count, first_due_date)
    _create_installments(order, installments, user=user)
    audit_log(
        actor=user,
        action='purchase.create',
        obj=order,
        company=company,
        branch=branch,
        after=_order_snapshot(order),
        metadata={
            'summary': f'Compra {order.order_number} criada em rascunho.',
            'exclusive_supplier_override': exclusive_supplier_override,
            'exclusive_supplier_overrides': (
                _exclusive_supplier_override_details(created_items, supplier)
                if exclusive_supplier_override else []
            ),
        },
    )
    return order


@transaction.atomic
def update_purchase_order(*, purchase_order, user, items=None, installments=None,
                           installment_count=None, first_due_date=None,
                          support_session=None, **values):
    if 'attachment_reference' in values:
        raise ValidationError({
            'attachment_reference': 'Envie anexos pelo endpoint protegido da compra.'
        })
    order = PurchaseOrder.objects.select_for_update().select_related(
        'company', 'branch', 'supplier'
    ).get(pk=_pk(purchase_order))
    _authorized_branch(
        order.branch, user, 'purchases.create', support_session=support_session
    )
    if installments is not None or installment_count is not None:
        _authorized_branch(
            order.branch, user, 'purchases.manage_payables',
            support_session=support_session,
        )
    financial_fields = {
        'global_discount', 'freight_total', 'other_expenses_total'
    }
    changes_commercial_terms = bool(
        items is not None or installments is not None or installment_count is not None
        or financial_fields.intersection(values)
    )
    if changes_commercial_terms and (
        order.status != PurchaseOrderStatus.DRAFT or order.receipts.exists()
    ):
        raise ValidationError({
            'status': 'Valores, itens e parcelas somente podem mudar antes do recebimento, no rascunho.'
        })
    before = _order_snapshot(order)
    if items is not None:
        if order.items.exists():
            raise ValidationError({
                'items': 'Itens ja snapshotados nao podem ser substituidos; crie outro rascunho.'
            })
        created_items = _create_items(order, items)
    else:
        created_items = list(order.items.select_for_update())
    for field in ('global_discount', 'freight_total', 'other_expenses_total'):
        if field in values:
            setattr(order, field, _money(values[field], field))
    for field in (
        'document_number', 'document_key', 'document_series', 'notes', 'document_date'
    ):
        if field in values:
            value = values[field]
            setattr(order, field, value.strip() if isinstance(value, str) else value)
    if financial_fields.intersection(values) or items is not None:
        _allocate_order(order, created_items)
    document_fields = tuple(
        field for field in (
            'document_number', 'document_key', 'document_series', 'notes',
            'document_date',
        ) if field in values
    )
    if document_fields:
        order.save(update_fields=(*document_fields, 'updated_at'))
    if installment_count is not None:
        installments = _automatic_installments(order, installment_count, first_due_date)
    if installments is not None:
        _create_installments(order, installments, user=user)
    _assert_installment_reconciliation(order)
    audit_log(
        actor=user,
        action='purchase.update',
        obj=order,
        company=order.company,
        branch=order.branch,
        before=before,
        after=_order_snapshot(order),
        metadata={'summary': f'Rascunho {order.order_number} atualizado.'},
    )
    return order


@transaction.atomic
def set_purchase_attachment(*, purchase_order, attachment, user, support_session=None):
    order = PurchaseOrder.objects.select_for_update().select_related(
        'company', 'branch'
    ).get(pk=_pk(purchase_order))
    _authorized_branch(
        order.branch, user, 'purchases.create', support_session=support_session
    )
    previous_name = order.attachment.name if order.attachment else ''
    order.attachment = attachment
    order.save(update_fields=('attachment', 'updated_at'))
    if previous_name and previous_name != order.attachment.name:
        storage = order.attachment.storage
        transaction.on_commit(lambda: storage.delete(previous_name))
    audit_log(
        actor=user,
        action='purchase.attachment.upload',
        obj=order,
        company=order.company,
        branch=order.branch,
        before={'attachment': bool(previous_name)},
        after={'attachment': True},
        metadata={'summary': f'Anexo da compra {order.order_number} atualizado.'},
    )
    return order


@transaction.atomic
def add_purchase_attachment(*, purchase_order, attachment, user, support_session=None):
    from .models import PurchaseAttachment

    order = PurchaseOrder.objects.select_for_update().select_related('company', 'branch').get(
        pk=_pk(purchase_order)
    )
    _authorized_branch(order.branch, user, 'purchases.create', support_session=support_session)
    item = PurchaseAttachment.objects.create(
        purchase_order=order, company=order.company, attachment=attachment, uploaded_by=user,
    )
    audit_log(
        actor=user, action='purchase.attachment.upload', obj=item,
        company=order.company, branch=order.branch,
        after={'purchase_order_id': order.pk, 'attachment': True},
        metadata={'summary': f'Anexo adicionado à compra {order.order_number}.'},
    )
    return item


@transaction.atomic
def remove_purchase_attachment(*, purchase_order, attachment_id, user, support_session=None):
    from .models import PurchaseAttachment

    order = PurchaseOrder.objects.select_for_update().select_related('company', 'branch').get(
        pk=_pk(purchase_order)
    )
    _authorized_branch(order.branch, user, 'purchases.create', support_session=support_session)
    item = PurchaseAttachment.objects.select_for_update().get(
        pk=attachment_id, purchase_order=order, status='active'
    )
    item.status = 'inactive'
    item.save(update_fields=('status', 'updated_at'))
    audit_log(
        actor=user, action='purchase.attachment.remove', obj=item,
        company=order.company, branch=order.branch,
        before={'status': 'active'}, after={'status': 'inactive'},
    )
    return item


@transaction.atomic
def set_installments(*, purchase_order, installments, user, support_session=None):
    order = PurchaseOrder.objects.select_for_update().select_related(
        'branch', 'company', 'supplier'
    ).get(pk=_pk(purchase_order))
    _authorized_branch(
        order.branch, user, 'purchases.manage_payables', support_session=support_session
    )
    if order.status != PurchaseOrderStatus.DRAFT:
        raise ValidationError({'status': 'Parcelas somente podem ser definidas no rascunho.'})
    created = _create_installments(order, installments, user=user)
    audit_log(
        actor=user,
        action='purchase.payables.define',
        obj=order,
        company=order.company,
        branch=order.branch,
        after={
            'payable_total': str(order.payable_total),
            'installments': [
                {'id': item.pk, 'number': item.installment_number, 'amount': str(item.amount),
                 'due_date': str(item.due_date)}
                for item in created
            ],
        },
        metadata={'summary': f'Parcelas da compra {order.order_number} definidas.'},
    )
    return created


@transaction.atomic
def place_purchase_order(*, purchase_order, user, support_session=None,
                         exclusive_supplier_override=False):
    order = PurchaseOrder.objects.select_for_update().select_related(
        'branch', 'company', 'supplier'
    ).get(pk=_pk(purchase_order))
    _authorized_branch(
        order.branch, user, 'purchases.place', support_session=support_session
    )
    if order.order_type != PurchaseOrderType.ORDER or order.status != PurchaseOrderStatus.DRAFT:
        raise ValidationError({'status': 'Somente pedido em rascunho pode ser realizado.'})
    item_ids = list(order.items.values_list('pk', flat=True))
    items = list(
        order.items.select_for_update().filter(pk__in=item_ids)
    ) if item_ids else []
    items = list(order.items.select_related(
        'product_supplier_unit__product_supplier__product', 'product_supplier'
    ).filter(pk__in=item_ids))
    if not items:
        raise ValidationError({'items': 'A compra deve possuir itens.'})
    allow_exclusive = bool(
        order.exclusive_supplier_override and exclusive_supplier_override
    )
    for item in items:
        _validate_purchase_item(
            item, company=order.company, supplier=order.supplier,
            allow_exclusive=allow_exclusive,
        )
    _assert_installment_reconciliation(order)
    order.status = PurchaseOrderStatus.PLACED
    order.placed_by = user
    order.placed_at = timezone.now()
    order._allow_status_transition = True
    order.save(update_fields=('status', 'placed_by', 'placed_at', 'updated_at'))
    audit_log(
        actor=user, action='purchase.place', obj=order, company=order.company,
        branch=order.branch, before={'status': PurchaseOrderStatus.DRAFT},
        after=model_snapshot(order, ('status', 'placed_by_id', 'placed_at')),
        metadata={
            'summary': f'Pedido {order.order_number} realizado.',
            'exclusive_supplier_override': allow_exclusive,
            'exclusive_supplier_overrides': (
                _exclusive_supplier_override_details(items, order.supplier)
                if allow_exclusive else []
            ),
        },
    )
    return order


def _canonical_receipt_payload(order, raw_items, notes, divergence_reason):
    if not isinstance(raw_items, list) or not raw_items:
        raise ValidationError({'items': 'Informe ao menos um item recebido.'})
    canonical = []
    seen = set()
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict) or raw.get('purchase_order_item', raw.get('item')) in (None, ''):
            raise ValidationError({'items': f'Item {index + 1}: informe a linha da compra.'})
        try:
            item_id = int(raw.get('purchase_order_item', raw.get('item')))
        except (TypeError, ValueError) as error:
            raise ValidationError({'items': f'Item {index + 1}: linha invalida.'}) from error
        if item_id in seen:
            raise ValidationError({'items': 'Nao repita uma linha no mesmo recebimento.'})
        seen.add(item_id)
        quantity_field = (
            'received_stock_quantity'
            if raw.get('received_stock_quantity') is not None
            else 'received_quantity'
        )
        quantity = strict_decimal(
            raw.get(quantity_field, raw.get('quantity')),
            f'items.{index}.{quantity_field}',
            places=6,
            nonnegative=True,
        )
        canonical.append({
            'purchase_order_item': item_id,
            quantity_field: format(quantity, 'f'),
            'divergence_reason': (raw.get('divergence_reason') or '').strip(),
        })
    canonical.sort(key=lambda item: item['purchase_order_item'])
    if not any(
        Decimal(item.get('received_stock_quantity', item.get('received_quantity', '0'))) > 0
        for item in canonical
    ):
        raise ValidationError({'items': 'Confirme quantidade positiva para ao menos um item.'})
    return {
        'purchase_order': order.pk,
        'items': canonical,
        'notes': (notes or '').strip(),
        'divergence_reason': (divergence_reason or '').strip(),
    }


def _payload_fingerprint(payload):
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


@transaction.atomic
def receive_purchase_order(*, purchase_order, idempotency_key, items, user,
                           notes='', divergence_reason='', support_session=None):
    try:
        key = str(idempotency_key)
        from uuid import UUID
        key = UUID(key)
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError({'idempotency_key': 'Informe um UUID valido.'}) from error

    order_reference = PurchaseOrder.objects.only('branch_id').get(pk=_pk(purchase_order))
    branch = _authorized_branch(
        order_reference.branch_id, user, 'purchases.receive', lock=True,
        support_session=support_session,
    )
    order = PurchaseOrder.objects.select_for_update().select_related(
        'company', 'branch', 'supplier'
    ).get(pk=order_reference.pk, branch=branch)
    payload = _canonical_receipt_payload(order, items, notes, divergence_reason)
    fingerprint = _payload_fingerprint(payload)
    replay = PurchaseReceipt.objects.filter(branch=branch, idempotency_key=key).first()
    if replay:
        if replay.payload_fingerprint != fingerprint:
            raise DomainValidationError(
                code='idempotency_key_conflict',
                message='A chave de idempotencia ja foi usada com outros dados.',
                details={'idempotency_key': str(key), 'receipt_id': str(replay.pk)},
            )
        replay._idempotency_replayed = True
        return replay

    valid_statuses = (
        (PurchaseOrderStatus.DRAFT,)
        if order.order_type == PurchaseOrderType.DIRECT
        else (PurchaseOrderStatus.PLACED, PurchaseOrderStatus.PARTIALLY_RECEIVED)
    )
    if order.status not in valid_statuses:
        raise ValidationError({'status': 'A compra nao esta disponivel para recebimento.'})
    _assert_installment_reconciliation(order)
    order_item_ids = list(order.items.values_list('pk', flat=True))
    _locked = list(order.items.select_for_update().filter(pk__in=order_item_ids)) if order_item_ids else []
    order_items = {
        item.pk: item
        for item in order.items.select_related(
            'product', 'product_supplier_unit__product_supplier__product'
        ).filter(pk__in=order_item_ids).order_by('pk')
    }
    supplied_ids = {item['purchase_order_item'] for item in payload['items']}
    if not supplied_ids.issubset(order_items):
        raise ValidationError({'items': 'Um item nao pertence a compra informada.'})
    previous = {
        item_id: (
            PurchaseReceiptItem.objects.filter(
                purchase_order_item_id=item_id
            ).aggregate(total=Sum('received_quantity'))['total'] or Decimal('0.000000')
        )
        for item_id in order_items
    }
    previous_stock = {
        item_id: (
            PurchaseReceiptItem.objects.filter(
                purchase_order_item_id=item_id
            ).aggregate(total=Sum('stock_quantity'))['total'] or Decimal('0.000000')
        )
        for item_id in order_items
    }
    if order.order_type == PurchaseOrderType.DIRECT and supplied_ids != set(order_items):
        raise ValidationError({'items': 'Entrada direta deve confirmar todos os itens.'})
    if order.order_type == PurchaseOrderType.DIRECT:
        for order_item in order_items.values():
            _validate_purchase_item(
                order_item, company=order.company, supplier=order.supplier,
                allow_exclusive=order.exclusive_supplier_override,
            )

    prepared = []
    resulting_complete = True
    any_divergence = False
    by_id = {item['purchase_order_item']: item for item in payload['items']}
    for item_id, order_item in order_items.items():
        ordered_stock_quantity = order_item.ordered_stock_quantity
        pending_before = max(ordered_stock_quantity - previous_stock[item_id], Decimal('0'))
        raw = by_id.get(item_id)
        received_stock_quantity = Decimal('0.000000')
        if raw:
            received_stock_quantity = Decimal(
                raw.get('received_stock_quantity', '0')
            ) if 'received_stock_quantity' in raw else (
                Decimal(raw['received_quantity']) * order_item.conversion_factor
            )
        if (
            order_item.product.unit == Unit.UNIT
            and received_stock_quantity != received_stock_quantity.to_integral_value()
        ):
            raise ValidationError({
                'items': (
                    f'Item {order_item.line_number}: cada recebimento de produto UN '
                    'deve informar unidades inteiras.'
                )
            })
        if received_stock_quantity.quantize(Decimal('0.001')) != received_stock_quantity:
            raise ValidationError({
                'items': (
                    f'Item {order_item.line_number}: a quantidade em estoque deve possuir '
                    'no maximo tres casas decimais.'
                )
            })
        received_now = (
            received_stock_quantity / order_item.conversion_factor
        ).quantize(SIX_PLACES, rounding=ROUND_HALF_UP)
        accumulated_stock = previous_stock[item_id] + received_stock_quantity
        accumulated = (
            accumulated_stock / order_item.conversion_factor
        ).quantize(SIX_PLACES, rounding=ROUND_HALF_UP)
        pending_after_stock = max(ordered_stock_quantity - accumulated_stock, Decimal('0'))
        pending_after = (
            pending_after_stock / order_item.conversion_factor
        ).quantize(SIX_PLACES, rounding=ROUND_HALF_UP)
        if pending_after_stock > 0:
            resulting_complete = False
        divergence_stock = received_stock_quantity - pending_before if raw else -pending_before
        divergence = (
            divergence_stock / order_item.conversion_factor
        ).quantize(SIX_PLACES, rounding=ROUND_HALF_UP)
        if divergence_stock != 0:
            any_divergence = True
        reason = (
            raw['divergence_reason'] if raw else ''
        ) or payload['divergence_reason']
        prepared.append((
            order_item, previous[item_id], received_now, accumulated, pending_after,
            divergence, reason, received_stock_quantity,
        ))
    missing_lines = supplied_ids != set(order_items)
    unexplained_lines = any(not row[6] for row in prepared if row[5] != 0)
    if any_divergence and not payload['divergence_reason'] and (
        missing_lines or unexplained_lines
    ):
        raise ValidationError({
            'divergence_reason': 'Informe o motivo do recebimento parcial ou divergente.'
        })
    if order.order_type == PurchaseOrderType.DIRECT and not resulting_complete:
        raise ValidationError({'items': 'Entrada direta deve ser recebida integralmente.'})

    receipt = PurchaseReceipt.objects.create(
        purchase_order=order,
        company=order.company,
        branch=branch,
        idempotency_key=key,
        payload_fingerprint=fingerprint,
        payload=payload,
        notes=payload['notes'],
        divergence_reason=payload['divergence_reason'],
        confirmed_by=user,
        confirmed_at=timezone.now(),
    )
    receipt_items = []
    for (
        order_item, previously_received, received_now, accumulated,
        pending_after, divergence, reason, stock_quantity,
    ) in prepared:
        stock_quantity = stock_quantity.quantize(Decimal('0.001'))
        fraction_config = FractionableProductConfig.objects.filter(
            product=order_item.product, tracking_active=True
        ).first()
        stock_content_quantity = (
            (stock_quantity * fraction_config.package_content).quantize(
                Decimal('0.000000001'), rounding=ROUND_HALF_UP
            )
            if fraction_config else None
        )
        if stock_quantity > 0:
            purchase_receipt_entry(
                product=order_item.product,
                branch=branch,
                quantity=stock_quantity,
                effective_unit_cost=order_item.effective_stock_unit_cost,
                user=user,
                operation_reference=receipt.pk,
                reason=f'Recebimento da compra {order.order_number}',
            )
        receipt_items.append(PurchaseReceiptItem.objects.create(
            receipt=receipt,
            purchase_order_item=order_item,
            ordered_quantity_snapshot=order_item.ordered_quantity,
            previously_received_quantity=previously_received,
            received_quantity=received_now,
            accumulated_quantity=accumulated,
            pending_quantity=pending_after,
            divergence_quantity=divergence,
            divergence_reason=reason,
            conversion_factor_snapshot=order_item.conversion_factor,
            stock_quantity=stock_quantity,
            stock_content_quantity=stock_content_quantity,
            stock_content_unit=fraction_config.content_unit if fraction_config else '',
            stock_package_content_snapshot=(
                fraction_config.package_content if fraction_config else None
            ),
            effective_stock_unit_cost_snapshot=order_item.effective_stock_unit_cost,
            product_name_snapshot=order_item.product_name,
            supplier_name_snapshot=order_item.supplier_name,
            presentation_snapshot=(
                f'{order_item.presentation_unit_code} - '
                f'{order_item.presentation_description}'
            ),
        ))
    previous_status = order.status
    order.status = (
        PurchaseOrderStatus.RECEIVED
        if resulting_complete else PurchaseOrderStatus.PARTIALLY_RECEIVED
    )
    order._allow_status_transition = True
    order.save(update_fields=('status', 'updated_at'))
    audit_log(
        actor=user,
        action='purchase.receive',
        obj=receipt,
        company=order.company,
        branch=branch,
        before={'purchase_status': previous_status},
        after={
            'purchase_status': order.status,
            'confirmed_at': str(receipt.confirmed_at),
            'items': [
                model_snapshot(item, (
                    'purchase_order_item_id', 'ordered_quantity_snapshot',
                    'previously_received_quantity', 'received_quantity',
                    'accumulated_quantity', 'pending_quantity', 'divergence_quantity',
                    'divergence_reason', 'stock_quantity',
                    'effective_stock_unit_cost_snapshot',
                ))
                for item in receipt_items
            ],
        },
        metadata={
            'summary': f'Recebimento {receipt.pk} confirmado para {order.order_number}.',
            'idempotency_key': str(key),
        },
    )
    return receipt


@transaction.atomic
def close_partial_purchase_order(*, purchase_order, user, reason, support_session=None):
    order = PurchaseOrder.objects.select_for_update().select_related(
        'branch', 'company'
    ).get(pk=_pk(purchase_order))
    _authorized_branch(
        order.branch, user, 'purchases.close', support_session=support_session
    )
    reason = (reason or '').strip()
    if order.status != PurchaseOrderStatus.PARTIALLY_RECEIVED:
        raise ValidationError({'status': 'Somente compra parcialmente recebida pode ser encerrada.'})
    if len(reason) < 3:
        raise ValidationError({'reason': 'Informe o motivo do encerramento parcial.'})
    order.status = PurchaseOrderStatus.CLOSED_PARTIAL
    order.closed_by = user
    order.closed_at = timezone.now()
    order.closure_reason = reason
    order._allow_status_transition = True
    order.save(update_fields=(
        'status', 'closed_by', 'closed_at', 'closure_reason', 'updated_at'
    ))
    audit_log(
        actor=user, action='purchase.close_partial', obj=order,
        company=order.company, branch=order.branch,
        before={'status': PurchaseOrderStatus.PARTIALLY_RECEIVED},
        after=model_snapshot(order, ('status', 'closed_by_id', 'closed_at', 'closure_reason')),
        metadata={'summary': f'Pendencia da compra {order.order_number} encerrada.'},
    )
    return order


@transaction.atomic
def cancel_purchase_order(*, purchase_order, user, reason, support_session=None):
    order = PurchaseOrder.objects.select_for_update().select_related(
        'branch', 'company'
    ).get(pk=_pk(purchase_order))
    _authorized_branch(
        order.branch, user, 'purchases.close', support_session=support_session
    )
    reason = (reason or '').strip()
    if order.status not in (PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.PLACED):
        raise ValidationError({'status': 'Somente compra sem recebimento pode ser cancelada.'})
    if order.receipts.exists():
        raise ValidationError({'status': 'Compra com recebimento confirmado nao pode ser cancelada.'})
    if len(reason) < 3:
        raise ValidationError({'reason': 'Informe o motivo do cancelamento.'})
    paid = order.installments.filter(status=PayableInstallmentStatus.PAID).exists()
    if paid:
        raise ValidationError({'installments': 'A compra possui parcela paga e nao pode ser cancelada.'})
    previous_status = order.status
    now = timezone.now()
    cancelled_installments = []
    for installment in order.installments.select_for_update().filter(
        status=PayableInstallmentStatus.PENDING
    ):
        installment_before = _installment_snapshot(installment)
        installment.status = PayableInstallmentStatus.CANCELLED
        installment.cancelled_at = now
        installment.cancelled_by = user
        installment.cancellation_reason = f'Compra cancelada: {reason}'
        installment._allow_status_transition = True
        installment.save(update_fields=(
            'status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 'updated_at'
        ))
        _audit_installment(
            installment=installment,
            user=user,
            action='purchase.payable.cancel',
            summary=(
                f'Parcela {installment.installment_number} de '
                f'{order.order_number} cancelada com a compra.'
            ),
            before=installment_before,
        )
        cancelled_installments.append(installment.pk)
    order.status = PurchaseOrderStatus.CANCELLED
    order.closed_by = user
    order.closed_at = now
    order.closure_reason = reason
    order._allow_status_transition = True
    order.save(update_fields=(
        'status', 'closed_by', 'closed_at', 'closure_reason', 'updated_at'
    ))
    audit_log(
        actor=user, action='purchase.cancel', obj=order,
        company=order.company, branch=order.branch,
        before={'status': previous_status},
        after=model_snapshot(order, ('status', 'closed_by_id', 'closed_at', 'closure_reason')),
        metadata={
            'summary': f'Compra {order.order_number} cancelada.',
            'cancelled_installment_ids': cancelled_installments,
        },
    )
    return order


@transaction.atomic
def pay_installment(*, installment, user, payment_method='MANUAL', paid_amount=None,
                    paid_date=None, notes=None, support_session=None):
    item = PayableInstallment.objects.select_for_update().select_related(
        'purchase_order__branch', 'purchase_order__company'
    ).get(pk=_pk(installment))
    order = item.purchase_order
    _authorized_branch(
        order.branch, user, 'purchases.manage_payables', support_session=support_session
    )
    if order.status == PurchaseOrderStatus.DRAFT:
        raise ValidationError({'purchase_order': 'Não é possível pagar parcelas de uma compra em rascunho.'})
    if item.status != PayableInstallmentStatus.PENDING:
        raise ValidationError({'status': 'Somente parcela pendente pode ser paga.'})
    method = (payment_method or '').strip()
    if not method:
        raise ValidationError({'payment_method': 'Informe a forma de pagamento utilizada.'})
    amount = _money(paid_amount if paid_amount is not None else item.amount, 'paid_amount')
    if amount != item.amount:
        raise ValidationError({'paid_amount': 'O valor pago deve quitar integralmente a parcela.'})
    before = _installment_snapshot(item)
    item.status = PayableInstallmentStatus.PAID
    item.paid_at = (
        timezone.make_aware(datetime.combine(paid_date, time.min))
        if paid_date else timezone.now()
    )
    item.paid_by = user
    item.paid_amount = amount
    item.paid_payment_method = method
    if notes is not None:
        item.notes = notes.strip()
    item._allow_status_transition = True
    item.save(update_fields=(
        'status', 'paid_at', 'paid_by', 'paid_amount', 'paid_payment_method',
        'notes', 'updated_at',
    ))
    _audit_installment(
        installment=item,
        user=user,
        action='purchase.payable.pay',
        summary=(
            f'Parcela {item.installment_number} de '
            f'{order.order_number} paga manualmente.'
        ),
        before=before,
    )
    return item


@transaction.atomic
def cancel_installment(*, installment, user, reason, support_session=None):
    item = PayableInstallment.objects.select_for_update().select_related(
        'purchase_order__branch', 'purchase_order__company'
    ).get(pk=_pk(installment))
    order = item.purchase_order
    _authorized_branch(
        order.branch, user, 'purchases.manage_payables', support_session=support_session
    )
    reason = (reason or '').strip()
    if item.status != PayableInstallmentStatus.PENDING:
        raise ValidationError({'status': 'Somente parcela pendente pode ser cancelada.'})
    if len(reason) < 3:
        raise ValidationError({'reason': 'Informe o motivo do cancelamento.'})
    before = _installment_snapshot(item)
    item.status = PayableInstallmentStatus.CANCELLED
    item.cancelled_at = timezone.now()
    item.cancelled_by = user
    item.cancellation_reason = reason
    item._allow_status_transition = True
    item.save(update_fields=(
        'status', 'cancelled_at', 'cancelled_by', 'cancellation_reason', 'updated_at'
    ))
    _audit_installment(
        installment=item,
        user=user,
        action='purchase.payable.cancel',
        summary=(
            f'Parcela {item.installment_number} de '
            f'{order.order_number} cancelada.'
        ),
        before=before,
    )
    return item
