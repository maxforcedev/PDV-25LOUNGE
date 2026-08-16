from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0001_initial')]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='email',
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='can_login',
            field=models.BooleanField(null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='user_type',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
