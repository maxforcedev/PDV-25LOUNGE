import re

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.companies.models import Branch, Company

from .models import (
    BranchProductPrice, Category, FractionableProductConfig, InventoryBehavior,
    ModifierGroup, ModifierOption, Product, ProductBranchConfig, ProductComponent, ProductFractionComponent,
    ProductModifierGroup,
    ProductProductionDestination, ProductionDestination, SalesChannel, Unit,
)


@transaction.atomic
def create_product(*, components=None, fraction_components=None, **product_data):
    company = Company.objects.select_for_update().get(pk=product_data['company'].pk)
    product_data['company'] = company
    desired_sellable = product_data.get('is_sellable', True)
    if product_data.get('inventory_behavior') == InventoryBehavior.COMPONENTS:
        product_data['is_sellable'] = False

    product = None
    if product_data.get('internal_code', '').strip():
        product = Product.objects.create(**product_data)
    else:
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
                    product = Product.objects.create(internal_code=candidate, **product_data)
                break
            except (IntegrityError, ValidationError):
                if not Product.objects.filter(
                    company=company, internal_code__iexact=candidate
                ).exists():
                    raise
        if product is None:
            raise ValidationError({'internal_code': 'Não foi possível gerar um código único.'})

    if product.inventory_behavior == InventoryBehavior.COMPONENTS:
        replace_composition(product=product, components=components or [])
        replace_fraction_composition(
            product=product, components=fraction_components or []
        )
        if desired_sellable:
            product.is_sellable = True
            product.save(update_fields=('is_sellable', 'updated_at'))
    return product


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


def _reorder(*, queryset, item_ids, field_name):
    items = list(queryset.select_for_update())
    if len(item_ids) != len(set(item_ids)) or set(item_ids) != {item.pk for item in items}:
        raise ValidationError({field_name: 'Informe exatamente todos os itens do escopo, sem repeticao.'})
    by_id = {item.pk: item for item in items}
    for position, item_id in enumerate(item_ids):
        by_id[item_id].sort_order = position
    type(items[0]).objects.bulk_update(items, ['sort_order']) if items else None
    return [by_id[item_id] for item_id in item_ids]


@transaction.atomic
def reorder_modifier_groups(*, company, group_ids):
    Company.objects.select_for_update().get(pk=company.pk)
    return _reorder(
        queryset=ModifierGroup.objects.filter(company=company), item_ids=group_ids,
        field_name='group_ids',
    )


@transaction.atomic
def reorder_modifier_options(*, group, option_ids):
    ModifierGroup.objects.select_for_update().get(pk=group.pk)
    return _reorder(
        queryset=ModifierOption.objects.filter(modifier_group=group), item_ids=option_ids,
        field_name='option_ids',
    )


@transaction.atomic
def reorder_product_modifier_groups(*, product, link_ids):
    Product.objects.select_for_update().get(pk=product.pk)
    return _reorder(
        queryset=ProductModifierGroup.objects.filter(product=product), item_ids=link_ids,
        field_name='link_ids',
    )


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
            {'inventory_behavior': 'Somente produtos com comportamento components possuem composição.'}
        )

    if len(component_ids) != len(set(component_ids)):
        raise ValidationError({'components': 'Não repita produtos na composição.'})
    if product.is_sellable and not components:
        raise ValidationError(
            {'components': 'Um produto composto vendável deve possuir componentes.'}
        )

    prepared = []
    for index, item in enumerate(components):
        component = locked_products.get(item['component_product'].pk)
        if component is None:
            raise ValidationError(
                {'components': {index: {'component_product': ['Componente invalido.']}}}
            )
        if component.pk == product.pk:
            raise ValidationError(
                {'components': {index: {'component_product': ['Um produto nao pode compor a si mesmo.']}}}
            )
        if component.company_id != company_id:
            raise ValidationError(
                {'components': {index: {'component_product': ['O componente deve pertencer a mesma empresa.']}}}
            )
        if component.inventory_behavior != InventoryBehavior.DIRECT:
            raise ValidationError(
                {'components': {index: {'component_product': ['Somente produtos com estoque próprio podem ser componentes.']}}}
            )
        if (
            component.unit == Unit.UNIT
            and item['quantity'] != item['quantity'].to_integral_value()
        ):
            raise ValidationError(
                {'components': {index: {'quantity': ['A quantidade de um componente UN deve ser inteira.']}}}
            )
        candidate = ProductComponent(
            parent_product=product,
            component_product=component,
            quantity=item['quantity'],
        )
        candidate.full_clean(validate_unique=False, validate_constraints=False)
        prepared.append(candidate)

    ProductComponent.objects.filter(parent_product=product).delete()
    for candidate in prepared:
        candidate.save()
    return product


