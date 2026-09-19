from django.db import migrations


MANAGER_CODES = {
    'tables.view', 'tables.open', 'tables.set_customer', 'tables.add_items',
    'tables.cancel_items', 'tables.payments.view', 'tables.payments.record',
    'tables.payments.reverse', 'tables.transfer', 'tables.transfer_items',
    'tables.merge', 'tables.close',
}
CASHIER_CODES = {
    'tables.view', 'tables.open', 'tables.set_customer', 'tables.add_items',
    'tables.payments.view', 'tables.payments.record', 'tables.close',
}


def grant_table_operations(apps, schema_editor):
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    FunctionalPermission = apps.get_model('companies', 'FunctionalPermission')
    for name, codes in (('Gerente', MANAGER_CODES), ('Operador de Caixa', CASHIER_CODES)):
        permissions = FunctionalPermission.objects.filter(code__in=codes)
        for profile in AccessProfile.objects.filter(is_system=True, name=name):
            profile.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('companies', '0054_quick_sale_payment_reverse_permission')]

    operations = [migrations.RunPython(grant_table_operations, migrations.RunPython.noop)]
