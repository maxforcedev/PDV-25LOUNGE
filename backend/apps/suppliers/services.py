from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.companies.models import Company, Status
from apps.products.models import Product

from .models import ProductSupplier, ProductSupplierUnit, Supplier


def _save_with_validation(instance, conflict_error):
    try:
        with transaction.atomic():
            instance.save()
    except IntegrityError as error:
        raise ValidationError(conflict_error) from error
    return instance


def _lock_instance(instance):
    if isinstance(instance, Supplier):
        Company.objects.select_for_update().get(pk=instance.company_id)
        return Supplier.objects.select_for_update().get(pk=instance.pk)
    if isinstance(instance, ProductSupplier):
        Product.objects.select_for_update().get(pk=instance.product_id)
        Supplier.objects.select_for_update().get(pk=instance.supplier_id)
        return ProductSupplier.objects.select_for_update().get(pk=instance.pk)
    if isinstance(instance, ProductSupplierUnit):
        ProductSupplier.objects.select_for_update().get(
            pk=instance.product_supplier_id
        )
        return ProductSupplierUnit.objects.select_for_update().get(pk=instance.pk)
    raise TypeError('Tipo de registro de fornecedor não suportado.')


@transaction.atomic
def _save_supplier(*, instance=None, **values):
    if instance is not None:
        instance = _lock_instance(instance)
        for field, value in values.items():
            setattr(instance, field, value)
    else:
        company = values['company']
        Company.objects.select_for_update().get(pk=company.pk)
        instance = Supplier(**values)
    return _save_with_validation(
        instance,
        {'tax_id': 'Outro fornecedor desta empresa já utiliza este CPF/CNPJ.'},
    )


@transaction.atomic
def _save_product_supplier(*, instance=None, **values):
    if instance is not None:
        instance = _lock_instance(instance)
        for field, value in values.items():
            setattr(instance, field, value)
    else:
        product = Product.objects.select_for_update().select_related('company').get(
            pk=values['product'].pk
        )
        supplier = Supplier.objects.select_for_update().select_related('company').get(
            pk=values['supplier'].pk
        )
        instance = ProductSupplier(**values)
        instance.product = product
        instance.supplier = supplier
    if instance.status == Status.ACTIVE and instance.is_exclusive:
        instance.is_preferred = True
    return _save_with_validation(
        instance,
        {'non_field_errors': 'A relação conflita com outro fornecedor ativo do produto.'},
    )


@transaction.atomic
def _save_product_supplier_unit(*, instance=None, **values):
    if instance is not None:
        instance = _lock_instance(instance)
        for field, value in values.items():
            setattr(instance, field, value)
    else:
        relation = ProductSupplier.objects.select_for_update().select_related('company').get(
            pk=values['product_supplier'].pk
        )
        instance = ProductSupplierUnit(**values)
        instance.product_supplier = relation
    return _save_with_validation(
        instance,
        {'is_default': 'A relação já possui uma apresentação padrão ativa.'},
    )


def _set_supplier_status(*, instance, status):
    return _save_supplier(instance=instance, status=status)


def _set_product_supplier_status(*, instance, status):
    return _save_product_supplier(instance=instance, status=status)


def _set_product_supplier_unit_status(*, instance, status):
    return _save_product_supplier_unit(instance=instance, status=status)
