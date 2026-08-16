from django.db import migrations

from apps.companies.rbac import (
    DEFAULT_PROFILE_DESCRIPTIONS,
    DEFAULT_PROFILE_PERMISSIONS,
    PERMISSION_CATALOG,
)

SPRINT_7_1_CODES = {
    'inventory.view_stock_kpis',
    'inventory.view_stock_costs',
    'sales.apply_discount',
    'sales.create_consumption',
    'sales.view_consumption',
    'sales.cancel_consumption',
}
PERMISSION_CATALOG = tuple(
    item for item in PERMISSION_CATALOG if item[0] not in SPRINT_7_1_CODES
)
DEFAULT_PROFILE_PERMISSIONS = {
    name: codes - SPRINT_7_1_CODES
    for name, codes in DEFAULT_PROFILE_PERMISSIONS.items()
}


def populate_access_profiles(apps, schema_editor):
    FunctionalPermission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    Company = apps.get_model('companies', 'Company')
    UserCompanyAccess = apps.get_model('companies', 'UserCompanyAccess')

    permissions = {}
    for code, module, label, description in PERMISSION_CATALOG:
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

    for company in Company.objects.all().iterator():
        profiles = {}
        for name, permission_codes in DEFAULT_PROFILE_PERMISSIONS.items():
            profile, _ = AccessProfile.objects.get_or_create(
                company=company,
                name=name,
                defaults={
                    'description': DEFAULT_PROFILE_DESCRIPTIONS[name],
                    'is_system': True,
                    'status': 'active',
                },
            )
            profile.permissions.set(permissions[code] for code in permission_codes)
            profiles[name] = profile

        UserCompanyAccess.objects.filter(
            company=company,
            role='administrator',
        ).update(access_profile=profiles['Administrador'])
        UserCompanyAccess.objects.filter(
            company=company,
            role='manager',
        ).update(access_profile=profiles['Gerente'])


def restore_roles(apps, schema_editor):
    UserCompanyAccess = apps.get_model('companies', 'UserCompanyAccess')
    UserCompanyAccess.objects.filter(
        access_profile__name='Administrador'
    ).update(role='administrator')
    UserCompanyAccess.objects.exclude(
        access_profile__name='Administrador'
    ).update(role='manager')


class Migration(migrations.Migration):
    dependencies = [('companies', '0005_access_profiles_schema')]

    operations = [
        migrations.RunPython(populate_access_profiles, restore_roles),
    ]
