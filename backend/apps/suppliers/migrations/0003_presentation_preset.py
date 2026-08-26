from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0035_functional_permission_scopes_and_branch_prices'),
        ('suppliers', '0002_supplier_legal_name_optional'),
    ]

    operations = [
        migrations.CreateModel(
            name='PresentationPreset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('presentation_type', models.CharField(choices=[('UN', 'Unidade'), ('CX', 'Caixa'), ('FD', 'Fardo'), ('PK', 'Pack'), ('PCT', 'Pacote'), ('ENG', 'Engradado'), ('DSP', 'Display'), ('BDJ', 'Bandeja'), ('SC', 'Saco'), ('KIT', 'Kit'), ('OTHER', 'Outro')], max_length=5)),
                ('conversion_factor', models.DecimalField(decimal_places=6, max_digits=18)),
                ('code', models.CharField(max_length=20)),
                ('description', models.CharField(max_length=200)),
                ('custom_code', models.CharField(blank=True, max_length=20)),
                ('custom_name', models.CharField(blank=True, max_length=100)),
                ('status', models.CharField(choices=[('active', 'Ativo'), ('inactive', 'Inativo')], default='active', max_length=10)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='presentation_presets', to='companies.company')),
            ],
            options={'ordering': ('code', 'description', 'id')},
        ),
        migrations.AddField(
            model_name='productsupplierunit',
            name='presentation_preset',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='product_supplier_units', to='suppliers.presentationpreset'),
        ),
        migrations.AddConstraint(
            model_name='presentationpreset',
            constraint=models.CheckConstraint(condition=models.Q(('conversion_factor__gt', 0)), name='suppliers_preset_conversion_factor_positive'),
        ),
        migrations.AddConstraint(
            model_name='presentationpreset',
            constraint=models.UniqueConstraint(fields=('company', 'presentation_type', 'conversion_factor', 'custom_code', 'custom_name'), name='suppliers_preset_company_semantic_unique'),
        ),
    ]
