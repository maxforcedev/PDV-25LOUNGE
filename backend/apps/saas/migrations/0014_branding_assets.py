import apps.saas.storage
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('saas', '0013_legal_settings')]

    operations = [
        migrations.AddField(
            model_name='globalsaassettings', name='logo_file',
            field=models.FileField(blank=True, storage=apps.saas.storage.PrivateBrandingStorage(), upload_to=apps.saas.storage.branding_asset_path, validators=[apps.saas.storage.validate_branding_image]),
        ),
        migrations.AddField(
            model_name='globalsaassettings', name='compact_logo_file',
            field=models.FileField(blank=True, storage=apps.saas.storage.PrivateBrandingStorage(), upload_to=apps.saas.storage.branding_asset_path, validators=[apps.saas.storage.validate_branding_image]),
        ),
        migrations.AddField(
            model_name='globalsaassettings', name='favicon_file',
            field=models.FileField(blank=True, storage=apps.saas.storage.PrivateBrandingStorage(), upload_to=apps.saas.storage.branding_asset_path, validators=[apps.saas.storage.validate_branding_favicon]),
        ),
        migrations.AddField(
            model_name='globalsaassettings', name='logo_light_file',
            field=models.FileField(blank=True, storage=apps.saas.storage.PrivateBrandingStorage(), upload_to=apps.saas.storage.branding_asset_path, validators=[apps.saas.storage.validate_branding_image]),
        ),
        migrations.AddField(
            model_name='globalsaassettings', name='logo_dark_file',
            field=models.FileField(blank=True, storage=apps.saas.storage.PrivateBrandingStorage(), upload_to=apps.saas.storage.branding_asset_path, validators=[apps.saas.storage.validate_branding_image]),
        ),
        migrations.AddField(
            model_name='globalsaassettings', name='compact_logo_light_file',
            field=models.FileField(blank=True, storage=apps.saas.storage.PrivateBrandingStorage(), upload_to=apps.saas.storage.branding_asset_path, validators=[apps.saas.storage.validate_branding_image]),
        ),
        migrations.AddField(
            model_name='globalsaassettings', name='compact_logo_dark_file',
            field=models.FileField(blank=True, storage=apps.saas.storage.PrivateBrandingStorage(), upload_to=apps.saas.storage.branding_asset_path, validators=[apps.saas.storage.validate_branding_image]),
        ),
    ]
