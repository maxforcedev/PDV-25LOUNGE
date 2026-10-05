from django.db import migrations


def deactivate_legacy_permission(apps, schema_editor):
    FunctionalPermission = apps.get_model('companies', 'FunctionalPermission')
    FunctionalPermission.objects.filter(code='commands.transfer').update(status='inactive')


class Migration(migrations.Migration):
    dependencies = [('companies', '0056_document_printing_permissions')]

    operations = [
        migrations.RunPython(deactivate_legacy_permission, migrations.RunPython.noop),
    ]
