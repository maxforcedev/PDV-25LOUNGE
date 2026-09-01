from django.db import migrations, models


def backfill_company_login_access(apps, schema_editor):
    UserCompanyAccess = apps.get_model('companies', 'UserCompanyAccess')
    UserCompanyAccess.objects.filter(user__can_login=False).update(can_login=False)


class Migration(migrations.Migration):
    dependencies = [('companies', '0043_usercompanyaccess_archived_at')]

    operations = [
        migrations.AddField(
            model_name='usercompanyaccess',
            name='can_login',
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(backfill_company_login_access, migrations.RunPython.noop),
    ]
