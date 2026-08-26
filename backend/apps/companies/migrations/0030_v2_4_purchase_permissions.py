from django.db import migrations


PERMISSIONS = (
    ('purchases.view', 'Visualizar compras', 'Visualizar pedidos, entradas e recebimentos da filial.'),
    ('purchases.create', 'Criar compras', 'Criar e editar compras em rascunho.'),
    ('purchases.place', 'Realizar pedidos', 'Confirmar pedidos de compra planejados.'),
    ('purchases.receive', 'Receber mercadorias', 'Confirmar recebimentos de compras e entradas diretas.'),
    ('purchases.close', 'Cancelar ou encerrar compras', 'Cancelar compras sem recebimento ou encerrar pendencias parciais.'),
    ('purchases.view_costs', 'Visualizar custos de compras', 'Visualizar precos, rateios e custos efetivos das compras.'),
    ('purchases.manage_payables', 'Administrar contas a pagar de compras', 'Definir parcelas e registrar pagamento ou cancelamento manual.'),
)


def add_purchase_permissions(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    Profile = apps.get_model('companies', 'AccessProfile')
    permissions = []
    for code, label, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={
                'module': 'purchases',
                'label': label,
                'description': description,
                'status': 'active',
            },
        )
        permissions.append(permission)
    for profile in Profile.objects.filter(is_system=True, name='Administrador'):
        profile.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('companies', '0029_v2_3_supplier_permissions')]
    operations = [
        migrations.RunPython(add_purchase_permissions, migrations.RunPython.noop),
    ]
