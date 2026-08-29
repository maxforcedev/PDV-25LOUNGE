from django.db import migrations, models
import django.db.models.deletion


def backfill_presentations(apps, schema_editor):
    Unit = apps.get_model('suppliers', 'ProductSupplierUnit')
    Presentation = apps.get_model('suppliers', 'ProductPurchasePresentation')
    for unit in Unit.objects.select_related('product_supplier').all():
        presentation, _created = Presentation.objects.get_or_create(
            company_id=unit.company_id,
            product_id=unit.product_supplier.product_id,
            unit_code=unit.unit_code,
            conversion_factor=unit.conversion_factor,
            defaults={'description': unit.description, 'status': unit.status},
        )
        Unit.objects.filter(pk=unit.pk).update(purchase_presentation_id=presentation.pk)


class Migration(migrations.Migration):
    dependencies = [('suppliers', '0003_presentation_preset')]
    operations = [
        migrations.CreateModel(
            name='ProductPurchasePresentation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
                ('unit_code', models.CharField(max_length=20)), ('description', models.CharField(max_length=200)),
                ('conversion_factor', models.DecimalField(decimal_places=6, max_digits=18)),
                ('status', models.CharField(choices=[('active', 'Ativo'), ('inactive', 'Inativo')], default='active', max_length=10)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='product_purchase_presentations', to='companies.company')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='purchase_presentations', to='products.product')),
            ], options={'ordering': ('product_id', 'unit_code', 'id')},
        ),
        migrations.AddField(model_name='productsupplierunit', name='purchase_presentation', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='supplier_links', to='suppliers.productpurchasepresentation')),
        migrations.AddConstraint(model_name='productpurchasepresentation', constraint=models.CheckConstraint(condition=models.Q(('conversion_factor__gt', 0)), name='suppliers_product_presentation_factor_positive')),
        migrations.AddConstraint(model_name='productpurchasepresentation', constraint=models.UniqueConstraint(fields=('product', 'unit_code', 'conversion_factor'), name='suppliers_product_presentation_unique')),
        migrations.RunPython(backfill_presentations, migrations.RunPython.noop),
    ]
