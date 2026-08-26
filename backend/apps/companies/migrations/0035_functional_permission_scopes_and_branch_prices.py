from django.db import migrations, models


BRANCH_PERMISSION_CODES = {
    'products.view', 'products.add', 'products.change', 'products.change_status',
    'products.configure_composition', 'products.change_cost', 'products.change_price',
    'products.configure_branch', 'products.configure_fraction',
    'products.configure_destinations', 'products.duplicate',
    'categories.view', 'categories.add', 'categories.change', 'categories.change_status',
    'branch_prices.view', 'branch_prices.change',
    'suppliers.view', 'suppliers.change', 'modifiers.view', 'modifiers.change',
    'purchases.view', 'purchases.create', 'purchases.place', 'purchases.receive',
    'purchases.close', 'purchases.view_costs', 'purchases.manage_payables',
    'inventory.view', 'inventory.move', 'inventory.entry', 'inventory.exit',
    'inventory.adjust', 'inventory.regularize', 'inventory.change_minimum',
    'inventory.view_history', 'inventory.view_stock_kpis', 'inventory.view_stock_costs',
    'inventory.transfer.view', 'inventory.transfer.create',
    'inventory.transfer.dispatch', 'inventory.transfer.receive',
    'inventory.transfer.resolve', 'inventory.loss.record', 'inventory.count.perform',
    'inventory.report.view',
    'cash_registers.view', 'cash_registers.open', 'cash_registers.manual_entry',
    'cash_registers.withdraw', 'cash_registers.close', 'cash_registers.add',
    'cash_registers.change', 'cash_registers.change_status',
    'cash_registers.administer_others',
    'sales.create', 'sales.view', 'sales.cancel', 'sales.apply_discount',
    'sales.apply_item_discount', 'sales.waive_service_fee', 'sales.create_consumption',
    'sales.view_consumption', 'sales.cancel_consumption',
    'commands.view', 'commands.open', 'commands.add_items', 'commands.cancel_items',
    'commands.finalize', 'payment_methods.view', 'payment_methods.change',
    'promotions.view', 'promotions.change', 'dashboard.view',
    'reports.view_sales', 'reports.view_consumptions', 'reports.view_cash',
    'reports.view_withdrawals', 'reports.view_inventory',
    'reports.view_operational_result', 'reports.view_stock_consumption',
    'reports.view_products', 'reports.view_receipts', 'reports.view_team',
    'reports.view_discounts', 'reports.view_cancellations', 'reports.view_prices',
    'reports.export', 'audit_logs.view', 'commissions.view',
    'commissions.change_branch_default', 'commissions.change_user_override',
}


BRANCH_PRICE_PERMISSIONS = (
    ('branch_prices.view', 'products', 'Visualizar preços por filial',
     'Visualizar preços da filial atual.', 'BRANCH'),
    ('branch_prices.view_company', 'products', 'Comparar preços da empresa',
     'Visualizar e comparar preços das filiais da empresa.', 'COMPANY'),
    ('branch_prices.change_company', 'products', 'Alterar preços da empresa',
     'Alterar preços de qualquer filial da empresa.', 'COMPANY'),
)


def populate_scopes_and_branch_prices(apps, schema_editor):
    FunctionalPermission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')

    FunctionalPermission.objects.filter(code__in=BRANCH_PERMISSION_CODES).update(scope='BRANCH')
    FunctionalPermission.objects.exclude(code__in=BRANCH_PERMISSION_CODES).update(scope='COMPANY')
    permissions = {}
    for code, module, label, description, scope in BRANCH_PRICE_PERMISSIONS:
        permission, _ = FunctionalPermission.objects.update_or_create(
            code=code,
            defaults={
                'module': module,
                'label': label,
                'description': description,
                'scope': scope,
                'status': 'active',
            },
        )
        permissions[code] = permission

    view_permission = permissions['branch_prices.view']
    for profile in AccessProfile.objects.filter(
        permissions__code='branch_prices.change'
    ).distinct():
        profile.permissions.add(view_permission)
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(
            permissions['branch_prices.view_company'],
            permissions['branch_prices.change_company'],
        )


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0034_v2_10_ensure_owner_branch_access'),
    ]

    operations = [
        migrations.AddField(
            model_name='functionalpermission',
            name='scope',
            field=models.CharField(
                choices=[('COMPANY', 'Company'), ('BRANCH', 'Branch')],
                default='COMPANY', max_length=10,
            ),
        ),
        migrations.RunPython(populate_scopes_and_branch_prices, migrations.RunPython.noop),
    ]
