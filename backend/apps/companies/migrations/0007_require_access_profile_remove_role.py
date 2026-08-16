import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('companies', '0006_populate_access_profiles')]

    operations = [
        migrations.AlterField(
            model_name='usercompanyaccess',
            name='access_profile',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='user_accesses',
                to='companies.accessprofile',
            ),
        ),
        migrations.RemoveField(
            model_name='usercompanyaccess',
            name='role',
        ),
    ]
