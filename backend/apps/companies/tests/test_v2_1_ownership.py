import importlib
from io import StringIO

from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.base.models import AuditLog
from apps.companies.models import (
    AccessProfile, Branch, Company, Status, UserBranchAccess, UserCompanyAccess,
)
from apps.companies.selectors import accessible_branches, accessible_companies
from apps.companies.serializers import CompanySerializer
from apps.companies.services import (
    create_company_with_matrix,
    replace_user_accesses,
    transfer_company_owner,
)


def create_user(email):
    return User.objects.create_user(email=email, password='owner-password')


def create_company(name):
    return Company.objects.create(trade_name=name, legal_name=f'{name} Legal')


def administrator_profile(company):
    return AccessProfile.objects.get(
        company=company, name='Administrador', is_system=True
    )


class CompanyIdentityTests(TestCase):
    def test_duplicate_names_are_allowed_but_cnpj_remains_unique(self):
        first = Company.objects.create(
            trade_name='Mesmo Nome',
            legal_name='Mesma Razao',
            cnpj='11222333000181',
        )
        second = Company.objects.create(
            trade_name='mesmo nome',
            legal_name='mesma razao',
            cnpj='04252011000110',
        )
        self.assertNotEqual(first.pk, second.pk)

        with self.assertRaises(ValidationError):
            Company.objects.create(
                trade_name='Terceira',
                legal_name='Terceira Legal',
                cnpj='11222333000181',
            )

    def test_serializer_does_not_reject_duplicate_names(self):
        Company.objects.create(
            trade_name='Nome Livre',
            legal_name='Razao Livre',
            cnpj='11222333000181',
        )
        serializer = CompanySerializer(data={
            'trade_name': 'nome livre',
            'legal_name': 'razao livre',
            'cnpj': '04.252.011/0001-10',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

        duplicate_cnpj = CompanySerializer(data={
            'trade_name': 'Outro Nome',
            'legal_name': 'Outra Razao',
            'cnpj': '11.222.333/0001-81',
        })
        self.assertFalse(duplicate_cnpj.is_valid())
        self.assertIn('cnpj', duplicate_cnpj.errors)


class OwnershipInvariantTests(TestCase):
    def setUp(self):
        self.owner = create_user('owner@example.com')
        self.company = create_company('Empresa A')
        self.profile = administrator_profile(self.company)
        self.matrix = Branch.objects.create(company=self.company, name='Matriz')
        self.access = UserCompanyAccess.objects.create(
            user=self.owner,
            company=self.company,
            access_profile=self.profile,
            is_owner=True,
        )
        UserBranchAccess.objects.create(
            user=self.owner,
            branch=self.matrix,
            access_profile=self.profile,
        )

    def test_company_creator_becomes_owner(self):
        creator = create_user('creator@example.com')
        company = create_company_with_matrix(
            creator=creator,
            trade_name='Criada',
            legal_name='Criada Legal',
        )
        access = UserCompanyAccess.objects.get(company=company, user=creator)
        self.assertTrue(access.is_owner)
        self.assertTrue(access.is_active)

    def test_only_one_owner_is_allowed(self):
        other = create_user('other@example.com')
        with self.assertRaises(ValidationError):
            UserCompanyAccess.objects.create(
                user=other,
                company=self.company,
                access_profile=self.profile,
                is_owner=True,
            )

    def test_owner_membership_and_user_cannot_be_disabled_or_removed(self):
        self.access.is_active = False
        with self.assertRaises(ValidationError):
            self.access.save()

        self.access.is_active = True
        self.access.access_profile = None
        self.access.save()

        self.access.access_profile = self.profile
        with self.assertRaises(ValidationError):
            self.access.delete()

        self.owner.is_active = False
        with self.assertRaises(ValidationError):
            self.owner.save()
        self.owner.is_active = True
        self.owner.can_login = False
        with self.assertRaises(ValidationError):
            self.owner.save()

    def test_bulk_operations_cannot_bypass_owner_protection(self):
        with self.assertRaises(ValidationError):
            UserCompanyAccess.objects.filter(pk=self.access.pk).update(is_owner=False)
        with self.assertRaises(ValidationError):
            UserCompanyAccess.objects.filter(pk=self.access.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            UserCompanyAccess.objects.filter(pk=self.access.pk).delete()
        with self.assertRaises(ValidationError):
            User.objects.filter(pk=self.owner.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            User.objects.filter(pk=self.owner.pk).delete()
        with self.assertRaises(ValidationError):
            AccessProfile.objects.filter(pk=self.profile.pk).update(
                status=Status.INACTIVE
            )

        self.access.refresh_from_db()
        self.owner.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertTrue(self.access.is_owner)
        self.assertTrue(self.access.is_active)
        self.assertTrue(self.owner.is_active)
        self.assertEqual(self.profile.status, Status.ACTIVE)

    def test_owner_access_cannot_be_omitted_or_profile_cleared_by_service(self):
        with self.assertRaises(ValidationError):
            replace_user_accesses(user=self.owner, company_accesses=[])

        replace_user_accesses(user=self.owner, company_accesses=[{
            'company': self.company,
            'access_profile': None,
            'branch_accesses': [
                {'branch': self.matrix, 'access_profile': self.profile},
            ],
        }])

    def test_owner_profile_cannot_be_deactivated(self):
        self.profile.status = Status.INACTIVE
        with self.assertRaises(ValidationError):
            self.profile.save()

    def test_existing_user_api_paths_cannot_disable_owner(self):
        actor = User.objects.create_superuser(
            email='platform@example.com', password='owner-password'
        )
        client = APIClient()
        client.force_authenticate(actor)

        response = client.post(reverse('user-deactivate', args=[self.owner.pk]))
        self.assertEqual(response.status_code, 400, response.data)
        response = client.patch(
            reverse('user-detail', args=[self.owner.pk]),
            {'can_login': False},
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)
        self.assertTrue(self.owner.can_login)


class TenantIsolationTests(TestCase):
    def test_company_and_branch_selectors_remain_isolated(self):
        user = create_user('tenant-a@example.com')
        first = create_company_with_matrix(
            creator=user,
            trade_name='Tenant A',
            legal_name='Tenant A Legal',
        )
        outsider = create_user('tenant-b@example.com')
        second = create_company_with_matrix(
            creator=outsider,
            trade_name='Tenant B',
            legal_name='Tenant B Legal',
        )

        self.assertQuerySetEqual(
            accessible_companies(user, 'companies.view'),
            [first],
        )
        self.assertQuerySetEqual(
            accessible_branches(user, 'branches.view'),
            list(first.branches.all()),
            ordered=False,
        )
        self.assertFalse(
            accessible_companies(user).filter(pk=second.pk).exists()
        )
        self.assertFalse(
            accessible_branches(user).filter(company=second).exists()
        )


class OwnerBackfillTests(TestCase):
    def test_backfill_promotes_only_exactly_one_eligible_administrator(self):
        no_candidate = create_company('Sem Candidato')
        one_candidate = create_company('Um Candidato')
        many_candidates = create_company('Muitos Candidatos')

        inactive_user = create_user('inactive@example.com')
        inactive_user.is_active = False
        inactive_user.save()
        UserCompanyAccess.objects.create(
            user=inactive_user,
            company=no_candidate,
            access_profile=administrator_profile(no_candidate),
        )
        one_user = create_user('one@example.com')
        UserCompanyAccess.objects.create(
            user=one_user,
            company=one_candidate,
            access_profile=administrator_profile(one_candidate),
        )
        for index in range(2):
            UserCompanyAccess.objects.create(
                user=create_user(f'many{index}@example.com'),
                company=many_candidates,
                access_profile=administrator_profile(many_candidates),
            )

        migration = importlib.import_module(
            'apps.companies.migrations.0027_v2_1_company_ownership'
        )
        migration.promote_unambiguous_company_owners(apps, None)

        self.assertFalse(
            UserCompanyAccess.objects.filter(company=no_candidate, is_owner=True).exists()
        )
        self.assertEqual(
            UserCompanyAccess.objects.get(company=one_candidate, is_owner=True).user,
            one_user,
        )
        self.assertFalse(
            UserCompanyAccess.objects.filter(company=many_candidates, is_owner=True).exists()
        )

    def test_backfill_does_not_ignore_disabled_candidate_when_counting_ambiguity(self):
        company = create_company('Candidatos Mistos')
        profile = administrator_profile(company)
        UserCompanyAccess.objects.create(
            user=create_user('enabled@example.com'),
            company=company,
            access_profile=profile,
        )
        disabled = create_user('disabled@example.com')
        disabled.is_active = False
        disabled.save()
        UserCompanyAccess.objects.create(
            user=disabled,
            company=company,
            access_profile=profile,
        )

        migration = importlib.import_module(
            'apps.companies.migrations.0027_v2_1_company_ownership'
        )
        migration.promote_unambiguous_company_owners(apps, None)

        self.assertFalse(
            UserCompanyAccess.objects.filter(company=company, is_owner=True).exists()
        )


class AssignCompanyOwnerCommandTests(TestCase):
    def setUp(self):
        self.company = create_company('Pendente')
        self.user = create_user('pending-owner@example.com')
        self.matrix = Branch.objects.create(company=self.company, name='Matriz')
        self.profile = administrator_profile(self.company)
        self.access = UserCompanyAccess.objects.create(
            user=self.user,
            company=self.company,
            access_profile=self.profile,
        )
        UserBranchAccess.objects.create(
            user=self.user,
            branch=self.matrix,
            access_profile=self.profile,
        )

    def test_lists_pending_and_assignment_is_idempotent(self):
        output = StringIO()
        call_command('assign_company_owner', stdout=output)
        self.assertIn(f'{self.company.pk}\t{self.company.trade_name}', output.getvalue())

        call_command(
            'assign_company_owner',
            company_id=self.company.pk,
            user_id=self.user.pk,
            stdout=StringIO(),
        )
        self.access.refresh_from_db()
        self.assertTrue(self.access.is_owner)
        audit_count = AuditLog.objects.filter(action='company.owner.assign').count()

        call_command(
            'assign_company_owner',
            company_id=self.company.pk,
            user_id=self.user.pk,
            stdout=StringIO(),
        )
        self.assertEqual(
            AuditLog.objects.filter(action='company.owner.assign').count(), audit_count
        )

    def test_refuses_owner_replacement(self):
        call_command(
            'assign_company_owner',
            company_id=self.company.pk,
            user_id=self.user.pk,
            stdout=StringIO(),
        )
        other = create_user('replacement@example.com')
        UserCompanyAccess.objects.create(
            user=other,
            company=self.company,
            access_profile=self.profile,
        )
        UserBranchAccess.objects.create(
            user=other,
            branch=self.matrix,
            access_profile=self.profile,
        )
        with self.assertRaises(CommandError):
            call_command(
                'assign_company_owner',
                company_id=self.company.pk,
                user_id=other.pk,
            )


class OwnerTransferTests(TestCase):
    def setUp(self):
        self.owner = create_user('current@example.com')
        self.target = create_user('target@example.com')
        self.company = create_company('Transferivel')
        profile = administrator_profile(self.company)
        self.matrix = Branch.objects.create(company=self.company, name='Matriz')
        self.current_access = UserCompanyAccess.objects.create(
            user=self.owner,
            company=self.company,
            access_profile=profile,
            is_owner=True,
        )
        UserBranchAccess.objects.create(
            user=self.owner,
            branch=self.matrix,
            access_profile=profile,
        )
        self.target_access = UserCompanyAccess.objects.create(
            user=self.target,
            company=self.company,
            access_profile=profile,
        )
        UserBranchAccess.objects.create(
            user=self.target,
            branch=self.matrix,
            access_profile=profile,
        )

    def test_transfer_requires_reauthentication_and_writes_explicit_audit(self):
        with self.assertRaises(ValidationError):
            transfer_company_owner(
                company=self.company,
                actor=self.owner,
                target_user_id=self.target.pk,
                current_password='wrong-password',
                reason='Sucessão administrativa',
            )
        with self.assertRaises(ValidationError):
            transfer_company_owner(
                company=self.company,
                actor=self.owner,
                target_user_id=self.target.pk,
                current_password='owner-password',
                reason=' ',
            )

        transfer_company_owner(
            company=self.company,
            actor=self.owner,
            target_user_id=self.target.pk,
            current_password='owner-password',
            reason='Sucessão administrativa',
        )
        self.current_access.refresh_from_db()
        self.target_access.refresh_from_db()
        self.assertFalse(self.current_access.is_owner)
        self.assertTrue(self.target_access.is_owner)
        log = AuditLog.objects.get(action='company.owner.transfer')
        self.assertEqual(log.actor, self.owner)
        self.assertEqual(log.before['user_id'], self.owner.pk)
        self.assertEqual(log.after['user_id'], self.target.pk)
        self.assertEqual(log.metadata['reason'], 'Sucessão administrativa')

    def test_transfer_requires_current_owner_and_active_target(self):
        with self.assertRaises(ValidationError):
            transfer_company_owner(
                company=self.company,
                actor=self.target,
                target_user_id=self.owner.pk,
                current_password='owner-password',
                reason='Ator inválido',
            )

        self.target_access.is_active = False
        self.target_access.save()
        with self.assertRaises(ValidationError):
            transfer_company_owner(
                company=self.company,
                actor=self.owner,
                target_user_id=self.target.pk,
                current_password='owner-password',
                reason='Destino inválido',
            )

    def test_transfer_api_returns_owner_summary(self):
        client = APIClient()
        client.force_authenticate(self.owner)
        response = client.post(
            reverse('company-transfer-owner', args=[self.company.pk]),
            {
                'target_user_id': self.target.pk,
                'current_password': 'owner-password',
                'reason': 'Mudança de controle',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['owner']['user_id'], self.target.pk)

    def test_transfer_api_is_tenant_isolated(self):
        other_owner = create_user('other-owner@example.com')
        other_target = create_user('other-target@example.com')
        other_company = create_company('Outra Empresa')
        profile = administrator_profile(other_company)
        UserCompanyAccess.objects.create(
            user=other_owner,
            company=other_company,
            access_profile=profile,
            is_owner=True,
        )
        UserCompanyAccess.objects.create(
            user=other_target,
            company=other_company,
            access_profile=profile,
        )

        client = APIClient()
        client.force_authenticate(self.owner)
        response = client.post(
            reverse('company-transfer-owner', args=[other_company.pk]),
            {
                'target_user_id': other_target.pk,
                'current_password': 'owner-password',
                'reason': 'Tentativa fora do tenant',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            UserCompanyAccess.objects.get(company=other_company, user=other_owner).is_owner
        )
