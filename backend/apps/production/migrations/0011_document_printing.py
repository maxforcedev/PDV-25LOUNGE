from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.expressions


def migrate_legacy_receipt_preferences(apps, schema_editor):
    PrintRoute = apps.get_model('production', 'PrintRoute')
    PrintRouteOverride = apps.get_model('production', 'PrintRouteOverride')
    PrinterDevice = apps.get_model('production', 'PrinterDevice')
    Branch = apps.get_model('companies', 'Branch')
    BranchPOSSettings = apps.get_model('pos', 'BranchPOSSettings')
    POSDeviceSettings = apps.get_model('pos', 'POSDeviceSettings')

    def mode(enabled, configured_mode):
        if not enabled:
            return 'disabled'
        return 'automatic' if configured_mode == 'automatic' else 'manual'

    for legacy in BranchPOSSettings.objects.all():
        route, created = PrintRoute.objects.get_or_create(
            branch_id=legacy.branch_id,
            document_type='quick_sale_receipt',
            defaults={
                'mode': mode(legacy.sale_confirmation_print, legacy.receipt_print_mode),
                'copies': legacy.copies or 1,
                'document_format': legacy.receipt_format or '',
            },
        )
        # A route created by the initial defaults must not mask the legacy receipt
        # configuration when this migration is applied to an existing branch.
        if not created and (
            route.mode == 'disabled'
            and route.copies == 1
            and not route.document_format
            and not route.printer_devices.exists()
        ):
            route.mode = mode(legacy.sale_confirmation_print, legacy.receipt_print_mode)
            route.copies = legacy.copies or 1
            route.document_format = legacy.receipt_format or ''
            route.save(update_fields=('mode', 'copies', 'document_format', 'updated_at'))
        if legacy.receipt_printer and legacy.receipt_printer != 'none':
            printer = PrinterDevice.objects.filter(
                branch_id=legacy.branch_id, name__iexact=legacy.receipt_printer,
            ).first()
            if printer:
                route.printer_devices.add(printer)

    for legacy in POSDeviceSettings.objects.select_related('device'):
        has_override = any((
            legacy.receipt_printer,
            legacy.sale_confirmation_print is not None,
            legacy.receipt_print_mode,
            legacy.receipt_format,
            legacy.copies,
        ))
        if not has_override:
            continue
        override, _ = PrintRouteOverride.objects.get_or_create(
            pos_device_id=legacy.device_id,
            document_type='quick_sale_receipt',
            defaults={
                'inherit_branch': False,
                'mode': mode(bool(legacy.sale_confirmation_print), legacy.receipt_print_mode),
                'copies': legacy.copies or 1,
                'document_format': legacy.receipt_format or '',
            },
        )
        if legacy.receipt_printer and legacy.receipt_printer != 'none':
            printer = PrinterDevice.objects.filter(
                branch_id=legacy.device.branch_id, name__iexact=legacy.receipt_printer,
            ).first()
            if printer:
                override.printer_devices.add(printer)

    for branch in Branch.objects.all():
        for document_type in (
            'table_bill', 'table_conference', 'table_final_receipt',
            'quick_sale_receipt', 'payment_receipt', 'ticket',
        ):
            PrintRoute.objects.get_or_create(
                branch_id=branch.pk, document_type=document_type,
                defaults={'mode': 'disabled', 'copies': 1},
            )


