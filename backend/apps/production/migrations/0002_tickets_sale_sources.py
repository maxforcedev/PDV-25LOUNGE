import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ('production', '0001_initial'),
        ('products', '0011_product_emits_ticket'),
        ('sales', '0017_payment_command_provenance'),
        ('commands', '0006_command_checkout_context'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productionjob', name='order_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='production_jobs', to='commands.orderitem'),
        ),
        migrations.AddField(
            model_name='productionjob', name='sale_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='production_jobs', to='sales.saleitem'),
        ),
        migrations.RemoveConstraint(model_name='productionjob', name='production_job_item_destination_event_unique'),
        migrations.AddConstraint(model_name='productionjob', constraint=models.CheckConstraint(condition=(Q(order_item__isnull=False, sale_item__isnull=True) | Q(order_item__isnull=True, sale_item__isnull=False)), name='production_job_exactly_one_source')),
        migrations.AddConstraint(model_name='productionjob', constraint=models.UniqueConstraint(condition=Q(order_item__isnull=False), fields=('order_item', 'destination', 'event'), name='production_job_order_destination_event_unique')),
        migrations.AddConstraint(model_name='productionjob', constraint=models.UniqueConstraint(condition=Q(sale_item__isnull=False), fields=('sale_item', 'destination', 'event'), name='production_job_sale_destination_event_unique')),
        migrations.AddConstraint(model_name='printjob', constraint=models.UniqueConstraint(condition=Q(reprint_of__isnull=False), fields=('reprint_of', 'reprint_number'), name='production_print_job_reprint_number_unique')),
        migrations.CreateModel(
            name='Ticket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('number', models.PositiveIntegerField()),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('status', models.CharField(choices=[('issued', 'Emitido'), ('used', 'Utilizado'), ('cancelled', 'Cancelado')], default='issued', max_length=10)),
                ('issued_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('reprint_count', models.PositiveIntegerField(default=0)),
                ('identification_snapshot', models.JSONField(default=dict)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tickets', to='companies.branch')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='tickets', to='companies.company')),
                ('source_order_item', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='order_ticket', to='commands.orderitem')),
                ('source_sale_item', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sale_ticket', to='sales.saleitem')),
            ],
            options={'ordering': ('-issued_at', '-id')},
        ),
        migrations.AddConstraint(model_name='ticket', constraint=models.UniqueConstraint(fields=('company', 'branch', 'number'), name='production_ticket_branch_number_unique')),
        migrations.AddConstraint(model_name='ticket', constraint=models.CheckConstraint(condition=Q(quantity__gt=0), name='production_ticket_quantity_positive')),
        migrations.AddConstraint(model_name='ticket', constraint=models.CheckConstraint(condition=(Q(source_sale_item__isnull=False, source_order_item__isnull=True) | Q(source_sale_item__isnull=True, source_order_item__isnull=False)), name='production_ticket_exactly_one_source')),
    ]
