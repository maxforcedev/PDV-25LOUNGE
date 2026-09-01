from apps.accounts.models import User

from .models import Branch, Company, UserBranchAccess, UserCompanyAccess, UserPermissionBlock


def _company_blocked_codes(user, company_id):
    return set(
        UserPermissionBlock.objects.filter(
            user=user, company_id=company_id, branch__isnull=True, is_active=True,
            permission__status='active',
        ).values_list('permission__code', flat=True)
    )


def _branch_blocked_codes(user, branch_id):
    branch = Branch.objects.filter(pk=branch_id).only('company_id').first()
    if not branch:
        return set()
    return set(
        UserPermissionBlock.objects.filter(
            user=user,
            company_id=branch.company_id,
            is_active=True,
            permission__status='active',
        ).filter(branch_id__in=(branch_id,) if branch_id else ()).values_list(
            'permission__code', flat=True
        )
    ) | _company_blocked_codes(user, branch.company_id)


def _permission_blocked(user, *, company_id=None, branch_id=None, code):
    if user.is_superuser:
        return False
    if branch_id:
        return code in _branch_blocked_codes(user, branch_id)
    return code in _company_blocked_codes(user, company_id)


def _company_membership_filters(user):
    return {
        'user_accesses__user': user,
        'user_accesses__is_active': True,
        'user_accesses__can_login': True,
        'user_accesses__saas_status': UserCompanyAccess.SaaSStatus.ACTIVE,
    }


def accessible_companies(user, permission_code=None):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return Company.objects.none()
    if user.is_authenticated and user.is_superuser:
        return Company.objects.all()
    filters = _company_membership_filters(user)
    filters.update({
        'branches__user_accesses__user': user,
        'branches__user_accesses__is_active': True,
        'branches__user_accesses__access_profile__status': 'active',
    })
    if permission_code:
        filters.update(
            {
                'branches__user_accesses__access_profile__permissions__status': 'active',
                'branches__user_accesses__access_profile__permissions__code': permission_code,
            }
        )
    queryset = Company.objects.filter(**filters).distinct()
    if permission_code and not user.is_superuser:
        blocked_company_ids = UserPermissionBlock.objects.filter(
            user=user, branch__isnull=True, is_active=True,
            permission__code=permission_code,
        ).values_list('company_id', flat=True)
        queryset = queryset.exclude(id__in=blocked_company_ids)
    return queryset


def accessible_branches(user, permission_code=None):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return Branch.objects.none()
    if user.is_authenticated and user.is_superuser:
        return Branch.objects.all()
    membership_filters = {
        'user_accesses__user': user,
        'user_accesses__is_active': True,
        'user_accesses__access_profile__status': 'active',
        'company__user_accesses__user': user,
        'company__user_accesses__is_active': True,
        'company__user_accesses__can_login': True,
        'company__user_accesses__saas_status': UserCompanyAccess.SaaSStatus.ACTIVE,
    }
    if permission_code:
        from .rbac import OPERATING_PERMISSION_CODES

        if permission_code in OPERATING_PERMISSION_CODES:
            membership_filters.update({
                'user_accesses__access_profile__permissions__status': 'active',
                'user_accesses__access_profile__permissions__code': permission_code,
            })
            queryset = Branch.objects.filter(**membership_filters).distinct()
        else:
            company_ids_with_perm = set(
                UserBranchAccess.objects.filter(
                    user=user,
                    is_active=True,
                    access_profile__status='active',
                    access_profile__permissions__status='active',
                    access_profile__permissions__code=permission_code,
                    branch__company__user_accesses__user=user,
                    branch__company__user_accesses__is_active=True,
                    branch__company__user_accesses__can_login=True,
                    branch__company__user_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
                ).values_list('branch__company_id', flat=True).distinct()
            )
            queryset = Branch.objects.filter(**{
                k: v for k, v in membership_filters.items()
                if not k.startswith('user_accesses__access_profile__permissions')
            }).filter(company_id__in=company_ids_with_perm).distinct()
    else:
        queryset = Branch.objects.filter(**membership_filters).distinct()
    if permission_code and not user.is_superuser:
        blocked = UserPermissionBlock.objects.filter(
            user=user, is_active=True, permission__code=permission_code,
        )
        blocked_branches = blocked.exclude(branch__isnull=True).values_list('branch_id', flat=True)
        blocked_companies = blocked.filter(branch__isnull=True).values_list('company_id', flat=True)
        queryset = queryset.exclude(id__in=blocked_branches).exclude(company_id__in=blocked_companies)
    return queryset


def active_operational_companies(user):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return Company.objects.none()
    return Company.objects.filter(
        status='active',
        user_accesses__user=user,
        user_accesses__is_active=True,
        user_accesses__can_login=True,
        user_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
    ).distinct()


def active_operational_branches(user):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return Branch.objects.none()
    return Branch.objects.filter(
        status='active',
        company__status='active',
        user_accesses__user=user,
        user_accesses__is_active=True,
        user_accesses__access_profile__status='active',
        company__user_accesses__user=user,
        company__user_accesses__is_active=True,
        company__user_accesses__can_login=True,
        company__user_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
    ).distinct()


