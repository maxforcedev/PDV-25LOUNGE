from django.db import migrations


def sync_administrator_permissions(apps, schema_editor):
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    FunctionalPermission = apps.get_model('companies', 'FunctionalPermission')
    active_permissions = FunctionalPermission.objects.filter(status='active')
    for profile in AccessProfile.objects.filter(
        name='Administrador', is_system=True
    ).iterator():
        profile.permissions.add(*active_permissions)


class Migration(migrations.Migration):
    dependencies = [('companies', '0012_sprint_7_1_permissions')]

    operations = [
        migrations.RunPython(
            sync_administrator_permissions,
            migrations.RunPython.noop,
        ),
    ]
