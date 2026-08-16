from django.db import migrations


def copy_company_profiles(apps, schema_editor):
    UserBranchAccess = apps.get_model('companies', 'UserBranchAccess')
    UserCompanyAccess = apps.get_model('companies', 'UserCompanyAccess')

    profiles = {
        (access.user_id, access.company_id): access.access_profile_id
        for access in UserCompanyAccess.objects.all().iterator()
    }
    branch_accesses = list(
        UserBranchAccess.objects.select_related('branch').iterator()
    )
    orphaned = [
        (
            access.pk,
            access.user_id,
            access.branch_id,
            access.branch.company_id,
        )
        for access in branch_accesses
        if (access.user_id, access.branch.company_id) not in profiles
    ]
    if orphaned:
        details = ', '.join(
            f'access={access_id} user={user_id} branch={branch_id} company={company_id}'
            for access_id, user_id, branch_id, company_id in orphaned
        )
        raise RuntimeError(
            'UserBranchAccess sem UserCompanyAccess correspondente: ' + details
        )
    for access in branch_accesses:
        access.access_profile_id = profiles[(access.user_id, access.branch.company_id)]
        access.save(update_fields=['access_profile'])


class Migration(migrations.Migration):
    dependencies = [('companies', '0008_branch_access_profile_expand')]

    operations = [
        migrations.RunPython(copy_company_profiles, migrations.RunPython.noop),
    ]
