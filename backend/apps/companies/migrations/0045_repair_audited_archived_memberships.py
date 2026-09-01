from django.db import migrations


def repair_audited_archived_memberships(apps, schema_editor):
    AuditLog = apps.get_model('base', 'AuditLog')
    UserBranchAccess = apps.get_model('companies', 'UserBranchAccess')
    UserCompanyAccess = apps.get_model('companies', 'UserCompanyAccess')

    latest_events = {}
    events = AuditLog.objects.filter(
        action__in=('user.archive', 'user.restore'),
        company_id__isnull=False,
    ).order_by('-created_at', '-id').values(
        'action', 'object_id', 'company_id', 'created_at',
    )
    for event in events.iterator():
        latest_events.setdefault(
            (event['object_id'], event['company_id']), event,
        )

    accesses = UserCompanyAccess.objects.filter(
        is_active=False,
        archived_at__isnull=True,
    ).only('id', 'user_id', 'company_id')
    for access in accesses.iterator():
        event = latest_events.get((str(access.user_id), access.company_id))
        if event and event['action'] == 'user.archive':
            UserCompanyAccess.objects.filter(pk=access.pk).update(
                archived_at=event['created_at'],
                updated_at=event['created_at'],
            )
            UserBranchAccess.objects.filter(
                user_id=access.user_id,
                branch__company_id=access.company_id,
            ).update(
                is_active=False,
                updated_at=event['created_at'],
            )


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0001_initial'),
        ('companies', '0044_usercompanyaccess_can_login'),
    ]

    operations = [
        migrations.RunPython(
            repair_audited_archived_memberships,
            migrations.RunPython.noop,
        ),
    ]
