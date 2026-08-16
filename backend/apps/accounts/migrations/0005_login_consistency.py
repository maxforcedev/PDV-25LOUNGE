from django.contrib.auth.hashers import make_password
from django.db import migrations, models
from django.db.models import Q


def disable_inconsistent_logins(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    UserCompanyAccess = apps.get_model('companies', 'UserCompanyAccess')
    UserBranchAccess = apps.get_model('companies', 'UserBranchAccess')
    user_ids = list(
        User.objects.filter(can_login=True, email__isnull=True).values_list('pk', flat=True)
    )
    if not user_ids:
        return
    User.objects.filter(pk__in=user_ids).update(
        can_login=False, password=make_password(None)
    )
    UserCompanyAccess.objects.filter(user_id__in=user_ids).update(access_profile=None)
    UserBranchAccess.objects.filter(user_id__in=user_ids).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0004_operational_users_contract'),
        ('companies', '0012_sprint_7_1_permissions'),
    ]

    operations = [
        migrations.RunPython(disable_inconsistent_logins, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.CheckConstraint(
                condition=Q(can_login=False) | Q(email__isnull=False),
                name='accounts_user_login_requires_email',
            ),
        ),
    ]
