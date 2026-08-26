from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.base.audit import audit_log, model_snapshot

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
def create_company_with_matrix(*, creator, enforce_saas_limits=True, **company_data):
    company = Company.objects.create(**company_data)
    profiles = ensure_default_access_profiles(company)
    matrix = Branch(
        company=company, name='Matriz', is_matrix=True, address_pending=True
    )
    matrix.save(enforce_saas_limit=enforce_saas_limits)
    company_access = UserCompanyAccess(
        user=creator,
        company=company,
        access_profile=profiles['Administrador'],
        is_owner=True,
    )
    company_access.save(enforce_saas_limit=enforce_saas_limits)
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
        raise ValidationError({'company': 'Não é possível criar filial em empresa inativa.'})
    from apps.saas.services import assert_resource_limit

    assert_resource_limit(company, 'branches.max')
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
    from apps.saas.services import validate_company_ready_for_enforcement

    validate_company_ready_for_enforcement(locked_company)
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
        access, created = UserCompanyAccess.objects.get_or_create(
            user=user,
            company=company,
            defaults={'access_profile': profile, 'is_active': True},
        )
        if user.can_login and (created or not access.is_active or access.saas_status != UserCompanyAccess.SaaSStatus.ACTIVE):
            from apps.saas.services import assert_resource_limit

            assert_resource_limit(company, 'users.max', delta=0 if created else 1)
        access.access_profile = profile
        access.is_active = True
        access.saas_status = UserCompanyAccess.SaaSStatus.ACTIVE
        access.save(update_fields=['access_profile', 'is_active', 'saas_status', 'updated_at'])

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


def _validate_owner_target(access):
    errors = {}
    if not access.is_active:
        errors['target_user_id'] = 'O acesso do novo proprietário deve estar ativo.'
    if not access.user.is_active or not access.user.can_login:
        errors['target_user_id'] = 'O novo proprietário deve estar ativo e habilitado para login.'
    has_branch_profile = UserBranchAccess.objects.filter(
        user=access.user,
        branch__company_id=access.company_id,
        is_active=True,
        access_profile__status='active',
        branch__company__user_accesses__user=access.user,
        branch__company__user_accesses__is_active=True,
    ).exists()
    if not has_branch_profile:
        errors['target_user_id'] = 'O novo proprietário deve possuir ao menos uma filial com perfil ativo.'
    if errors:
        raise ValidationError(errors)


@transaction.atomic
def assign_company_owner(*, company_id, user_id, source='management_command'):
    company = Company.objects.select_for_update().get(pk=company_id)
    accesses = UserCompanyAccess.objects.select_for_update().filter(company=company)
    current = accesses.filter(is_owner=True).select_related('user').first()
    if current:
        if current.user_id == user_id:
            return current, False
        raise ValidationError(
            {'company_id': 'A empresa já possui proprietário; substituições exigem transferência.'}
        )
    try:
        target = accesses.get(user_id=user_id)
    except UserCompanyAccess.DoesNotExist as error:
        raise ValidationError(
            {'user_id': 'O usuário não possui acesso a esta empresa.'}
        ) from error
    target.user = User.objects.select_for_update().get(pk=target.user_id)
    if target.access_profile_id:
        target.access_profile = AccessProfile.objects.select_for_update().get(
            pk=target.access_profile_id
        )
    _validate_owner_target(target)
    target.is_owner = True
    target.save(update_fields=('is_owner', 'updated_at'))
    audit_log(
        action='company.owner.assign',
        obj=target,
        company=company,
        after=model_snapshot(
            target, ('company_id', 'user_id', 'access_profile_id', 'is_active', 'is_owner')
        ),
        metadata={'source': source},
    )
    return target, True


@transaction.atomic
def transfer_company_owner(
    *, company, actor, target_user_id, current_password, reason,
    platform_authorized=False,
):
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': 'Informe o motivo da transferência.'})

    locked_company = Company.objects.select_for_update().get(pk=company.pk)
    accesses = UserCompanyAccess.objects.select_for_update().filter(
        company=locked_company
    )
    current = accesses.filter(is_owner=True).select_related('user').first()
    if not current:
        raise ValidationError({'current_password': 'A empresa nao possui proprietário atual.'})
    if platform_authorized:
        from apps.saas.services import user_has_platform_permission

        authorized = user_has_platform_permission(actor, 'platform.tenants.manage')
        password_user = actor
    else:
        authorized = current.user_id == actor.pk
        password_user = current.user
    if not authorized:
        raise ValidationError(
            {'current_password': 'Somente o proprietário atual pode transferir a propriedade.'}
        )
    if not password_user.check_password(current_password or ''):
        raise ValidationError({'current_password': 'Senha atual inválida.'})
    if target_user_id == current.user_id:
        raise ValidationError({'target_user_id': 'Selecione outro usuário como proprietário.'})
    try:
        target = accesses.get(user_id=target_user_id)
    except UserCompanyAccess.DoesNotExist as error:
        raise ValidationError(
            {'target_user_id': 'O usuário não possui acesso a esta empresa.'}
        ) from error
    target.user = User.objects.select_for_update().get(pk=target.user_id)
    if target.access_profile_id:
        target.access_profile = AccessProfile.objects.select_for_update().get(
            pk=target.access_profile_id
        )
    _validate_owner_target(target)

    before = {
        'membership_id': current.pk,
        'user_id': current.user_id,
        'is_owner': True,
    }
    now = timezone.now()
    models.QuerySet.update(
        accesses.filter(pk=current.pk),
        is_owner=False, updated_at=now
    )
    models.QuerySet.update(
        accesses.filter(pk=target.pk),
        is_owner=True, updated_at=now
    )
    target.is_owner = True
    target.updated_at = now
    audit_log(
        actor=actor,
        action='company.owner.transfer',
        obj=target,
        company=locked_company,
        before=before,
        after={
            'membership_id': target.pk,
            'user_id': target.user_id,
            'is_owner': True,
        },
        metadata={'reason': reason},
    )
    return target
