import django.db.models.deletion
import django.db.models.functions.text

from django.db import migrations, models


def migrate_operational_scope(apps, schema_editor):
    Branch = apps.get_model('companies', 'Branch')
    Category = apps.get_model('products', 'Category')
    Product = apps.get_model('products', 'Product')
    ProductBranchConfig = apps.get_model('products', 'ProductBranchConfig')
    ModifierGroup = apps.get_model('products', 'ModifierGroup')
    ModifierOption = apps.get_model('products', 'ModifierOption')
    ProductModifierGroup = apps.get_model('products', 'ProductModifierGroup')

    category_by_branch = {}
    for category in list(Category.objects.order_by('pk')):
        branches = list(Branch.objects.filter(company_id=category.company_id).order_by('pk'))
        for index, branch in enumerate(branches):
            if index == 0:
                Category.objects.filter(pk=category.pk).update(branch_id=branch.pk)
                category_by_branch[(category.pk, branch.pk)] = category.pk
                continue
            clone = Category.objects.create(
                company_id=category.company_id,
                branch_id=branch.pk,
                name=category.name,
                description=category.description,
                sort_order=category.sort_order,
                available_counter=category.available_counter,
                available_table=category.available_table,
                available_command=category.available_command,
                participates_in_service_fee=category.participates_in_service_fee,
                participates_in_commission=category.participates_in_commission,
                status=category.status,
            )
            category_by_branch[(category.pk, branch.pk)] = clone.pk

    for product in Product.objects.order_by('pk').iterator():
        for branch in Branch.objects.filter(company_id=product.company_id).order_by('pk'):
            config, _created = ProductBranchConfig.objects.get_or_create(
                product_id=product.pk,
                branch_id=branch.pk,
                defaults={'is_available': True},
            )
            category_id = category_by_branch.get((product.category_id, branch.pk))
            if category_id and config.category_id != category_id:
                ProductBranchConfig.objects.filter(pk=config.pk).update(category_id=category_id)

    group_by_branch = {}
    source_groups = list(ModifierGroup.objects.order_by('pk'))
    for group in source_groups:
        branches = list(Branch.objects.filter(company_id=group.company_id).order_by('pk'))
        for index, branch in enumerate(branches):
            if index == 0:
                ModifierGroup.objects.filter(pk=group.pk).update(branch_id=branch.pk)
                group_by_branch[(group.pk, branch.pk)] = group.pk
                continue
            clone = ModifierGroup.objects.create(
                company_id=group.company_id,
                branch_id=branch.pk,
                name=group.name,
                is_required=group.is_required,
                min_selections=group.min_selections,
                max_selections=group.max_selections,
                allow_option_quantity=group.allow_option_quantity,
                substitution_component_id=group.substitution_component_id,
                inherit_component_quantity=group.inherit_component_quantity,
                sort_order=group.sort_order,
                status=group.status,
                deleted_at=group.deleted_at,
                deleted_by_id=group.deleted_by_id,
            )
            group_by_branch[(group.pk, branch.pk)] = clone.pk

    source_options = list(ModifierOption.objects.order_by('pk'))
    for option in source_options:
        source_group_id = option.modifier_group_id
        source_group = next(group for group in source_groups if group.pk == source_group_id)
        for branch in Branch.objects.filter(company_id=source_group.company_id).order_by('pk'):
            target_group_id = group_by_branch[(source_group_id, branch.pk)]
            if target_group_id == source_group_id:
                continue
            ModifierOption.objects.create(
                modifier_group_id=target_group_id,
                name=option.name,
                option_type=option.option_type,
                additional_price=option.additional_price,
                stock_product_id=option.stock_product_id,
                sort_order=option.sort_order,
                status=option.status,
                deleted_at=option.deleted_at,
                deleted_by_id=option.deleted_by_id,
            )

    source_links = list(ProductModifierGroup.objects.order_by('pk'))
    source_group_company = {group.pk: group.company_id for group in source_groups}
    for link in source_links:
        for branch in Branch.objects.filter(
            company_id=source_group_company[link.modifier_group_id]
        ).order_by('pk'):
            target_group_id = group_by_branch[(link.modifier_group_id, branch.pk)]
            if target_group_id == link.modifier_group_id:
                continue
            ProductModifierGroup.objects.create(
                product_id=link.product_id,
                modifier_group_id=target_group_id,
                sort_order=link.sort_order,
                status=link.status,
                deleted_at=link.deleted_at,
                deleted_by_id=link.deleted_by_id,
            )


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('companies', '0042_branchsettings_table_range'),
        ('products', '0014_modifier_soft_delete'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='branch',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='product_categories',
                to='companies.branch',
            ),
        ),
        migrations.AddField(
            model_name='productbranchconfig',
            name='category',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='branch_product_configs',
                to='products.category',
            ),
        ),
        migrations.AddField(
            model_name='modifiergroup',
            name='branch',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='modifier_groups',
                to='companies.branch',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='category',
            name='products_category_company_name_ci_unique',
        ),
        migrations.RemoveConstraint(
            model_name='modifiergroup',
            name='products_modifier_group_company_name_ci_unique',
        ),
        migrations.AddConstraint(
            model_name='category',
            constraint=models.UniqueConstraint(
                models.F('branch'),
                django.db.models.functions.text.Lower('name'),
                name='products_category_branch_name_ci_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='modifiergroup',
            constraint=models.UniqueConstraint(
                models.F('branch'),
                django.db.models.functions.text.Lower('name'),
                condition=models.Q(('deleted_at__isnull', True)),
                name='products_modifier_group_branch_name_ci_unique',
            ),
        ),
        migrations.RunPython(migrate_operational_scope, migrations.RunPython.noop),
    ]
