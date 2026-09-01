import django.db.models.deletion

from django.db import migrations, models


def backfill_supplier_branches(apps, schema_editor):
    Branch = apps.get_model('companies', 'Branch')
    Supplier = apps.get_model('suppliers', 'Supplier')
    SupplierBranch = apps.get_model('suppliers', 'SupplierBranch')

    configs = []
    for supplier in Supplier.objects.order_by('pk').iterator():
        configs.extend(
            SupplierBranch(supplier_id=supplier.pk, branch_id=branch_id, is_available=True)
            for branch_id in Branch.objects.filter(
                company_id=supplier.company_id
            ).values_list('pk', flat=True)
        )
    SupplierBranch.objects.bulk_create(configs, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0042_branchsettings_table_range'),
        ('suppliers', '0004_product_purchase_presentation'),
    ]

    operations = [
        migrations.CreateModel(
            name='SupplierBranch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_available', models.BooleanField(default=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='supplier_configs', to='companies.branch')),
                ('supplier', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branch_configs', to='suppliers.supplier')),
            ],
            options={'ordering': ('branch__name', 'supplier__trade_name')},
        ),
        migrations.AddConstraint(
            model_name='supplierbranch',
            constraint=models.UniqueConstraint(
                fields=('supplier', 'branch'),
                name='suppliers_branch_supplier_branch_unique',
            ),
        ),
        migrations.RunPython(backfill_supplier_branches, migrations.RunPython.noop),
    ]
