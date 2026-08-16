import re

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.companies.models import Company

from .models import Category, InventoryBehavior, Product, ProductComponent, Unit


@transaction.atomic
def create_product(**product_data):
    company = Company.objects.select_for_update().get(pk=product_data['company'].pk)
    product_data['company'] = company
    if product_data.get('internal_code', '').strip():
        return Product.objects.create(**product_data)
    product_data.pop('internal_code', None)

    generated = Product.objects.filter(
        company=company, internal_code__iregex=r'^P[0-9]{6}$'
    ).values_list('internal_code', flat=True)
    number = max(
        (int(match.group(1)) for code in generated if (match := re.match(r'^P(\d{6})$', code, re.I))),
        default=0,
    )
    for _ in range(10):
        number += 1
        candidate = f'P{number:06d}'
        try:
            with transaction.atomic():
                return Product.objects.create(internal_code=candidate, **product_data)
        except (IntegrityError, ValidationError):
            if not Product.objects.filter(
                company=company, internal_code__iexact=candidate
            ).exists():
                raise
    raise ValidationError({'internal_code': 'Nao foi possivel gerar um codigo unico.'})


@transaction.atomic
def reorder_categories(*, company, category_ids):
    Company.objects.select_for_update().get(pk=company.pk)
    categories = list(
        Category.objects.select_for_update().filter(company=company)
    )
    if len(category_ids) != len(set(category_ids)) or set(category_ids) != {
        category.pk for category in categories
    }:
        raise ValidationError(
            {'category_ids': 'Informe exatamente todas as categorias da empresa, sem repeticao.'}
        )
    by_id = {category.pk: category for category in categories}
    for position, category_id in enumerate(category_ids):
        category = by_id[category_id]
        category.sort_order = position
    Category.objects.bulk_update(categories, ['sort_order'])
    return categories


@transaction.atomic
def replace_composition(*, product, components):
    company_id = product.company_id
    Company.objects.select_for_update().get(pk=company_id)

    component_ids = [item['component_product'].pk for item in components]
    product_ids = sorted(set(component_ids) | {product.pk})
    locked_products = {
        item.pk: item
        for item in Product.objects.select_for_update().filter(
            pk__in=product_ids
        ).order_by('pk')
    }
    product = locked_products[product.pk]
    if product.inventory_behavior != InventoryBehavior.COMPONENTS:
        raise ValidationError(
            {'inventory_behavior': 'Somente produtos com comportamento components possuem composicao.'}
        )

    if len(component_ids) != len(set(component_ids)):
        raise ValidationError({'components': 'Nao repita produtos na composicao.'})
    if product.is_sellable and not components:
        raise ValidationError(
            {'components': 'Um produto composto vendavel deve possuir componentes.'}
        )

    for item in components:
        item['component_product'] = locked_products[item['component_product'].pk]
        if (
            item['component_product'].unit == Unit.UNIT
            and item['quantity'] != item['quantity'].to_integral_value()
        ):
            raise ValidationError(
                {'components': 'A quantidade de um componente UN deve ser inteira.'}
            )

    ProductComponent.objects.filter(parent_product=product).delete()
    for item in components:
        ProductComponent.objects.create(parent_product=product, **item)
    return product