def company_permission_codes(user, company_id):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return set()
    if user.is_superuser:
        from .rbac import ALL_PERMISSION_CODES

        return set(ALL_PERMISSION_CODES)
    codes = set(
        UserBranchAccess.objects.filter(
            user=user,
            branch__company_id=company_id,
            is_active=True,
            access_profile__status='active',
            access_profile__permissions__status='active',
            branch__company__user_accesses__user=user,
            branch__company__user_accesses__is_active=True,
            branch__company__user_accesses__can_login=True,
            branch__company__user_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
        ).values_list('access_profile__permissions__code', flat=True)
    )
    return codes - _company_blocked_codes(user, company_id)


def user_has_company_permission(user, company_id, code):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return False
    if user.is_superuser:
        return True
    if _permission_blocked(user, company_id=company_id, code=code):
        return False
    return UserBranchAccess.objects.filter(
        user=user,
        branch__company_id=company_id,
        is_active=True,
        access_profile__status='active',
        access_profile__permissions__status='active',
        access_profile__permissions__code=code,
        branch__company__user_accesses__user=user,
        branch__company__user_accesses__is_active=True,
        branch__company__user_accesses__can_login=True,
        branch__company__user_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
    ).exists()


def user_has_branch_permission(user, branch_id, code):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return False
    if user.is_superuser:
        return True
    if _permission_blocked(user, branch_id=branch_id, code=code):
        return False
    return UserBranchAccess.objects.filter(
        user=user,
        branch_id=branch_id,
        is_active=True,
        access_profile__status='active',
        access_profile__permissions__status='active',
        access_profile__permissions__code=code,
        branch__company__user_accesses__user=user,
        branch__company__user_accesses__is_active=True,
        branch__company__user_accesses__can_login=True,
        branch__company__user_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
    ).exists()


def eligible_branch_users(branch, permission_code):
    blocked_users = UserPermissionBlock.objects.filter(
        company_id=branch.company_id,
        is_active=True,
        permission__code=permission_code,
    ).filter(branch_id__in=(branch.pk,)).values_list('user_id', flat=True)
    company_blocked_users = UserPermissionBlock.objects.filter(
        company_id=branch.company_id,
        branch__isnull=True,
        is_active=True,
        permission__code=permission_code,
    ).values_list('user_id', flat=True)
    return User.objects.filter(
        is_active=True,
        archived_at__isnull=True,
        can_login=True,
        branch_accesses__branch=branch,
        branch_accesses__is_active=True,
        branch_accesses__access_profile__status='active',
        branch_accesses__access_profile__permissions__status='active',
        branch_accesses__access_profile__permissions__code=permission_code,
        company_accesses__company_id=branch.company_id,
        company_accesses__is_active=True,
        company_accesses__can_login=True,
        company_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
    ).exclude(id__in=blocked_users).exclude(id__in=company_blocked_users).distinct().order_by('first_name', 'last_name', 'email', 'id')


def branch_permission_codes(user, branch_id):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return set()
    if user.is_superuser:
        from .rbac import ALL_PERMISSION_CODES

        return set(ALL_PERMISSION_CODES)
    codes = set(
        UserBranchAccess.objects.filter(
            user=user,
            branch_id=branch_id,
            is_active=True,
            access_profile__status='active',
            access_profile__permissions__status='active',
            branch__company__user_accesses__user=user,
            branch__company__user_accesses__is_active=True,
            branch__company__user_accesses__can_login=True,
            branch__company__user_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
        ).values_list('access_profile__permissions__code', flat=True)
    )
    return codes - _branch_blocked_codes(user, branch_id)


def inherited_permission_codes(user, company_id, branch_id=None):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return set()
    if user.is_superuser:
        from .rbac import ALL_PERMISSION_CODES

        return set(ALL_PERMISSION_CODES)

    if branch_id:
        return set(
            UserBranchAccess.objects.filter(
                user=user,
                branch_id=branch_id,
                branch__company_id=company_id,
                is_active=True,
                access_profile__status='active',
                access_profile__permissions__status='active',
                branch__company__user_accesses__user=user,
                branch__company__user_accesses__is_active=True,
                branch__company__user_accesses__can_login=True,
                branch__company__user_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
            ).values_list('access_profile__permissions__code', flat=True)
        )

    return set(
        UserBranchAccess.objects.filter(
            user=user,
            branch__company_id=company_id,
            is_active=True,
            access_profile__status='active',
            access_profile__permissions__status='active',
            branch__company__user_accesses__user=user,
            branch__company__user_accesses__is_active=True,
            branch__company__user_accesses__can_login=True,
            branch__company__user_accesses__saas_status=UserCompanyAccess.SaaSStatus.ACTIVE,
        ).values_list('access_profile__permissions__code', flat=True)
    )


def blockable_permission_codes(user, company_id, branch_id=None):
    codes = inherited_permission_codes(user, company_id, branch_id)
    if branch_id:
        return codes - _branch_blocked_codes(user, branch_id)
    return codes - _company_blocked_codes(user, company_id)
