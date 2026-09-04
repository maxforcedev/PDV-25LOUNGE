from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0007_user_profile_fields')]

    operations = [
        migrations.AddField(model_name='user', name='can_access_pos', field=models.BooleanField(db_default=False, default=False)),
        migrations.AddField(model_name='user', name='pos_pin_hash', field=models.CharField(blank=True, default='', editable=False, max_length=256)),
    ]
