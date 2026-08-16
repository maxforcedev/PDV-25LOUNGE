from django.db import migrations


PERMISSIONS = (
    ('reports.view_sales', 'reports', 'Visualizar relatorio de vendas', 'Visualizar relatorio operacional de vendas.'),
    ('reports.view_consumptions', 'reports', 'Visualizar relatorio de consumacoes', 'Visualizar relatorio operacional de consumacoes.'),
    ('reports.view_cash', 'reports', 'Visualizar relatorio de caixa', 'Visualizar relatorio operacional de caixa.'),
    ('reports.view_withdrawals', 'reports', 'Visualizar relatorio de sangrias', 'Visualizar relatorio operacional de sangrias.'),
    ('reports.view_inventory', 'reports', 'Visualizar relatorio de estoque', 'Visualizar relatorio de movimentacoes de estoque.'),
    ('reports.export', 'reports', 'Exportar relatorios', 'Exportar relatorios operacionais.'),
)


def add_report_permissions(apps, schema_editor):
    FunctionalPermission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permissions = {}
    for code, module, label, description in PERMISSIONS:
        permission, _ = FunctionalPermission.objects.update_or_create(
            code=code,
            defaults={
                'module': module,
                'label': label,
                'description': description,
                'status': 'active',
            },
        )
        permissions[code] = permission

    for profile in AccessProfile.objects.filter(
        is_system=True, name__in=('Administrador', 'Gerente')
    ).iterator():
        profile.permissions.add(*permissions.values())
    for profile in AccessProfile.objects.filter(
        is_system=True, name='Operador de Estoque'
    ).iterator():
        profile.permissions.add(permissions['reports.view_inventory'])
    for profile in AccessProfile.objects.filter(
        is_system=True, name='Operador de Caixa'
    ).iterator():
        profile.permissions.add(
            permissions['reports.view_sales'],
            permissions['reports.view_consumptions'],
            permissions['reports.view_cash'],
            permissions['reports.view_withdrawals'],
        )


class Migration(migrations.Migration):
    dependencies = [('companies', '0013_sync_administrator_permissions')]

    operations = [
        migrations.RunPython(add_report_permissions, migrations.RunPython.noop),
    ]
