from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.companies.models import (
    AccessProfile,
    Branch,
    Company,
    Status,
    UserBranchAccess,
    UserCompanyAccess,
    UserPermissionBlock,
    FunctionalPermission,
)
from apps.companies.rbac import PERMISSION_CATALOG
from apps.companies.selectors import (
    accessible_branches,
    accessible_companies,
    branch_permission_codes,
    company_permission_codes,
    inherited_permission_codes,
    user_has_branch_permission,
    user_has_company_permission,
)
from apps.companies.services import (
    create_company_with_matrix,
    ensure_permission_catalog,
    replace_user_accesses,
)


def _admin_profile(company):
    return AccessProfile.objects.get(company=company, name='Administrador', is_system=True)


def _make_profile(company, name, codes):
    profile = AccessProfile.objects.create(company=company, name=name, status=Status.ACTIVE)
    perms = []
    for code in codes:
        perm, _ = FunctionalPermission.objects.get_or_create(
            code=code,
            defaults={'module': code.split('.')[0], 'label': code, 'description': ''},
        )
        perms.append(perm)
    profile.permissions.set(perms)
    return profile


class MembershipCompanyTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = User.objects.create_user(email='owner@example.com', password='secret123')
        self.company = create_company_with_matrix(creator=self.owner, trade_name='Empresa A', legal_name='Empresa A Legal')
        self.user = User.objects.create_user(email='user@example.com', password='secret123')
        self.matrix = self.company.branches.get(is_matrix=True)
        self.admin = _admin_profile(self.company)
        UserCompanyAccess.objects.create(user=self.user, company=self.company, is_active=True)
        UserBranchAccess.objects.create(user=self.user, branch=self.matrix, access_profile=self.admin, is_active=True)

    def test_user_with_branch_profile_can_access_company(self):
        self.assertIn(self.company, accessible_companies(self.user))

    def test_user_without_branch_profile_cannot_access_company(self):
        other = User.objects.create_user(email='other@example.com', password='secret123')
        UserCompanyAccess.objects.create(user=other, company=self.company, is_active=True)
        self.assertNotIn(self.company, accessible_companies(other))

    def test_company_access_without_profile_still_memberships(self):
        self.assertTrue(self.user.company_accesses.filter(company=self.company, is_active=True).exists())

    def test_deactivated_branch_access_blocks_company_access(self):
        self.user.branch_accesses.filter(branch=self.matrix).update(is_active=False)
        self.assertNotIn(self.company, accessible_companies(self.user))


class BranchAccessTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = User.objects.create_user(email='owner@example.com', password='secret123')
        self.company = create_company_with_matrix(creator=self.owner, trade_name='Co', legal_name='Co Legal')
        self.user = User.objects.create_user(email='user@example.com', password='secret123')
        self.matrix = self.company.branches.get(is_matrix=True)
        self.admin = _admin_profile(self.company)
        UserCompanyAccess.objects.create(user=self.user, company=self.company, is_active=True)
        UserBranchAccess.objects.create(user=self.user, branch=self.matrix, access_profile=self.admin)

    def test_branch_access_with_profile_grants_permissions(self):
        self.assertIn(self.matrix, accessible_branches(self.user))
        self.assertIn('products.view', branch_permission_codes(self.user, self.matrix.id))

    def test_branch_access_without_company_membership_blocks(self):
        self.user.company_accesses.filter(company=self.company).update(is_active=False)
        self.assertNotIn(self.matrix, accessible_branches(self.user))

    def test_inactive_branch_profile_blocks_permission(self):
        limited = _make_profile(self.company, 'Perfil Limitado', {'products.view'})
        self.user.branch_accesses.filter(branch=self.matrix).update(access_profile=limited)
        limited.status = Status.INACTIVE
        limited.save()
        self.assertNotIn(self.matrix, accessible_branches(self.user))

    def test_user_can_have_different_profiles_per_branch(self):
        branch2 = Branch.objects.create(company=self.company, name='Filial 2')
        profile2 = _make_profile(self.company, 'Perfil Filial 2', {'products.view', 'inventory.view'})
        UserBranchAccess.objects.create(user=self.user, branch=branch2, access_profile=profile2)
        codes_matrix = branch_permission_codes(self.user, self.matrix.id)
        codes_branch2 = branch_permission_codes(self.user, branch2.id)
        self.assertIn('sales.create', codes_matrix)
        self.assertNotIn('sales.create', codes_branch2)
        self.assertIn('inventory.view', codes_branch2)


class OwnerTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = User.objects.create_user(email='owner@example.com', password='secret123')
        self.company = create_company_with_matrix(creator=self.owner, trade_name='Co', legal_name='Co Legal')

    def test_owner_without_company_profile_still_has_access(self):
        access = self.owner.company_accesses.get(company=self.company)
        access.access_profile = None
        access.save(update_fields=['access_profile', 'updated_at'])
        self.assertIn(self.company, accessible_companies(self.owner))

    def test_owner_cannot_be_deactivated(self):
        self.owner.is_active = False
        with self.assertRaises(ValidationError):
            self.owner.save()

    def test_owner_cannot_be_removed(self):
        with self.assertRaises(ValidationError):
            self.owner.delete()

    def test_owner_membership_cannot_be_disabled(self):
        access = self.owner.company_accesses.get(company=self.company)
        access.is_active = False
        with self.assertRaises(ValidationError):
            access.save()

    def test_owner_can_transfer_without_company_profile(self):
        new_owner = User.objects.create_user(email='new@example.com', password='secret123')
        UserCompanyAccess.objects.create(user=new_owner, company=self.company, is_active=True)
        matrix = self.company.branches.get(is_matrix=True)
        admin = _admin_profile(self.company)
        UserBranchAccess.objects.create(user=new_owner, branch=matrix, access_profile=admin)
        from apps.companies.services import transfer_company_owner
        transfer_company_owner(
            company=self.company,
            actor=self.owner,
            target_user_id=new_owner.pk,
            current_password='secret123',
            reason='Transferência de teste',
        )
        access = self.owner.company_accesses.get(company=self.company)
        self.assertFalse(access.is_owner)
        new_access = new_owner.company_accesses.get(company=self.company)
        self.assertTrue(new_access.is_owner)


class DenyOverrideTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = User.objects.create_user(email='owner@example.com', password='secret123')
        self.company = create_company_with_matrix(creator=self.owner, trade_name='Co', legal_name='Co Legal')
        self.user = User.objects.create_user(email='user@example.com', password='secret123')
        self.matrix = self.company.branches.get(is_matrix=True)
        self.admin = _admin_profile(self.company)
        UserCompanyAccess.objects.create(user=self.user, company=self.company, is_active=True)
        UserBranchAccess.objects.create(user=self.user, branch=self.matrix, access_profile=self.admin)

    def test_block_removes_permission(self):
        perm = FunctionalPermission.objects.get(code='products.view')
        UserPermissionBlock.objects.create(
            company=self.company, branch=self.matrix, user=self.user,
            permission=perm, reason='Bloqueio de teste',
        )
        self.assertFalse(user_has_branch_permission(self.user, self.matrix.id, 'products.view'))
        self.assertNotIn('products.view', branch_permission_codes(self.user, self.matrix.id))

    def test_block_does_not_grant_additional_permissions(self):
        perm = FunctionalPermission.objects.get(code='products.view')
        UserPermissionBlock.objects.create(
            company=self.company, branch=self.matrix, user=self.user,
            permission=perm, reason='Teste',
        )
        codes = branch_permission_codes(self.user, self.matrix.id)
        self.assertNotIn('products.view', codes)
        self.assertIn('sales.create', codes)

    def test_company_scope_block_cascades_to_branch(self):
        perm = FunctionalPermission.objects.get(code='products.view')
        UserPermissionBlock.objects.create(
            company=self.company, user=self.user,
            permission=perm, reason='Bloqueio empresa',
        )
        self.assertFalse(user_has_branch_permission(self.user, self.matrix.id, 'products.view'))
        self.assertFalse(user_has_company_permission(self.user, self.company.id, 'products.view'))

    def test_revoke_block_restores_permission(self):
        from django.utils import timezone
        perm = FunctionalPermission.objects.get(code='products.view')
        block = UserPermissionBlock.objects.create(
            company=self.company, branch=self.matrix, user=self.user,
            permission=perm, reason='Teste',
        )
        block.is_active = False
        block.revoked_at = timezone.now()
        block.save(update_fields=['is_active', 'revoked_at', 'updated_at'])
        self.assertTrue(user_has_branch_permission(self.user, self.matrix.id, 'products.view'))


class CrossTenantTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner_a = User.objects.create_user(email='owner.a@example.com', password='secret123')
        self.company_a = create_company_with_matrix(creator=self.owner_a, trade_name='Empresa A', legal_name='A Legal')
        self.owner_b = User.objects.create_user(email='owner.b@example.com', password='secret123')
        self.company_b = create_company_with_matrix(creator=self.owner_b, trade_name='Empresa B', legal_name='B Legal')
        self.user = User.objects.create_user(email='user@example.com', password='secret123')
        self.matrix_a = self.company_a.branches.get(is_matrix=True)
        self.admin_a = _admin_profile(self.company_a)
        UserCompanyAccess.objects.create(user=self.user, company=self.company_a, is_active=True)
        UserBranchAccess.objects.create(user=self.user, branch=self.matrix_a, access_profile=self.admin_a)

    def test_user_cannot_access_company_b(self):
        self.assertNotIn(self.company_b, accessible_companies(self.user))

    def test_user_cannot_access_branch_of_company_b(self):
        matrix_b = self.company_b.branches.get(is_matrix=True)
        self.assertNotIn(matrix_b, accessible_branches(self.user))

    def test_company_permission_codes_do_not_leak_across_tenant(self):
        codes_a = company_permission_codes(self.user, self.company_a.id)
        self.assertTrue(len(codes_a) > 0)
        codes_b = company_permission_codes(self.user, self.company_b.id)
        self.assertEqual(codes_b, set())


class CrossBranchTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = User.objects.create_user(email='owner@example.com', password='secret123')
        self.company = create_company_with_matrix(creator=self.owner, trade_name='Co', legal_name='Co Legal')
        self.user = User.objects.create_user(email='user@example.com', password='secret123')
        self.matrix = self.company.branches.get(is_matrix=True)
        self.branch2 = Branch.objects.create(company=self.company, name='Filial 2')
        self.admin = _admin_profile(self.company)
        self.limited = _make_profile(self.company, 'Limitado', {'products.view'})
        UserCompanyAccess.objects.create(user=self.user, company=self.company, is_active=True)
        UserBranchAccess.objects.create(user=self.user, branch=self.matrix, access_profile=self.admin)

    def test_user_without_access_to_branch2_cannot_see_it(self):
        self.assertNotIn(self.branch2, accessible_branches(self.user))

    def test_user_with_different_profiles_in_different_branches(self):
        UserBranchAccess.objects.create(user=self.user, branch=self.branch2, access_profile=self.limited)
        self.assertIn(self.branch2, accessible_branches(self.user))
        self.assertIn('sales.create', branch_permission_codes(self.user, self.matrix.id))
        self.assertNotIn('sales.create', branch_permission_codes(self.user, self.branch2.id))


class CompanyViewSetAccessTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = User.objects.create_user(email='owner@example.com', password='secret123')
        self.company = create_company_with_matrix(creator=self.owner, trade_name='Co', legal_name='Co Legal')

    def test_non_superuser_cannot_list_companies(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.get('/api/v1/companies/')
        self.assertEqual(response.status_code, 403)

    def test_non_superuser_cannot_create_company(self):
        from rest_framework.test import APIClient
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.post('/api/v1/companies/', {'trade_name': 'X', 'legal_name': 'X Legal'})
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_list_companies(self):
        from rest_framework.test import APIClient
        admin = User.objects.create_superuser(email='admin@example.com', password='secret123')
        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.get('/api/v1/companies/')
        self.assertEqual(response.status_code, 200)


class SoftDeleteTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = User.objects.create_user(email='owner@example.com', password='secret123')
        self.company = create_company_with_matrix(creator=self.owner, trade_name='Co', legal_name='Co Legal')

    def test_user_delete_archives_instead_of_hard_delete(self):
        user = User.objects.create_user(email='temp@example.com', password='secret123')
        uid = user.pk
        user.delete()
        self.assertTrue(User.objects.filter(pk=uid, is_active=False, archived_at__isnull=False).exists())
