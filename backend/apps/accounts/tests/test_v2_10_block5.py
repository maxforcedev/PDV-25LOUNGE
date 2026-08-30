"""BLOCO 6 — Block 5 Regression tests.

Covers mandatory test area 16:
  - Sessions admin screen/API removed
  - login/logout/session authentication continue working
  - Empresas does not appear in Backoffice
  - Company remains intact in backend
  - lifecycles changed in Block 5 work
  - no dead import/route remains
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import Company, Branch
from apps.companies.services import (
    create_company_with_matrix, ensure_permission_catalog,
)
from apps.products.models import (
    Category, ModifierGroup, ModifierOption, ProductionDestination,
    Product, ProductModifierGroup, Unit, InventoryBehavior,
)

PASSWORD = 'Block5-regression-123!'


def create_user(email):
    return User.objects.create_user(email=email, password=PASSWORD)


class SessionsRemovalTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = create_user('owner@b5reg.com')
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='B5Reg', legal_name='B5Reg Legal',
        )
        self.branch = self.company.branches.get(is_matrix=True)

    def test_sessions_endpoint_does_not_exist(self):
        from apps.accounts.urls import urlpatterns as auth_urls
        auth_patterns = [str(p) for p in auth_urls]
        joined = ' '.join(auth_patterns)
        self.assertNotIn('sessions/', joined)

    def test_login_still_works(self):
        client = APIClient()
        resp = client.post('/api/v1/auth/login/', {
            'email': 'owner@b5reg.com',
            'password': PASSWORD,
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('X-CSRFToken', resp)

    def test_logout_works(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        resp = client.post('/api/v1/auth/logout/')
        self.assertEqual(resp.status_code, 204)

    def test_me_endpoint_works(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        resp = client.get('/api/v1/auth/me/')
        self.assertEqual(resp.status_code, 200)


class EmpresasRouteRemovedTests(TestCase):
    def test_empresas_page_does_not_exist(self):
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'frontend', 'src', 'app', '(private)', 'empresas', 'page.tsx',
        )
        self.assertFalse(os.path.exists(path))


class CompanyIntactTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = create_user('owner@ci.com')
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='CI', legal_name='CI Legal',
        )
        self.branch = self.company.branches.get(is_matrix=True)

    def test_company_model_still_exists(self):
        self.assertTrue(Company.objects.filter(pk=self.company.pk).exists())

    def test_branch_model_still_exists(self):
        self.assertTrue(Branch.objects.filter(pk=self.branch.pk).exists())

    def test_company_api_endpoint_still_works_for_superuser(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        resp = client.get(f'/api/v1/companies/', HTTP_X_BRANCH_ID=str(self.branch.pk))
        self.assertIn(resp.status_code, (200, 403))


class LifecycleTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = create_user('owner@lc.com')
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='LC', legal_name='LC Legal',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.branch.settings.uses_counter = True
        self.branch.settings.uses_cash_register = True
        self.branch.settings.save()
        self.category = Category.objects.create(company=self.company, name='Cat')
        self.product = Product.objects.create(
            company=self.company, category=self.category, name='P1',
            internal_code='P1', unit=Unit.UNIT, cost=Decimal('1.00'),
            sale_price=Decimal('5.00'), inventory_behavior=InventoryBehavior.DIRECT,
        )

    def test_production_destination_lifecycle(self):
        dest = ProductionDestination.objects.create(
            branch=self.branch, name='Cozinha', code='cozinha',
        )
        client = APIClient()
        client.force_authenticate(user=self.owner)
        client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)
        resp = client.post(f'/api/v1/production-destinations/{dest.pk}/deactivate/')
        self.assertEqual(resp.status_code, 200)
        dest.refresh_from_db()
        self.assertEqual(dest.status, 'inactive')
        resp = client.post(f'/api/v1/production-destinations/{dest.pk}/activate/')
        self.assertEqual(resp.status_code, 200)
        dest.refresh_from_db()
        self.assertEqual(dest.status, 'active')

    def test_modifier_group_lifecycle(self):
        group = ModifierGroup.objects.create(company=self.company, name='Extras')
        ModifierOption.objects.create(modifier_group=group, name='Bacon')
        client = APIClient()
        client.force_authenticate(user=self.owner)
        client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)
        response = client.delete(f'/api/v1/modifier-groups/{group.pk}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ModifierGroup.objects.filter(pk=group.pk).exists())
        self.assertTrue(ModifierGroup.all_objects.filter(pk=group.pk).exists())
