from apps.accounts.models import User

from .models import Branch, Company, UserBranchAccess, UserCompanyAccess


def accessible_companies(user, permission_code=None):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return Company.objects.none()
    if user.is_authenticated and user.is_superuser:
        return Company.objects.all()
    filters = {
        'user_accesses__user': user,
        'user_accesses__is_active': True,
        'user_accesses__access_profile__status': 'active',
    }
    if permission_code:
        filters.update(
            {
                'user_accesses__access_profile__permissions__status': 'active',
                'user_accesses__access_profile__permissions__code': permission_code,
            }
        )
    return Company.objects.filter(**filters).distinct()


def accessible_branches(user, permission_code=None):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return Branch.objects.none()
    if user.is_authenticated and user.is_superuser:
        return Branch.objects.all()
    filters = {
        'user_accesses__user': user,
        'user_accesses__is_active': True,
        'user_accesses__access_profile__status': 'active',
        'company__user_accesses__user': user,
        'company__user_accesses__is_active': True,
        'company__user_accesses__access_profile__status': 'active',
    }
    if permission_code:
        from .rbac import OPERATING_PERMISSION_CODES

        if permission_code in OPERATING_PERMISSION_CODES:
            filters.update({
                'user_accesses__access_profile__permissions__status': 'active',
                'user_accesses__access_profile__permissions__code': permission_code,
            })
        else:
            filters.update({
                'company__user_accesses__access_profile__permissions__status': 'active',
                'company__user_accesses__access_profile__permissions__code': permission_code,
            })
    return Branch.objects.filter(**filters).distinct()


def active_operational_companies(user):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return Company.objects.none()
    return Company.objects.filter(
        status='active',
        user_accesses__user=user,
        user_accesses__is_active=True,
        user_accesses__access_profile__status='active',
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
        company__user_accesses__access_profile__status='active',
    ).distinct()


def company_permission_codes(user, company_id):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return set()
    if user.is_superuser:
        from .rbac import ALL_PERMISSION_CODES

        return set(ALL_PERMISSION_CODES)
    return set(
        UserCompanyAccess.objects.filter(
            user=user,
            company_id=company_id,
            is_active=True,
            access_profile__status='active',
            access_profile__permissions__status='active',
        ).values_list('access_profile__permissions__code', flat=True)
    )


def user_has_company_permission(user, company_id, code):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return False
    return user.is_superuser or UserCompanyAccess.objects.filter(
        user=user,
        company_id=company_id,
        is_active=True,
        access_profile__status='active',
        access_profile__permissions__status='active',
        access_profile__permissions__code=code,
    ).exists()


def user_has_branch_permission(user, branch_id, code):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return UserBranchAccess.objects.filter(
        user=user,
        branch_id=branch_id,
        is_active=True,
        access_profile__status='active',
        access_profile__permissions__status='active',
        access_profile__permissions__code=code,
        branch__company__user_accesses__user=user,
        branch__company__user_accesses__is_active=True,
        branch__company__user_accesses__access_profile__status='active',
    ).exists()


def eligible_branch_users(branch, permission_code):
    return User.objects.filter(
        is_active=True,
        can_login=True,
        branch_accesses__branch=branch,
        branch_accesses__is_active=True,
        branch_accesses__access_profile__status='active',
        branch_accesses__access_profile__permissions__status='active',
        branch_accesses__access_profile__permissions__code=permission_code,
        company_accesses__company_id=branch.company_id,
        company_accesses__is_active=True,
        company_accesses__access_profile__status='active',
    ).distinct().order_by('first_name', 'last_name', 'email', 'id')


def branch_permission_codes(user, branch_id):
    if not user.is_authenticated or not user.can_login or not user.is_active:
        return set()
    if user.is_superuser:
        from .rbac import ALL_PERMISSION_CODES

        return set(ALL_PERMISSION_CODES)
    return set(
        UserBranchAccess.objects.filter(
            user=user,
            branch_id=branch_id,
            is_active=True,
            access_profile__status='active',
            access_profile__permissions__status='active',
            branch__company__user_accesses__user=user,
            branch__company__user_accesses__is_active=True,
            branch__company__user_accesses__access_profile__status='active',
        ).values_list('access_profile__permissions__code', flat=True)
    )
