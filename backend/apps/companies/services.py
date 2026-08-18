from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    AccessProfile,
    Branch,
    Company,
    FunctionalPermission,
    UserBranchAccess,
    UserCompanyAccess,
)
from .rbac import (
    DEFAULT_PROFILE_DESCRIPTIONS,
    DEFAULT_PROFILE_PERMISSIONS,
    PERMISSION_CATALOG,
)


def ensure_permission_catalog():
    permissions = {}
    catalog_codes = {item[0] for item in PERMISSION_CATALOG}
    FunctionalPermission.objects.exclude(code__in=catalog_codes).update(status='inactive')
    for code, module, label, description in PERMISSION_CATALOG:
        permission, _ = FunctionalPermission.objects.update_or_create(
            code=code,
            defaults={
                'module': module,
                'label': label,
                'description': description,
                'status': 'active',
            },
        )
        permissions[code] = permission
    return permissions


def ensure_default_access_profiles(company):
    permissions = ensure_permission_catalog()
    active_permissions = FunctionalPermission.objects.filter(status='active')
    profiles = {}
    for name, permission_codes in DEFAULT_PROFILE_PERMISSIONS.items():
        profile, created = AccessProfile.objects.get_or_create(
            company=company,
            name=name,
            defaults={
                'description': DEFAULT_PROFILE_DESCRIPTIONS[name],
                'is_system': True,
                'status': 'active',
            },
        )
        if created:
            profile.permissions.set(permissions[code] for code in permission_codes)
        if name == 'Administrador' and profile.is_system:
            profile.permissions.add(*active_permissions)
        profiles[name] = profile
    return profiles


@transaction.atomic
def create_company_with_matrix(*, creator, **company_data):
    company = Company.objects.create(**company_data)
    profiles = ensure_default_access_profiles(company)
    matrix = Branch.objects.create(
        company=company, name='Matriz', is_matrix=True, address_pending=True
    )
    UserCompanyAccess.objects.create(
        user=creator,
        company=company,
        access_profile=profiles['Administrador'],
    )
    UserBranchAccess.objects.create(
        user=creator,
        branch=matrix,
        access_profile=profiles['Administrador'],
    )
    return company


@transaction.atomic
def create_branch_with_access(*, creator, **branch_data):
    requested_company = branch_data.pop('company')
    company = Company.objects.select_for_update().get(pk=requested_company.pk)
    if company.status != 'active':
        raise ValidationError({'company': 'Nao e possivel criar filial em empresa inativa.'})
    branch_data['company'] = company
    branch = Branch.objects.create(**branch_data)
    company_access = UserCompanyAccess.objects.get(
        user=creator, company=company, is_active=True
    )
    UserBranchAccess.objects.update_or_create(
        user=creator,
        branch=branch,
        defaults={
            'access_profile': company_access.access_profile,
            'is_active': True,
        },
    )
    return branch


@transaction.atomic
def activate_company(*, company):
    locked_company = Company.objects.select_for_update().get(pk=company.pk)
    locked_company.status = 'active'
    locked_company.save(update_fields=['status', 'updated_at'])
    return locked_company


@transaction.atomic
def deactivate_company(*, company):
    locked_company = Company.objects.select_for_update().get(pk=company.pk)
    now = timezone.now()
    Branch.objects.filter(company=locked_company, status='active').update(
        status='inactive',
        updated_at=now,
    )
    locked_company.status = 'inactive'
    locked_company.save(update_fields=['status', 'updated_at'])
    return locked_company


@transaction.atomic
def activate_branch(*, branch):
    company = Company.objects.select_for_update().get(pk=branch.company_id)
    if company.status != 'active':
        raise ValidationError({'status': 'Ative a empresa antes de ativar a filial.'})
    locked_branch = Branch.objects.select_for_update().get(pk=branch.pk)
    locked_branch.status = 'active'
    locked_branch.save(update_fields=['status', 'updated_at'])
    return locked_branch


@transaction.atomic
def replace_user_accesses(*, user, company_accesses):
    requested_company_ids = {item['company'].id for item in company_accesses}
    existing_accesses = UserCompanyAccess.objects.select_for_update().filter(user=user)
    for access in existing_accesses.exclude(company_id__in=requested_company_ids):
        if access.is_active:
            access.is_active = False
            access.save(update_fields=['is_active', 'updated_at'])
        UserBranchAccess.objects.filter(
            user=user,
            branch__company_id=access.company_id,
        ).update(is_active=False, updated_at=timezone.now())

    for item in company_accesses:
        company = item['company']
        profile = item['access_profile']
        branch_accesses = {
            branch_item['branch'].id: branch_item
            for branch_item in item['branch_accesses']
        }
        access, _ = UserCompanyAccess.objects.get_or_create(
            user=user,
            company=company,
            defaults={'access_profile': profile, 'is_active': True},
        )
        access.access_profile = profile
        access.is_active = True
        access.save(update_fields=['access_profile', 'is_active', 'updated_at'])

        UserBranchAccess.objects.filter(user=user, branch__company=company).exclude(
            branch_id__in=branch_accesses
        ).update(is_active=False, updated_at=timezone.now())
        for branch in Branch.objects.filter(company=company):
            should_activate = branch.id in branch_accesses
            if not should_activate:
                continue
            branch_profile = branch_accesses[branch.id]['access_profile']
            branch_access, _ = UserBranchAccess.objects.get_or_create(
                user=user,
                branch=branch,
                defaults={
                    'access_profile': branch_profile,
                    'is_active': should_activate,
                },
            )
            branch_access.access_profile = branch_profile
            branch_access.is_active = should_activate
            branch_access.save(
                update_fields=['access_profile', 'is_active', 'updated_at']
            )