@transaction.atomic
def replace_fraction_composition(*, product, components):
    Company.objects.select_for_update().get(pk=product.company_id)
    component_ids = [item['component_product'].pk for item in components]
    if len(component_ids) != len(set(component_ids)):
        raise ValidationError({'fraction_components': 'Nao repita produtos na composicao.'})
    products = {
        item.pk: item
        for item in Product.objects.select_for_update().filter(
            pk__in=sorted(set(component_ids) | {product.pk})
        ).order_by('pk')
    }
    product = products[product.pk]
    if product.inventory_behavior != InventoryBehavior.COMPONENTS:
        raise ValidationError({
            'inventory_behavior': 'Somente produtos components possuem composicao.'
        })
    if product.is_sellable and not components and not product.components.exists():
        raise ValidationError({
            'fraction_components': 'Um produto composto vendavel deve possuir componentes.'
        })
    prepared = []
    for index, item in enumerate(components):
        component = products.get(item['component_product'].pk)
        if component is None:
            raise ValidationError({'fraction_components': {index: 'Componente invalido.'}})
        candidate = ProductFractionComponent(
            parent_product=product,
            component_product=component,
            content_quantity=item['content_quantity'],
        )
        candidate.full_clean(validate_unique=False, validate_constraints=False)
        prepared.append(candidate)
    for row in ProductFractionComponent.objects.filter(parent_product=product):
        row.delete()
    for candidate in prepared:
        candidate.save()
    return product


@transaction.atomic
def copy_branch_configuration(*, products, source_branch, target_branches):
    product_ids = sorted({_item.pk if hasattr(_item, 'pk') else int(_item) for _item in products})
    locked_products = list(Product.objects.select_for_update().filter(pk__in=product_ids))
    if len(locked_products) != len(product_ids):
        raise ValidationError({'products': 'Um ou mais produtos sao invalidos.'})
    company_ids = {product.company_id for product in locked_products}
    if len(company_ids) != 1:
        raise ValidationError({'products': 'Todos os produtos devem pertencer a mesma empresa.'})
    company_id = company_ids.pop()
    source = Branch.objects.select_for_update().get(pk=source_branch, company_id=company_id)
    if source.pk in set(target_branches):
        raise ValidationError({'target_branches': 'A origem nao pode ser um destino.'})
    targets = list(Branch.objects.select_for_update().filter(
        pk__in=target_branches, company_id=company_id
    ).order_by('pk'))
    if len(targets) != len(set(target_branches)):
        raise ValidationError({'target_branches': 'Uma filial de destino e invalida.'})
    source_configs = {
        row.product_id: row for row in ProductBranchConfig.objects.filter(
            branch=source, product_id__in=product_ids
        )
    }
    source_prices = {
        row.product_id: row for row in BranchProductPrice.objects.filter(
            branch=source, product_id__in=product_ids
        )
    }
    source_links = list(ProductProductionDestination.objects.select_related(
        'destination'
    ).filter(product_id__in=product_ids, destination__branch=source))
    copied = []
    for target in targets:
        destination_map = {}
        for link in source_links:
            source_destination = link.destination
            destination = ProductionDestination.objects.filter(
                branch=target, code__iexact=source_destination.code
            ).first()
            if destination is None:
                destination = ProductionDestination.objects.create(
                    branch=target,
                    name=source_destination.name,
                    code=source_destination.code,
                    status=source_destination.status,
                )
            destination_map[source_destination.pk] = destination
        for product in locked_products:
            before = branch_configuration_snapshot(product, target)
            source_snapshot = branch_configuration_snapshot(product, source)
            source_config = source_configs.get(product.pk)
            config, _created = ProductBranchConfig.objects.get_or_create(
                product=product,
                branch=target,
                defaults={'is_available': True},
            )
            config.is_available = source_config.is_available if source_config else True
            for field in ('available_counter', 'available_table', 'available_command'):
                setattr(config, field, getattr(source_config, field) if source_config else None)
            config.save()
            source_price = source_prices.get(product.pk)
            target_price = BranchProductPrice.objects.filter(
                product=product, branch=target
            ).first()
            if source_price:
                if target_price:
                    target_price.sale_price = source_price.sale_price
                    target_price.save()
                else:
                    BranchProductPrice.objects.create(
                        product=product, branch=target, sale_price=source_price.sale_price
                    )
            elif target_price:
                target_price.delete()
            for link in list(ProductProductionDestination.objects.filter(
                product=product, destination__branch=target
            )):
                link.delete()
            for source_link in source_links:
                if source_link.product_id == product.pk:
                    ProductProductionDestination.objects.create(
                        product=product,
                        destination=destination_map[source_link.destination_id],
                    )
            copied.append({
                'product': product,
                'target_branch': target,
                'source': source_snapshot,
                'before': before,
                'after': branch_configuration_snapshot(product, target),
            })
    return copied


