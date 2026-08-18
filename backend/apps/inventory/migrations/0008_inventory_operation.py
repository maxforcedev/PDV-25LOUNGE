from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inventory', '0007_stockmovement_nature_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='InventoryOperation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('idempotency_key', models.UUIDField(editable=False)),
                ('kind', models.CharField(choices=[('manual_entry', 'Entrada manual'), ('manual_exit', 'Saida manual'), ('manual_adjustment', 'Ajuste manual'), ('group_entry', 'Entrada em grupo')], max_length=32)),
                ('payload', models.JSONField(default=dict)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inventory_operations', to='companies.branch')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inventory_operations', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-created_at', '-pk')},
        ),
        migrations.AddConstraint(
            model_name='inventoryoperation',
            constraint=models.UniqueConstraint(fields=('branch', 'idempotency_key'), name='inventory_operation_branch_idempotency_unique'),
        ),
    ]
