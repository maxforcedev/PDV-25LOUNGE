import decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('companies', '0007_require_access_profile_remove_role'),
        ('products', '0001_initial'),
    ]
    operations = [
        migrations.CreateModel(
            name='Stock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('current_quantity', models.DecimalField(decimal_places=3, default=decimal.Decimal('0'), max_digits=14)),
                ('minimum_quantity', models.DecimalField(decimal_places=3, default=decimal.Decimal('0'), max_digits=14)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stocks', to='companies.branch')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stocks', to='products.product')),
            ],
            options={
                'ordering': ('product__name', 'branch__name'),
                'constraints': [
                    models.UniqueConstraint(fields=('product', 'branch'), name='inventory_stock_product_branch_unique'),
                    models.CheckConstraint(condition=models.Q(('current_quantity__gte', 0)), name='inventory_stock_current_nonnegative'),
                    models.CheckConstraint(condition=models.Q(('minimum_quantity__gte', 0)), name='inventory_stock_minimum_nonnegative'),
                ],
            },
        ),
        migrations.CreateModel(
            name='StockMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('movement_type', models.CharField(choices=[('entry', 'Entrada'), ('exit', 'Saida'), ('adjustment', 'Ajuste')], max_length=12)),
                ('previous_quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('final_quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('reason', models.TextField()),
                ('stock', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='movements', to='inventory.stock')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at', '-pk'),
                'constraints': [
                    models.CheckConstraint(condition=models.Q(('previous_quantity__gte', 0)), name='inventory_movement_previous_nonnegative'),
                    models.CheckConstraint(condition=models.Q(('final_quantity__gte', 0)), name='inventory_movement_final_nonnegative'),
                    models.CheckConstraint(condition=models.Q(('quantity', 0), _negated=True), name='inventory_movement_quantity_nonzero'),
                    models.CheckConstraint(condition=models.Q(models.Q(('movement_type', 'entry'), ('quantity__gt', 0)), models.Q(('movement_type', 'exit'), ('quantity__lt', 0)), ('movement_type', 'adjustment'), _connector='OR'), name='inventory_movement_quantity_sign'),
                ],
            },
        ),
    ]
