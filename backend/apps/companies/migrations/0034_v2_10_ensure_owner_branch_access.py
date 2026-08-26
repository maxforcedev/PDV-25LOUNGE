from django.db import migrations


def ensure_owner_branch_access(apps, schema_editor):
    UserCompanyAccess = apps.get_model('companies', 'UserCompanyAccess')
    UserBranchAccess = apps.get_model('companies', 'UserBranchAccess')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    Branch = apps.get_model('companies', 'Branch')

    for access in UserCompanyAccess.objects.filter(is_owner=True, is_active=True).select_related('company'):
        existing = UserBranchAccess.objects.filter(
            user_id=access.user_id,
            branch__company_id=access.company_id,
            is_active=True,
            access_profile__status='active',
        ).exists()
        if existing:
            continue
        matrix = Branch.objects.filter(company_id=access.company_id, is_matrix=True).first()
        if not matrix:
            matrix = Branch.objects.filter(company_id=access.company_id).first()
        if not matrix:
            continue
        profile = AccessProfile.objects.filter(
            company_id=access.company_id, name='Administrador', is_system=True, status='active'
        ).first()
        if not profile:
            profile = AccessProfile.objects.filter(company_id=access.company_id, status='active').first()
        if not profile:
            continue
        UserBranchAccess.objects.update_or_create(
            user_id=access.user_id, branch=matrix,
            defaults={'access_profile': profile, 'is_active': True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0033_v2_10_auth_consolidation'),
    ]

    operations = [
        migrations.RunPython(ensure_owner_branch_access, migrations.RunPython.noop),
    ]
