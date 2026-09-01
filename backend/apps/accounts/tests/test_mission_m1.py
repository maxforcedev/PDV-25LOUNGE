import shutil
import tempfile
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.base.models import AuditLog
from apps.companies.models import AccessProfile, Branch, UserBranchAccess, UserCompanyAccess
from apps.companies.services import create_company_with_matrix, ensure_permission_catalog


PASSWORD = 'Mission-M1-Secure-123!'


class MissionM1Tests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_media = tempfile.mkdtemp()
        cls.settings_override = override_settings(PRIVATE_MEDIA_ROOT=cls.private_media)
        cls.settings_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings_override.disable()
        shutil.rmtree(cls.private_media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        ensure_permission_catalog()
        self.owner = User.objects.create_user(email='owner.m1@example.com', password=PASSWORD)
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='Empresa M1', legal_name='Empresa M1 Legal',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.admin_profile = AccessProfile.objects.get(
            company=self.company, name='Administrador', is_system=True,
        )
        self.target = User.objects.create_user(email='target.m1@example.com', password=PASSWORD)
        UserCompanyAccess.objects.create(user=self.target, company=self.company, is_active=True)
        UserBranchAccess.objects.create(user=self.target, branch=self.branch, access_profile=self.admin_profile)
        self.client = APIClient()

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.owner)
        self.client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)

    def test_self_profile_optional_fields_and_photo_lifecycle(self):
        self.authenticate(self.target)
        photo = SimpleUploadedFile('avatar.png', b'\x89PNG\r\n\x1a\ncontent', content_type='image/png')
        response = self.client.patch('/api/v1/auth/me/', {
            'first_name': 'Maria', 'last_name': 'Silva', 'birth_date': '1990-05-20',
            'cpf': '123.456.789-00', 'zip_code': '12345-678', 'street': 'Rua Um',
            'address_number': '10', 'address_complement': 'Sala 2',
            'neighborhood': 'Centro', 'city': 'Sao Paulo', 'state': 'sp',
            'profile_photo': photo,
        }, format='multipart')
        self.assertEqual(response.status_code, 200, response.data)
        self.target.refresh_from_db()
        self.assertEqual(self.target.birth_date, date(1990, 5, 20))
        self.assertEqual(self.target.cpf, '12345678900')
        self.assertEqual(self.target.zip_code, '12345678')
        self.assertEqual(self.target.state, 'SP')
        self.assertTrue(self.target.profile_photo.name)
        self.assertEqual(self.client.get('/api/v1/auth/me/photo/').status_code, 200)
        self.assertEqual(self.client.delete('/api/v1/auth/me/photo/').status_code, 204)
        self.target.refresh_from_db()
        self.assertFalse(self.target.profile_photo)

    def test_profile_photo_rejects_fake_content_and_unsafe_type(self):
        self.authenticate(self.target)
        response = self.client.patch('/api/v1/auth/me/', {
            'profile_photo': SimpleUploadedFile('avatar.exe', b'not-image', content_type='application/octet-stream'),
        }, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('profile_photo', response.data)

    def test_admin_reset_password_route_succeeds_without_auditing_password(self):
        self.authenticate()
        new_password = 'Another-M1-Secure-456!'
        response = self.client.post(
            f'/api/v1/users/{self.target.pk}/reset-password/?company={self.company.pk}',
            {'new_password': new_password}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password(new_password))
        audit = AuditLog.objects.filter(action='user.reset_password', object_id=str(self.target.pk)).latest('id')
        self.assertNotIn(new_password, str(audit.before) + str(audit.after) + str(audit.metadata))

    def test_active_inactive_archive_filters_and_last_login(self):
        self.authenticate()
        self.target.last_login = timezone.now()
        self.target.save(update_fields=['last_login', 'updated_at'])
        response = self.client.post(f'/api/v1/users/{self.target.pk}/deactivate/?company={self.company.pk}')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['membership']['is_active'])
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        response = self.client.post(f'/api/v1/users/{self.target.pk}/activate/?company={self.company.pk}')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['membership']['is_active'])
        self.assertIsNotNone(response.data['last_login'])
        response = self.client.post(f'/api/v1/users/{self.target.pk}/archive/?company={self.company.pk}')
        self.assertEqual(response.status_code, 200, response.data)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertIsNotNone(self.target.archived_at)
        active_ids = {item['id'] for item in self.client.get(f'/api/v1/users/?company={self.company.pk}&status=active').data['results']}
        inactive_ids = {item['id'] for item in self.client.get(f'/api/v1/users/?company={self.company.pk}&status=inactive').data['results']}
        all_ids = {item['id'] for item in self.client.get(f'/api/v1/users/?company={self.company.pk}&status=all').data['results']}
        self.assertNotIn(self.target.pk, active_ids)
        self.assertNotIn(self.target.pk, inactive_ids)
        self.assertNotIn(self.target.pk, all_ids)

    def test_queryset_delete_also_preserves_user_history(self):
        target_id = self.target.pk
        deleted, _ = User.objects.filter(pk=target_id).delete()
        self.assertEqual(deleted, 1)
        self.assertTrue(User.objects.filter(pk=target_id, is_active=False, archived_at__isnull=False).exists())

    def test_tenant_and_branch_assignment_isolation(self):
        other_owner = User.objects.create_user(email='other.owner.m1@example.com', password=PASSWORD)
        other_company = create_company_with_matrix(
            creator=other_owner, trade_name='Outra M1', legal_name='Outra M1 Legal',
        )
        other_target = User.objects.create_user(email='other.target.m1@example.com', password=PASSWORD)
        UserCompanyAccess.objects.create(user=other_target, company=other_company, is_active=True)
        other_branch = other_company.branches.get(is_matrix=True)
        other_profile = AccessProfile.objects.get(company=other_company, name='Administrador', is_system=True)
        UserBranchAccess.objects.create(user=other_target, branch=other_branch, access_profile=other_profile)
        self.authenticate()
        self.assertEqual(self.client.get(f'/api/v1/users/{other_target.pk}/').status_code, 404)
        response = self.client.patch(f'/api/v1/users/{self.target.pk}/', {
            'company_accesses': [{
                'company_id': self.company.pk,
                'access_profile_id': None,
                'branch_accesses': [{'branch_id': other_branch.pk, 'access_profile_id': other_profile.pk}],
            }],
        }, format='json')
        self.assertIn(response.status_code, (400, 403))

        manager = User.objects.create_user(email='manager.m1@example.com', password=PASSWORD)
        UserCompanyAccess.objects.create(
            user=manager, company=self.company, access_profile=self.admin_profile, is_active=True,
        )
        UserBranchAccess.objects.create(
            user=manager, branch=self.branch, access_profile=self.admin_profile,
        )
        hidden_branch = Branch.objects.create(company=self.company, name='Filial restrita')
        hidden_target = User.objects.create_user(email='hidden.m1@example.com', password=PASSWORD)
        UserCompanyAccess.objects.create(user=hidden_target, company=self.company, is_active=True)
        UserBranchAccess.objects.create(
            user=hidden_target, branch=hidden_branch, access_profile=self.admin_profile,
        )
        self.authenticate(manager)
        response = self.client.patch(
            f'/api/v1/users/{hidden_target.pk}/', {
                'company_accesses': [{
                    'company_id': self.company.pk,
                    'access_profile_id': None,
                    'branch_accesses': [{
                        'branch_id': hidden_branch.pk,
                        'access_profile_id': self.admin_profile.pk,
                    }],
                }],
            }, format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_user_scoped_block_options_do_not_lose_target(self):
        self.authenticate()
        response = self.client.get(
            f'/api/v1/user-permission-blocks/options/?company={self.company.pk}&user={self.target.pk}'
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(self.target.pk, [item['id'] for item in response.data['users']])
        self.assertTrue(response.data['permissions'])
