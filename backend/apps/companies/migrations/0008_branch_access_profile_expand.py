import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('companies', '0007_require_access_profile_remove_role')]

    operations = [
        migrations.AddField(
            model_name='userbranchaccess',
            name='access_profile',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='branch_user_accesses',
                to='companies.accessprofile',
            ),
        ),
    ]
