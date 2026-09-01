from django.db import migrations, models
from django.utils import timezone


def backfill_archived_memberships(apps, schema_editor):
    UserCompanyAccess = apps.get_model('companies', 'UserCompanyAccess')
    UserBranchAccess = apps.get_model('companies', 'UserBranchAccess')
    archived_accesses = UserCompanyAccess.objects.filter(
        user__archived_at__isnull=False,
    ).select_related('user')
    now = timezone.now()
    for access in archived_accesses.iterator():
        access.archived_at = access.user.archived_at or now
        access.is_active = False
        access.save(update_fields=('archived_at', 'is_active', 'updated_at'))
        UserBranchAccess.objects.filter(
            user_id=access.user_id,
            branch__company_id=access.company_id,
        ).update(is_active=False, updated_at=now)


class Migration(migrations.Migration):
    dependencies = [('companies', '0042_branchsettings_table_range')]

    operations = [
        migrations.AddField(
            model_name='usercompanyaccess',
            name='archived_at',
            field=models.DateTimeField(blank=True, default=None, null=True),
        ),
        migrations.RunPython(backfill_archived_memberships, migrations.RunPython.noop),
    ]
