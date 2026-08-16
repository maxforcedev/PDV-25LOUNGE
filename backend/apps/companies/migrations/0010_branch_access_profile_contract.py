import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('companies', '0009_branch_access_profile_data')]

    operations = [
        migrations.AlterField(
            model_name='userbranchaccess',
            name='access_profile',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='branch_user_accesses',
                to='companies.accessprofile',
            ),
        ),
    ]
