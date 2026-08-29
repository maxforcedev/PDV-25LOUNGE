import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('commands', '0004_command_payment'),
        ('companies', '0038_command_payment_permissions'),
        ('products', '0010_category_configuration_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrinterDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('device_type', models.CharField(choices=[('manual', 'Manual'), ('development', 'Development')], default='manual', max_length=20)),
                ('status', models.CharField(choices=[('active', 'Ativo'), ('inactive', 'Inativo')], default='active', max_length=10)),
                ('technical_configuration', models.JSONField(blank=True, default=dict)),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='printer_devices', to='companies.branch')),
                ('destinations', models.ManyToManyField(blank=True, related_name='printer_devices', to='products.productiondestination')),
            ],
            options={'ordering': ('name', 'id')},
        ),
        migrations.CreateModel(
            name='ProductionJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('event', models.CharField(choices=[('new', 'Novo'), ('cancel', 'Cancelamento')], max_length=10)),
                ('payload_snapshot', models.JSONField(default=dict)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='production_jobs', to='companies.branch')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='production_jobs', to='companies.company')),
                ('destination', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='production_jobs', to='products.productiondestination')),
                ('order_item', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='production_jobs', to='commands.orderitem')),
                ('original_job', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='cancellation_jobs', to='production.productionjob')),
            ],
            options={'ordering': ('id',)},
        ),
        migrations.CreateModel(
            name='PrintJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('payload_snapshot', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('pending', 'Pendente'), ('processing', 'Processando'), ('printed', 'Impresso'), ('failed', 'Falhou'), ('cancelled', 'Cancelado')], default='pending', max_length=12)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('last_error', models.TextField(blank=True, default='')),
                ('idempotency_key', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('processing_at', models.DateTimeField(blank=True, null=True)),
                ('printed_at', models.DateTimeField(blank=True, null=True)),
                ('reprint_number', models.PositiveIntegerField(default=0)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='print_jobs', to='companies.branch')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='print_jobs', to='companies.company')),
                ('destination', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='print_jobs', to='products.productiondestination')),
                ('printer_device', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='print_jobs', to='production.printerdevice')),
                ('production_job', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='print_jobs', to='production.productionjob')),
                ('reprint_of', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reprints', to='production.printjob')),
            ],
            options={'ordering': ('id',)},
        ),
        migrations.AddConstraint(model_name='printerdevice', constraint=models.UniqueConstraint(fields=('branch', 'name'), name='production_printer_branch_name_unique')),
        migrations.AddConstraint(model_name='productionjob', constraint=models.UniqueConstraint(fields=('order_item', 'destination', 'event'), name='production_job_item_destination_event_unique')),
        migrations.AddConstraint(model_name='printjob', constraint=models.UniqueConstraint(fields=('production_job', 'printer_device', 'idempotency_key'), name='production_print_job_idempotency_unique')),
    ]
