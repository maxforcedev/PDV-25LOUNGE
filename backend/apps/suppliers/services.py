from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.companies.models import Company, Status
from apps.products.models import Product

from .models import (
    PresentationPreset, PresentationType, ProductPurchasePresentation, ProductSupplier, ProductSupplierUnit, Supplier,
)


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
    if isinstance(instance, PresentationPreset):
        Company.objects.select_for_update().get(pk=instance.company_id)
        return PresentationPreset.objects.select_for_update().get(pk=instance.pk)
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
    missing = object()
    preset_id = values.pop('presentation_preset', missing)
    presentation_type = values.pop('presentation_type', None)
    custom_code = values.pop('custom_code', '')
    custom_name = values.pop('custom_name', '')
    save_as_preset = values.pop('save_as_preset', False)
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
    if preset_id is not missing and preset_id is not None:
        try:
            preset = PresentationPreset.objects.select_for_update().get(
                pk=getattr(preset_id, 'pk', preset_id), company_id=instance.company_id,
                status=Status.ACTIVE,
            )
        except PresentationPreset.DoesNotExist as error:
            raise ValidationError({'presentation_preset': 'Padrão ativo inválido para esta empresa.'}) from error
        instance.presentation_preset = preset
        instance.unit_code = preset.code
        instance.description = preset.description
        instance.conversion_factor = preset.conversion_factor
    elif presentation_type:
        # A custom presentation replaces a previously linked preset.
        instance.presentation_preset = None
        preset_values = {
            'company': instance.company,
            'presentation_type': presentation_type,
            'conversion_factor': instance.conversion_factor,
            'custom_code': custom_code,
            'custom_name': custom_name,
        }
        candidate = PresentationPreset(**preset_values)
        candidate.custom_code = candidate.custom_code.strip().upper()
        candidate.custom_name = ' '.join(candidate.custom_name.split())
        candidate._populate_generated_fields()
        candidate.full_clean(validate_unique=False)
        instance.unit_code = candidate.code
        instance.description = candidate.description
        if save_as_preset:
            preset, _created = PresentationPreset.objects.get_or_create(
                company=instance.company,
                presentation_type=presentation_type,
                conversion_factor=candidate.conversion_factor,
                custom_code=candidate.custom_code,
                custom_name=candidate.custom_name,
                defaults={
                    'code': candidate.code,
                    'description': candidate.description,
                },
            )
            instance.presentation_preset = preset
    elif preset_id is None:
        # Explicit null detaches the preset while preserving legacy fields.
        instance.presentation_preset = None
    if instance.purchase_presentation_id is None:
        presentation, _created = ProductPurchasePresentation.objects.get_or_create(
            company=instance.company,
            product=instance.product_supplier.product,
            unit_code=instance.unit_code,
            conversion_factor=instance.conversion_factor,
            defaults={'description': instance.description},
        )
        instance.purchase_presentation = presentation
        instance.unit_code = presentation.unit_code
        instance.description = presentation.description
        instance.conversion_factor = presentation.conversion_factor
    else:
        instance.unit_code = instance.purchase_presentation.unit_code
        instance.description = instance.purchase_presentation.description
        instance.conversion_factor = instance.purchase_presentation.conversion_factor
    return _save_with_validation(
        instance,
        {'is_default': 'A relação já possui uma apresentação padrão ativa.'},
    )


@transaction.atomic
def _save_presentation_preset(*, instance=None, **values):
    if instance is not None:
        instance = _lock_instance(instance)
        for field, value in values.items():
            setattr(instance, field, value)
    else:
        Company.objects.select_for_update().get(pk=values['company'].pk)
        instance = PresentationPreset(**values)
    return _save_with_validation(
        instance,
        {'non_field_errors': 'Este padrão de apresentação já existe para a empresa.'},
    )


def _set_supplier_status(*, instance, status):
    return _save_supplier(instance=instance, status=status)


def _set_product_supplier_status(*, instance, status):
    return _save_product_supplier(instance=instance, status=status)


def _set_product_supplier_unit_status(*, instance, status):
    return _save_product_supplier_unit(instance=instance, status=status)


def _set_presentation_preset_status(*, instance, status):
    return _save_presentation_preset(instance=instance, status=status)
