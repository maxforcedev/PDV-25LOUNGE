import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('companies', '0010_branch_access_profile_contract')]

    operations = [
        migrations.AlterField(
            model_name='usercompanyaccess',
            name='access_profile',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='user_accesses',
                to='companies.accessprofile',
            ),
        ),
    ]
