from django.db import migrations


PERMISSIONS = (
    ('tables.add_items', 'Lançar pedidos de mesa', 'Salvar e confirmar pedidos em mesas abertas.'),
    ('tables.cancel_items', 'Cancelar itens de mesa', 'Cancelar itens confirmados ou pendentes de mesas.'),
    ('tables.payments.view', 'Ver pagamentos de mesa', 'Consultar pagamentos parciais de mesas.'),
    ('tables.payments.record', 'Registrar pagamento de mesa', 'Registrar pagamentos parciais em mesas abertas.'),
    ('tables.payments.reverse', 'Estornar pagamento de mesa', 'Estornar pagamentos parciais de mesas.'),
)


def add_table_operation_permissions(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permissions = []
    for code, label, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={'module': 'tables', 'scope': 'BRANCH', 'label': label, 'description': description, 'status': 'active'},
        )
        permissions.append(permission)
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('companies', '0051_table_manage_permission')]
    operations = [migrations.RunPython(add_table_operation_permissions, migrations.RunPython.noop)]
