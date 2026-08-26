import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ('companies', '0031_v2_5_inventory_permissions'),
        ('products', '0007_alter_product_inventory_behavior'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='product', name='sku',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='product', name='available_counter',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='product', name='available_table',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='product', name='available_command',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='product', name='participates_in_service_fee',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='product', name='participates_in_commission',
            field=models.BooleanField(default=True),
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.UniqueConstraint(
                models.F('company'), Lower('sku'),
                condition=models.Q(sku__isnull=False) & ~models.Q(sku=''),
                name='products_product_company_sku_ci_unique',
            ),
        ),
        migrations.CreateModel(
            name='ProductBranchConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_available', models.BooleanField(default=True)),
                ('available_counter', models.BooleanField(blank=True, null=True)),
                ('available_table', models.BooleanField(blank=True, null=True)),
                ('available_command', models.BooleanField(blank=True, null=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='product_configs', to='companies.branch')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branch_configs', to='products.product')),
            ],
            options={'ordering': ('branch__name', 'product__name')},
        ),
        migrations.AddConstraint(
            model_name='productbranchconfig',
            constraint=models.UniqueConstraint(
                fields=('product', 'branch'),
                name='products_branch_config_product_branch_unique',
            ),
        ),
        migrations.CreateModel(
            name='FractionableProductConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('package_content', models.DecimalField(decimal_places=9, max_digits=24)),
                ('content_unit', models.CharField(choices=[('ml', 'ML'), ('g', 'G')], max_length=2)),
                ('tracking_active', models.BooleanField(default=False, editable=False)),
                ('activated_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('activated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='activated_fraction_configs', to=settings.AUTH_USER_MODEL)),
                ('product', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='fraction_config', to='products.product')),
            ],
        ),
        migrations.AddConstraint(
            model_name='fractionableproductconfig',
            constraint=models.CheckConstraint(
                condition=models.Q(package_content__gt=0),
                name='products_fraction_package_content_positive',
            ),
        ),
        migrations.CreateModel(
            name='ProductFractionComponent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('content_quantity', models.DecimalField(decimal_places=9, max_digits=24)),
                ('component_product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='used_as_fraction_component', to='products.product')),
                ('parent_product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fraction_components', to='products.product')),
            ],
            options={'ordering': ('component_product__name',)},
        ),
        migrations.AddConstraint(
            model_name='productfractioncomponent',
            constraint=models.UniqueConstraint(fields=('parent_product', 'component_product'), name='products_fraction_component_pair_unique'),
        ),
        migrations.AddConstraint(
            model_name='productfractioncomponent',
            constraint=models.CheckConstraint(condition=models.Q(content_quantity__gt=0), name='products_fraction_component_content_positive'),
        ),
        migrations.AddConstraint(
            model_name='productfractioncomponent',
            constraint=models.CheckConstraint(condition=~models.Q(parent_product=models.F('component_product')), name='products_fraction_component_not_self'),
        ),
        migrations.CreateModel(
            name='ProductionDestination',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('code', models.SlugField(max_length=50)),
                ('status', models.CharField(choices=[('active', 'Ativo'), ('inactive', 'Inativo')], default='active', max_length=10)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='production_destinations', to='companies.branch')),
            ],
            options={'ordering': ('name', 'id')},
        ),
        migrations.AddConstraint(
            model_name='productiondestination',
            constraint=models.UniqueConstraint(models.F('branch'), Lower('name'), name='products_destination_branch_name_ci_unique'),
        ),
        migrations.AddConstraint(
            model_name='productiondestination',
            constraint=models.UniqueConstraint(models.F('branch'), Lower('code'), name='products_destination_branch_code_ci_unique'),
        ),
        migrations.CreateModel(
            name='ProductProductionDestination',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('destination', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='product_links', to='products.productiondestination')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='production_destination_links', to='products.product')),
            ],
            options={'ordering': ('destination__name', 'product__name')},
        ),
        migrations.AddConstraint(
            model_name='productproductiondestination',
            constraint=models.UniqueConstraint(fields=('product', 'destination'), name='products_product_destination_unique'),
        ),
    ]
