from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.base.models import AuditLog
from apps.companies.models import AccessProfile, UserBranchAccess, UserCompanyAccess
from apps.companies.services import create_company_with_matrix, ensure_permission_catalog


PASSWORD = 'Mission-M1.1-Secure-123!'


class MultiCompanyUserTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner_a = User.objects.create_user(email='owner.a.m11@example.com', password=PASSWORD)
        self.company_a = create_company_with_matrix(creator=self.owner_a, trade_name='Empresa A M11', legal_name='Empresa A M11 Legal')
        self.branch_a = self.company_a.branches.get(is_matrix=True)
        self.profile_a = AccessProfile.objects.get(company=self.company_a, name='Administrador', is_system=True)
        self.owner_b = User.objects.create_user(email='owner.b.m11@example.com', password=PASSWORD)
        self.company_b = create_company_with_matrix(creator=self.owner_b, trade_name='Empresa B M11', legal_name='Empresa B M11 Legal')
        self.branch_b = self.company_b.branches.get(is_matrix=True)
        self.profile_b = AccessProfile.objects.get(company=self.company_b, name='Administrador', is_system=True)
        self.david = User.objects.create_user(email='david.m11@example.com', password=PASSWORD, first_name='David', last_name='Silva')
        self.access_a = UserCompanyAccess.objects.create(user=self.david, company=self.company_a, is_active=True)
        self.access_b = UserCompanyAccess.objects.create(user=self.david, company=self.company_b, is_active=True)
        self.branch_access_a = UserBranchAccess.objects.create(user=self.david, branch=self.branch_a, access_profile=self.profile_a)
        self.branch_access_b = UserBranchAccess.objects.create(user=self.david, branch=self.branch_b, access_profile=self.profile_b)
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner_a)
        self.client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch_a.pk)

    def url(self, suffix=''):
        return f'/api/v1/users/{self.david.pk}/{suffix}?company={self.company_a.pk}'

    def test_detail_and_edit_are_scoped_to_company_a(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['membership']['company_id'], self.company_a.pk)
        self.assertEqual([company['id'] for company in response.data['companies']], [self.company_a.pk])
        self.assertNotIn(self.branch_b.pk, [branch['id'] for branch in response.data['branches']])

        b_membership_before = self.access_b.updated_at
        b_branch_before = self.branch_access_b.updated_at
        response = self.client.patch(self.url(), {
            'first_name': 'David A',
            'company_accesses': [{
                'company_id': self.company_a.pk,
                'access_profile_id': None,
                'branch_accesses': [{
                    'branch_id': self.branch_a.pk,
                    'access_profile_id': self.profile_a.pk,
                }],
            }],
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.access_b.refresh_from_db()
        self.branch_access_b.refresh_from_db()
        self.assertEqual(self.access_b.updated_at, b_membership_before)
        self.assertEqual(self.branch_access_b.updated_at, b_branch_before)
        self.assertTrue(self.access_b.is_active)
        self.assertTrue(self.branch_access_b.is_active)
        audit = AuditLog.objects.filter(action='user.update', company=self.company_a, object_id=str(self.david.pk)).latest('id')
        self.assertEqual(
            {item['company_id'] for item in audit.after['company_accesses']},
            {self.company_a.pk},
        )
        self.assertNotIn(
            self.branch_b.pk,
            {item['branch_id'] for item in audit.after['branch_accesses']},
        )

    def test_company_a_cannot_submit_company_b_membership(self):
        response = self.client.patch(self.url(), {
            'company_accesses': [{
                'company_id': self.company_b.pk,
                'access_profile_id': None,
                'branch_accesses': [{
                    'branch_id': self.branch_b.pk,
                    'access_profile_id': self.profile_b.pk,
                }],
            }],
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_company_b_can_edit_its_own_membership(self):
        client = APIClient()
        client.force_authenticate(user=self.owner_b)
        client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch_b.pk)
        response = client.patch(f'/api/v1/users/{self.david.pk}/?company={self.company_b.pk}', {
            'company_accesses': [{
                'company_id': self.company_b.pk,
                'access_profile_id': None,
                'branch_accesses': [{
                    'branch_id': self.branch_b.pk,
                    'access_profile_id': self.profile_b.pk,
                }],
            }],
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['membership']['company_id'], self.company_b.pk)
        self.access_a.refresh_from_db()
        self.assertTrue(self.access_a.is_active)

    def test_deactivate_and_activate_change_only_company_a(self):
        response = self.client.post(self.url('deactivate/'))
        self.assertEqual(response.status_code, 200, response.data)
        self.access_a.refresh_from_db()
        self.access_b.refresh_from_db()
        self.david.refresh_from_db()
        self.assertFalse(self.access_a.is_active)
        self.assertTrue(self.access_b.is_active)
        self.assertTrue(self.david.is_active)
        self.assertTrue(self.david.check_password(PASSWORD))
        response = self.client.get(f'/api/v1/users/?company={self.company_a.pk}&status=inactive')
        self.assertIn(self.david.pk, [item['id'] for item in response.data['results']])

        response = self.client.post(self.url('activate/'))
        self.assertEqual(response.status_code, 200, response.data)
        self.access_a.refresh_from_db()
        self.access_b.refresh_from_db()
        self.assertTrue(self.access_a.is_active)
        self.assertTrue(self.access_b.is_active)

    def test_password_reset_works_in_context_without_touching_memberships(self):
        new_password = 'Mission-M1.1-New-456!'
        response = self.client.post(self.url('reset-password/'), {'new_password': new_password}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.david.refresh_from_db()
        self.access_a.refresh_from_db()
        self.access_b.refresh_from_db()
        self.assertTrue(self.david.check_password(new_password))
        self.assertTrue(self.access_a.is_active)
        self.assertTrue(self.access_b.is_active)
        audit = AuditLog.objects.filter(action='user.reset_password', company=self.company_a, object_id=str(self.david.pk)).latest('id')
        self.assertNotIn(new_password, str(audit.before) + str(audit.after) + str(audit.metadata))

    def test_user_without_membership_in_current_company_remains_blocked(self):
        owner_c = User.objects.create_user(
            email='owner.c.m11@example.com', password=PASSWORD
        )
        company_c = create_company_with_matrix(
            creator=owner_c,
            trade_name='Empresa C M11',
            legal_name='Empresa C M11 Legal',
        )
        branch_c = company_c.branches.get(is_matrix=True)
        client = APIClient()
        client.force_authenticate(owner_c)
        client.defaults['HTTP_X_BRANCH_ID'] = str(branch_c.pk)

        response = client.post(
            f'/api/v1/users/{self.david.pk}/deactivate/?company={company_c.pk}'
        )
        self.assertIn(response.status_code, (403, 404), response.data)
        self.access_a.refresh_from_db()
        self.access_b.refresh_from_db()
        self.assertTrue(self.access_a.is_active)
        self.assertTrue(self.access_b.is_active)