class Migration(migrations.Migration):
    dependencies = [
        ('production', '0010_print_job_physical_dispatch_started'),
        ('pos', '0005_posdevice_active_cash_session'),
    ]

    operations = [
        migrations.AlterField(
            model_name='printerdevice',
            name='connection_type',
            field=models.CharField(choices=[('network', 'Network'), ('stone_integrated', 'Stone integrada'), ('usb', 'USB'), ('bluetooth', 'Bluetooth')], default='network', max_length=18),
        ),
        migrations.CreateModel(
            name='PrintDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('document_type', models.CharField(choices=[('table_bill', 'Conta da mesa'), ('table_conference', 'Conferência da mesa'), ('table_final_receipt', 'Recibo final da mesa'), ('quick_sale_receipt', 'Recibo de venda rápida'), ('payment_receipt', 'Comprovante de pagamento'), ('ticket', 'Ticket'), ('report', 'Relatório'), ('fiscal_receipt', 'Recibo fiscal'), ('label', 'Etiqueta'), ('delivery_order', 'Pedido de entrega'), ('cash_closing', 'Fechamento de caixa'), ('cash_opening', 'Abertura de caixa')], max_length=32)),
                ('source_type', models.CharField(max_length=40)),
                ('source_id', models.CharField(max_length=64)),
                ('snapshot', models.JSONField(default=dict)),
                ('snapshot_hash', models.CharField(editable=False, max_length=64)),
                ('version', models.PositiveIntegerField(default=1, editable=False)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='print_documents', to='companies.branch')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='print_documents', to='companies.company')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='created_print_documents', to=settings.AUTH_USER_MODEL)),
                ('original_document', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='derived_documents', to='production.printdocument')),
            ],
            options={'ordering': ('-created_at', '-id')},
        ),
        migrations.CreateModel(
            name='PrintRoute',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('document_type', models.CharField(choices=[('table_bill', 'Conta da mesa'), ('table_conference', 'Conferência da mesa'), ('table_final_receipt', 'Recibo final da mesa'), ('quick_sale_receipt', 'Recibo de venda rápida'), ('payment_receipt', 'Comprovante de pagamento'), ('ticket', 'Ticket'), ('report', 'Relatório'), ('fiscal_receipt', 'Recibo fiscal'), ('label', 'Etiqueta'), ('delivery_order', 'Pedido de entrega'), ('cash_closing', 'Fechamento de caixa'), ('cash_opening', 'Abertura de caixa')], max_length=32)),
                ('mode', models.CharField(choices=[('disabled', 'Desabilitado'), ('manual', 'Manual'), ('automatic', 'Automático')], default='disabled', max_length=12)),
                ('copies', models.PositiveSmallIntegerField(default=1)),
                ('document_format', models.CharField(blank=True, default='', max_length=30)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='print_routes', to='companies.branch')),
                ('printer_devices', models.ManyToManyField(blank=True, related_name='print_routes', to='production.printerdevice')),
            ],
            options={'ordering': ('document_type', 'id')},
        ),
        migrations.CreateModel(
            name='PrintRouteOverride',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('document_type', models.CharField(choices=[('table_bill', 'Conta da mesa'), ('table_conference', 'Conferência da mesa'), ('table_final_receipt', 'Recibo final da mesa'), ('quick_sale_receipt', 'Recibo de venda rápida'), ('payment_receipt', 'Comprovante de pagamento'), ('ticket', 'Ticket'), ('report', 'Relatório'), ('fiscal_receipt', 'Recibo fiscal'), ('label', 'Etiqueta'), ('delivery_order', 'Pedido de entrega'), ('cash_closing', 'Fechamento de caixa'), ('cash_opening', 'Abertura de caixa')], max_length=32)),
                ('inherit_branch', models.BooleanField(default=True)),
                ('mode', models.CharField(choices=[('disabled', 'Desabilitado'), ('manual', 'Manual'), ('automatic', 'Automático')], default='disabled', max_length=12)),
                ('copies', models.PositiveSmallIntegerField(default=1)),
                ('document_format', models.CharField(blank=True, default='', max_length=30)),
                ('pos_device', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='print_route_overrides', to='pos.posdevice')),
                ('printer_devices', models.ManyToManyField(blank=True, related_name='print_route_overrides', to='production.printerdevice')),
            ],
            options={'ordering': ('document_type', 'id')},
        ),
        migrations.AddField(model_name='printjob', name='print_document', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='print_jobs', to='production.printdocument')),
        migrations.AlterField(model_name='printjob', name='destination', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='print_jobs', to='products.productiondestination')),
        migrations.AddConstraint(model_name='printdocument', constraint=models.UniqueConstraint(fields=('branch', 'document_type', 'source_type', 'source_id', 'snapshot_hash'), name='print_document_source_snapshot_unique')),
        migrations.AddConstraint(model_name='printdocument', constraint=models.CheckConstraint(condition=models.Q(('version__gte', 1)), name='print_document_version_positive')),
        migrations.AddConstraint(model_name='printroute', constraint=models.UniqueConstraint(fields=('branch', 'document_type'), name='print_route_branch_document_type_unique')),
        migrations.AddConstraint(model_name='printroute', constraint=models.CheckConstraint(condition=models.Q(('copies__gte', 1)), name='print_route_copies_positive')),
        migrations.AddConstraint(model_name='printrouteoverride', constraint=models.UniqueConstraint(fields=('pos_device', 'document_type'), name='print_route_override_device_document_type_unique')),
        migrations.AddConstraint(model_name='printrouteoverride', constraint=models.CheckConstraint(condition=models.Q(('copies__gte', 1)), name='print_route_override_copies_positive')),
        migrations.AddConstraint(
            model_name='printjob',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(('destination__isnull', False), ('is_test', False), ('print_document__isnull', True), ('production_job__isnull', False))
                    | models.Q(('destination__isnull', True), ('is_test', False), ('print_document__isnull', False), ('production_job__isnull', True))
                    | models.Q(('is_test', True), ('print_document__isnull', True), ('production_job__isnull', True))
                ),
                name='print_job_exactly_one_valid_origin',
            ),
        ),
        migrations.RunPython(migrate_legacy_receipt_preferences, migrations.RunPython.noop),
    ]
