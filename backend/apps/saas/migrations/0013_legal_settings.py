from django.db import migrations, models


def preserve_existing_site_identity(apps, schema_editor):
    Settings = apps.get_model('saas', 'GlobalSaaSSettings')
    for settings in Settings.objects.using(schema_editor.connection.alias).all():
        values = dict(settings.legal_settings or {})
        values.setdefault('legal_name', 'CAVALINI SOLUÇÕES TECNOLOGICAS')
        values.setdefault('cnpj', '69.366.055/0001-16')
        settings.legal_settings = values
        settings.save(update_fields=['legal_settings'])


class Migration(migrations.Migration):
    dependencies = [('saas', '0012_commercial_feature_capabilities')]
    operations = [migrations.AddField(
        model_name='globalsaassettings', name='legal_settings',
        field=models.JSONField(default=dict, blank=True),
    ), migrations.RunPython(preserve_existing_site_identity, migrations.RunPython.noop)]
