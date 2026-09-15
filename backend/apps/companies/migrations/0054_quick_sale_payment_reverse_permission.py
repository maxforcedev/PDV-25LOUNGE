from django.db import migrations


def add_quick_sale_payment_reverse_permission(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permission, _ = Permission.objects.update_or_create(
        code='sales.payments.reverse',
        defaults={
            'module': 'sales', 'scope': 'BRANCH',
            'label': 'Estornar pagamento de venda rápida',
            'description': 'Estornar um pagamento de checkout de venda rápida aberto.',
            'status': 'active',
        },
    )
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [('companies', '0053_table_set_customer_permission')]
    operations = [migrations.RunPython(add_quick_sale_payment_reverse_permission, migrations.RunPython.noop)]