def branch_configuration_snapshot(product, branch):
    config = ProductBranchConfig.objects.filter(
        product=product, branch=branch
    ).first()
    price = BranchProductPrice.objects.filter(
        product=product, branch=branch
    ).values_list('sale_price', flat=True).first()
    overrides = {
        channel: getattr(config, f'available_{channel}') if config else None
        for channel in SalesChannel.values
    }
    return {
        'branch_id': branch.pk,
        'is_available': config.is_available if config else True,
        'channel_overrides': overrides,
        'effective_channels': {
            channel: (
                getattr(product, f'available_{channel}')
                if overrides[channel] is None else overrides[channel]
            )
            for channel in SalesChannel.values
        },
        'price_override': format(price, 'f') if price is not None else None,
        'effective_price': format(
            product.sale_price if price is None else price, 'f'
        ),
        'destinations': [
            {
                'id': destination.pk,
                'name': destination.name,
                'code': destination.code,
                'status': destination.status,
            }
            for destination in ProductionDestination.objects.filter(
                branch=branch, product_links__product=product
            ).order_by('code', 'pk')
        ],
    }


@transaction.atomic
def duplicate_product(*, product, options):
    source = Product.objects.select_for_update().select_related('company', 'category').get(
        pk=product.pk if hasattr(product, 'pk') else product
    )
    Company.objects.select_for_update().get(pk=source.company_id)
    base_name = f'{source.name} (copia)'
    name = base_name
    suffix = 2
    while Product.objects.filter(company=source.company, normalized_name=normalize_name(name)).exists():
        name = f'{base_name} {suffix}'
        suffix += 1
    duplicate = create_product(
        company=source.company,
        category=source.category,
        name=name,
        description=source.description,
        internal_code='',
        sku=None,
        barcode='',
        unit=source.unit,
        cost=source.cost,
        sale_price=source.sale_price,
        image=source.image,
        is_sellable=False if source.inventory_behavior == InventoryBehavior.COMPONENTS else source.is_sellable,
        is_favorite=False,
        available_counter=source.available_counter,
        available_table=source.available_table,
        available_command=source.available_command,
        participates_in_service_fee=source.participates_in_service_fee,
        participates_in_commission=source.participates_in_commission,
        inventory_behavior=source.inventory_behavior,
        status=source.status,
        components=[],
        fraction_components=[],
    )
    if options.get('composition') and source.inventory_behavior == InventoryBehavior.COMPONENTS:
        replace_composition(product=duplicate, components=[
            {'component_product': row.component_product, 'quantity': row.quantity}
            for row in source.components.select_related('component_product')
        ])
        replace_fraction_composition(product=duplicate, components=[
            {
                'component_product': row.component_product,
                'content_quantity': row.content_quantity,
            }
            for row in source.fraction_components.select_related('component_product')
        ])
        if source.is_sellable:
            duplicate.is_sellable = True
            duplicate.save(update_fields=('is_sellable', 'updated_at'))
    if options.get('fraction'):
        try:
            fraction = source.fraction_config
        except FractionableProductConfig.DoesNotExist:
            fraction = None
        if fraction:
            FractionableProductConfig.objects.create(
                product=duplicate,
                package_content=fraction.package_content,
                content_unit=fraction.content_unit,
            )
    if options.get('branch_config'):
        for config in source.branch_configs.all():
            ProductBranchConfig.objects.create(
                product=duplicate,
                branch=config.branch,
                is_available=config.is_available,
                available_counter=config.available_counter,
                available_table=config.available_table,
                available_command=config.available_command,
            )
        for price in source.branch_prices.all():
            BranchProductPrice.objects.create(
                product=duplicate, branch=price.branch, sale_price=price.sale_price
            )
    if options.get('destinations'):
        for link in source.production_destination_links.all():
            ProductProductionDestination.objects.create(
                product=duplicate, destination=link.destination
            )
    if options.get('suppliers'):
        from apps.suppliers.models import ProductSupplier, ProductSupplierUnit

        for relation in source.product_suppliers.select_related('supplier').prefetch_related('units'):
            new_relation = ProductSupplier.objects.create(
                company=source.company,
                product=duplicate,
                supplier=relation.supplier,
                supplier_code=relation.supplier_code,
                is_preferred=relation.is_preferred,
                is_exclusive=relation.is_exclusive,
                status=relation.status,
            )
            for unit in relation.units.all():
                ProductSupplierUnit.objects.create(
                    company=source.company,
                    product_supplier=new_relation,
                    unit_code=unit.unit_code,
                    description=unit.description,
                    conversion_factor=unit.conversion_factor,
                    barcode=unit.barcode,
                    is_default=unit.is_default,
                    status=unit.status,
                )
    return duplicate


def normalize_name(value):
    from .models import normalize_product_name

    return normalize_product_name(value)[1]
