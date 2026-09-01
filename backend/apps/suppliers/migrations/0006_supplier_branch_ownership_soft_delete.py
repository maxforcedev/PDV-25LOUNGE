from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_supplier_branches(apps, schema_editor):
    Branch = apps.get_model('companies', 'Branch')
    Supplier = apps.get_model('suppliers', 'Supplier')
    SupplierBranch = apps.get_model('suppliers', 'SupplierBranch')

    for supplier in Supplier.objects.filter(branch_id__isnull=True).order_by('pk').iterator():
        branch_id = SupplierBranch.objects.filter(
            supplier_id=supplier.pk,
            is_available=True,
        ).order_by('branch_id').values_list('branch_id', flat=True).first()
        if branch_id is None:
            branch_id = SupplierBranch.objects.filter(
                supplier_id=supplier.pk,
            ).order_by('branch_id').values_list('branch_id', flat=True).first()
        if branch_id is None:
            branch_id = Branch.objects.filter(
                company_id=supplier.company_id,
            ).order_by('pk').values_list('pk', flat=True).first()
        if branch_id is None:
            raise RuntimeError(
                f'Fornecedor {supplier.pk} não pode ser migrado porque a empresa não possui filial.'
            )
        Supplier.objects.filter(pk=supplier.pk).update(branch_id=branch_id)


class Migration(migrations.Migration):
    dependencies = [
        ('suppliers', '0005_supplier_branch'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='supplier',
            name='branch',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='suppliers',
                to='companies.branch',
            ),
        ),
        migrations.AddField(
            model_name='supplier',
            name='deleted_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='supplier',
            name='deleted_by',
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='deleted_suppliers',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(assign_supplier_branches, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='supplier',
            name='branch',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='suppliers',
                to='companies.branch',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='supplier',
            name='suppliers_supplier_company_tax_id_unique',
        ),
        migrations.AddConstraint(
            model_name='supplier',
            constraint=models.UniqueConstraint(
                condition=models.Q(tax_id__isnull=False, deleted_at__isnull=True),
                fields=('branch', 'tax_id'),
                name='suppliers_supplier_active_branch_tax_id_unique',
            ),
        ),
        migrations.DeleteModel(name='SupplierBranch'),
    ]
