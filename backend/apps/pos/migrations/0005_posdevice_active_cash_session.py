from django.db import migrations, models
import django.db.models.deletion


def backfill_fixed_device_cash_context(apps, schema_editor):
    POSDevice = apps.get_model('pos', 'POSDevice')
    BranchPOSSettings = apps.get_model('pos', 'BranchPOSSettings')
    POSDeviceSettings = apps.get_model('pos', 'POSDeviceSettings')
    CashSession = apps.get_model('cash', 'CashSession')
    branch_settings = {
        row.branch_id: row
        for row in BranchPOSSettings.objects.all()
    }
    overrides = {
        row.device_id: row
        for row in POSDeviceSettings.objects.all()
    }
    for device in POSDevice.objects.filter(active_cash_session__isnull=True):
        branch = branch_settings.get(device.branch_id)
        override = overrides.get(device.pk)
        mode = (
            override.cash_binding_mode if override and override.cash_binding_mode
            else getattr(branch, 'cash_binding_mode', 'FLEXIBLE')
        )
        register_id = (
            override.default_cash_register_id
            if override and override.default_cash_register_id
            else getattr(branch, 'default_cash_register_id', None)
        )
        if mode != 'FIXED' or not register_id:
            continue
        session = CashSession.objects.filter(
            branch_id=device.branch_id,
            cash_register_id=register_id,
            status='open',
        ).order_by('pk').first()
        if session:
            device.active_cash_session_id = session.pk
            device.save(update_fields=('active_cash_session',))


class Migration(migrations.Migration):
    dependencies = [
        ('cash', '0009_remove_legacy_withdrawal_effect_constraint'),
        ('pos', '0004_quick_checkout_operator_idempotency'),
    ]

    operations = [
        migrations.AddField(
            model_name='posdevice',
            name='active_cash_session',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='active_on_pos_devices',
                to='cash.cashsession',
            ),
        ),
        migrations.RunPython(backfill_fixed_device_cash_context, migrations.RunPython.noop),
    ]
