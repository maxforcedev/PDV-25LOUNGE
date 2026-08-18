from django.db import migrations


MANAGER_CODES = {
    'companies.view', 'branches.view', 'products.view', 'categories.view',
    'inventory.view', 'inventory.move', 'inventory.entry', 'inventory.exit',
    'inventory.adjust', 'inventory.regularize', 'inventory.change_minimum',
    'inventory.view_history', 'inventory.view_stock_kpis', 'inventory.view_stock_costs',
    'cash_registers.view', 'cash_registers.open', 'cash_registers.manual_entry',
    'cash_registers.withdraw', 'cash_registers.close', 'sales.create', 'sales.view',
    'sales.cancel', 'sales.apply_discount', 'sales.waive_service_fee',
    'sales.create_consumption', 'sales.view_consumption', 'sales.cancel_consumption',
    'payment_methods.view', 'promotions.view', 'dashboard.view', 'reports.view_sales',
    'reports.view_consumptions', 'reports.view_cash', 'reports.view_withdrawals',
    'reports.view_inventory', 'reports.view_operational_result',
    'reports.view_stock_consumption', 'reports.view_products', 'reports.view_receipts',
    'reports.view_team', 'reports.view_discounts', 'reports.view_cancellations',
    'reports.view_prices', 'reports.export', 'commissions.view',
}


def reduce_manager_permissions(apps, schema_editor):
    Profile = apps.get_model('companies', 'AccessProfile')
    Permission = apps.get_model('companies', 'FunctionalPermission')
    manager_permissions = Permission.objects.filter(code__in=MANAGER_CODES, status='active')
    for profile in Profile.objects.filter(is_system=True, name='Gerente'):
        profile.permissions.set(manager_permissions)


class Migration(migrations.Migration):
    dependencies = [('companies', '0021_sprint_12_2_1_rbac_and_address')]
    operations = [migrations.RunPython(reduce_manager_permissions, migrations.RunPython.noop)]
