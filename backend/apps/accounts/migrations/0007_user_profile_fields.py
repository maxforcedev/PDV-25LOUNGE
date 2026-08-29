import apps.accounts.storage
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0006_v2_10_auth_consolidation')]

    operations = [
        migrations.AddField(
            model_name='user',
            name='profile_photo',
            field=models.FileField(
                blank=True,
                null=True,
                storage=apps.accounts.storage.PrivateProfileStorage(),
                upload_to=apps.accounts.storage.profile_photo_path,
                validators=[apps.accounts.storage.validate_profile_photo],
            ),
        ),
        migrations.AddField(model_name='user', name='birth_date', field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name='user', name='cpf', field=models.CharField(blank=True, default='', max_length=14)),
        migrations.AddField(model_name='user', name='zip_code', field=models.CharField(blank=True, default='', max_length=9)),
        migrations.AddField(model_name='user', name='street', field=models.CharField(blank=True, default='', max_length=160)),
        migrations.AddField(model_name='user', name='address_number', field=models.CharField(blank=True, default='', max_length=20)),
        migrations.AddField(model_name='user', name='address_complement', field=models.CharField(blank=True, default='', max_length=100)),
        migrations.AddField(model_name='user', name='neighborhood', field=models.CharField(blank=True, default='', max_length=100)),
        migrations.AddField(model_name='user', name='city', field=models.CharField(blank=True, default='', max_length=100)),
        migrations.AddField(model_name='user', name='state', field=models.CharField(blank=True, default='', max_length=2)),
    ]
