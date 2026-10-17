import uuid

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import (
    AccessProfile, Branch, FunctionalPermission, UserBranchAccess, UserCompanyAccess,
)

from ..models import (
    StockTransfer, StockTransferItem, StockTransferStatus, TransferCostSource, TransferDivergence,
    TransferDivergenceStatus,
)
from .test_v2_5_inventory import fixture


class TransferPermissionAlternativeTests(TestCase):
    """Alternative workflow permissions must retain their own read scopes."""

    def setUp(self):
        self.company, self.origin, self.destination, self.product, self.owner = fixture('V25RBAC')
        self.unrelated_origin = Branch.objects.create(company=self.company, name='Sem acesso origem')
        self.unrelated_destination = Branch.objects.create(company=self.company, name='Sem acesso destino')
        self.draft = self.transfer(self.origin, self.destination)
        self.dispatched = self.transfer(self.origin, self.destination, StockTransferStatus.IN_TRANSIT)
        self.receivable = self.transfer(self.origin, self.destination, StockTransferStatus.IN_TRANSIT)
        self.unrelated = self.transfer(self.unrelated_origin, self.unrelated_destination)
        item = StockTransferItem.objects.create(
            transfer=self.receivable,
            product=self.product,
            requested_quantity='1',
            dispatched_quantity='1',
            origin_unit_cost_snapshot='1',
            origin_cost_source=TransferCostSource.PRODUCT_FALLBACK,
            origin_sale_price_snapshot='1',
            product_name_snapshot=self.product.name,
            product_internal_code_snapshot=self.product.internal_code,
            product_unit_snapshot=self.product.unit,
        )
        self.divergence = TransferDivergence.objects.create(
            transfer_item=item,
            dispatched_quantity_snapshot='1',
            received_quantity_snapshot='0',
            initial_quantity='1',
            resolved_quantity='0',
            pending_quantity='1',
            status=TransferDivergenceStatus.PENDING,
            detected_by=self.owner,
            detected_at=timezone.now(),
        )
        other_company, other_origin, other_destination, _, other_owner = fixture('V25RBACOther')
        self.other_transfer = StockTransfer.objects.create(
            company=other_company,
            origin_branch=other_origin,
            destination_branch=other_destination,
            created_by=other_owner,
        )

    def transfer(self, origin, destination, status=StockTransferStatus.DRAFT, created_by=None):
        transfer = StockTransfer.objects.create(
            company=self.company,
            origin_branch=origin,
            destination_branch=destination,
            created_by=created_by or self.owner,
        )
        if status != StockTransferStatus.DRAFT:
            # Preserve the protected model's audited transition invariants.
            transfer.status = status
            transfer.dispatched_by = self.owner
            transfer.dispatched_at = timezone.now()
            transfer.dispatch_idempotency_key = uuid.uuid4()
            transfer.dispatch_payload_fingerprint = '0' * 64
            transfer.dispatch_payload = {'fixture': True}
            transfer._allow_status_transition = True
            transfer.save()
        return transfer

    def client_with(self, code, branch):
        user = User.objects.create_user(
            email=f'{code.replace(".", "-")}-{branch.pk}-{User.objects.count()}@example.com',
            password='Inventory-Permissions-123!',
        )
        profile = AccessProfile.objects.create(
            company=self.company,
            name=f'{code} {branch.pk} {user.pk}',
        )
        profile.permissions.add(FunctionalPermission.objects.get(code=code))
        UserCompanyAccess.objects.create(user=user, company=self.company, access_profile=profile)
        UserBranchAccess.objects.create(user=user, branch=branch, access_profile=profile)
        client = APIClient()
        client.force_authenticate(user)
        return user, client

    def test_each_transfer_permission_can_list_retrieve_and_reach_its_workflow(self):
        cases = (
            ('inventory.transfer.view', self.origin, self.dispatched, None),
            ('inventory.transfer.create', self.origin, None, 'create'),
            ('inventory.transfer.dispatch', self.origin, self.draft, 'dispatch'),
            ('inventory.transfer.receive', self.destination, self.receivable, 'receive'),
        )
        for code, branch, transfer, action in cases:
            with self.subTest(code=code):
                user, client = self.client_with(code, branch)
                if action == 'create':
                    transfer = self.transfer(self.origin, self.destination, created_by=user)
                headers = {'HTTP_X_BRANCH_ID': str(branch.pk)}
                listed = client.get(reverse('stock-transfer-list'), **headers)
                self.assertEqual(listed.status_code, 200, listed.data)
                self.assertIn(str(transfer.pk), [item['id'] for item in listed.data['results']])
                detail = client.get(reverse('stock-transfer-detail', args=[transfer.pk]), **headers)
                self.assertEqual(detail.status_code, 200, detail.data)
                hidden = client.get(reverse('stock-transfer-detail', args=[self.unrelated.pk]), **headers)
                self.assertEqual(hidden.status_code, 404, hidden.data)
                if action == 'create':
                    response = client.post(reverse('stock-transfer-list'), {}, format='json', **headers)
                elif action == 'dispatch':
                    response = client.post(reverse('stock-transfer-dispatch', args=[transfer.pk]), {}, format='json', **headers)
                elif action == 'receive':
                    response = client.post(reverse('stock-transfer-receive', args=[transfer.pk]), {}, format='json', **headers)
                else:
                    continue
                self.assertEqual(response.status_code, 400, response.data)

    def test_resolver_can_list_retrieve_and_reach_pending_divergences(self):
        _, client = self.client_with('inventory.transfer.resolve', self.destination)
        headers = {'HTTP_X_BRANCH_ID': str(self.destination.pk)}
        listed = client.get(reverse('transfer-divergence-list'), **headers)
        self.assertEqual(listed.status_code, 200, listed.data)
        self.assertIn(self.divergence.pk, [item['id'] for item in listed.data['results']])
        detail = client.get(reverse('transfer-divergence-detail', args=[self.divergence.pk]), **headers)
        self.assertEqual(detail.status_code, 200, detail.data)
        response = client.post(reverse('transfer-divergence-resolve', args=[self.divergence.pk]), {}, format='json', **headers)
        self.assertEqual(response.status_code, 400, response.data)

    def test_no_permission_or_other_branch_or_tenant_cannot_read_transfers(self):
        _, client = self.client_with('inventory.transfer.view', self.origin)
        own_headers = {'HTTP_X_BRANCH_ID': str(self.origin.pk)}
        other_tenant = client.get(
            reverse('stock-transfer-detail', args=[self.other_transfer.pk]), **own_headers,
        )
        self.assertEqual(other_tenant.status_code, 404, other_tenant.data)
        other_branch = client.get(
            reverse('stock-transfer-list'), HTTP_X_BRANCH_ID=str(self.unrelated_origin.pk),
        )
        self.assertEqual(other_branch.status_code, 403, other_branch.data)

        user = User.objects.create_user(email='no-transfer-permission@example.com', password='Inventory-Permissions-123!')
        profile = AccessProfile.objects.create(company=self.company, name='No transfer permissions')
        UserCompanyAccess.objects.create(user=user, company=self.company, access_profile=profile)
        UserBranchAccess.objects.create(user=user, branch=self.origin, access_profile=profile)
        denied = APIClient()
        denied.force_authenticate(user)
        response = denied.get(reverse('stock-transfer-list'), **own_headers)
        self.assertEqual(response.status_code, 403, response.data)
