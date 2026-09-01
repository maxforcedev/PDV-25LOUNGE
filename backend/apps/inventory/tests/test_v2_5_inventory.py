from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
import uuid

from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.base.exceptions import DomainValidationError
from apps.base.models import AuditLog
from apps.companies.models import (
    AccessProfile,
    Branch,
    Company,
    FunctionalPermission,
    UserBranchAccess,
    UserCompanyAccess,
)
from apps.products.models import Category, Product, ProductBranchConfig

from ..models import (
    InventoryCountStatus,
    LossRecord,
    MovementDomainOrigin,
    MovementNature,
    Stock,
    StockMovement,
    StockTransferReceipt,
    StockTransferStatus,
    TransferDivergenceStatus,
    TransferResolutionType,
)
from ..serializers import (
    InventoryCountSerializer,
    LossRecordSerializer,
    StockTransferSerializer,
)
from ..services import (
    confirm_inventory_count,
    create_inventory_count,
    create_stock_transfer,
    dispatch_stock_transfer,
    entry,
    exit,
    receive_stock_transfer,
    record_loss,
    resolve_transfer_divergence,
)


def fixture(name='V25'):
    company = Company.objects.create(trade_name=name, legal_name=f'{name} Ltda')
    origin = Branch.objects.create(company=company, name='Matriz', is_matrix=True)
    destination = Branch.objects.create(company=company, name='Destino')
    category = Category.objects.create(
        company=company, branch=origin, name='Estoque avancado'
    )
    destination_category = Category.objects.create(
        company=company, branch=destination, name='Estoque avancado'
    )
    product = Product.objects.create(
        company=company,
        category=category,
        name='Produto V25',
        internal_code=f'P-{name}',
        cost='5.00',
        sale_price='15.00',
        unit='kg',
    )
    ProductBranchConfig.objects.create(
        product=product, branch=origin, category=category
    )
    ProductBranchConfig.objects.create(
        product=product, branch=destination, category=destination_category
    )
    user = User.objects.create_user(email=f'{name.lower()}@example.com', password='password-123')
    user.is_superuser = True
    user.is_staff = True
    user.save(update_fields=('is_superuser', 'is_staff'))
    return company, origin, destination, product, user


def set_stock(branch, product, quantity, average_cost):
    category = product.category
    if category.branch_id != branch.pk:
        category, _ = Category.objects.get_or_create(
            company=branch.company,
            branch=branch,
            name=f'Estoque {branch.pk}',
        )
    ProductBranchConfig.objects.get_or_create(
        branch=branch, product=product, defaults={'category': category}
    )
    stock = Stock.objects.get(branch=branch, product=product)
    stock.current_quantity = Decimal(quantity)
    stock.average_unit_cost = Decimal(average_cost)
    stock.last_unit_cost = Decimal(average_cost)
    stock.save(update_fields=(
        'current_quantity', 'average_unit_cost', 'last_unit_cost', 'updated_at'
    ))
    return stock


def transfer_fixture(origin, destination, product, user, quantity='10'):
    return create_stock_transfer(
        origin_branch=origin,
        destination_branch=destination,
        items=[{'product': product.pk, 'quantity': quantity}],
        notes='Transferencia de teste',
        user=user,
    )


class TransferFlowTests(TestCase):
    def setUp(self):
        self.company, self.origin, self.destination, self.product, self.user = fixture()
        set_stock(self.origin, self.product, '30', '4')
        set_stock(self.destination, self.product, '10', '2')

    def test_full_and_partial_receipts_are_idempotent_and_weight_destination_cost(self):
        transfer = transfer_fixture(
            self.origin, self.destination, self.product, self.user, quantity='10'
        )
        dispatch_stock_transfer(
            transfer=transfer, idempotency_key=uuid.uuid4(), user=self.user
        )
        transfer.refresh_from_db()
        item = transfer.items.get()
        origin_stock = Stock.objects.get(branch=self.origin, product=self.product)
        self.assertEqual(transfer.status, StockTransferStatus.IN_TRANSIT)
        self.assertEqual(origin_stock.current_quantity, Decimal('20.000'))
        self.assertEqual(item.origin_unit_cost_snapshot, Decimal('4.000000000000'))
        dispatch_movement = item.stock_movements.get(
            domain_origin=MovementDomainOrigin.TRANSFER_DISPATCH
        )
        self.assertEqual(dispatch_movement.quantity, Decimal('-10.000'))

        first_key = uuid.uuid4()
        first = receive_stock_transfer(
            transfer=transfer,
            idempotency_key=first_key,
            items=[{'transfer_item': item.pk, 'quantity': '6'}],
            user=self.user,
        )
        replay = receive_stock_transfer(
            transfer=transfer,
            idempotency_key=first_key,
            items=[{'transfer_item': item.pk, 'quantity': '6'}],
            user=self.user,
        )
        self.assertEqual(first.pk, replay.pk)
        self.assertTrue(replay._idempotency_replayed)
        transfer.refresh_from_db()
        destination_stock = Stock.objects.get(branch=self.destination, product=self.product)
        self.assertEqual(transfer.status, StockTransferStatus.PARTIALLY_RECEIVED)
        self.assertEqual(destination_stock.current_quantity, Decimal('16.000'))
        self.assertEqual(destination_stock.average_unit_cost, Decimal('2.750000000000'))

        receive_stock_transfer(
            transfer=transfer,
            idempotency_key=uuid.uuid4(),
            items=[{'transfer_item': item.pk, 'quantity': '4'}],
            user=self.user,
        )
        transfer.refresh_from_db()
        destination_stock.refresh_from_db()
        self.assertEqual(transfer.status, StockTransferStatus.RECEIVED)
        self.assertEqual(destination_stock.current_quantity, Decimal('20.000'))
        self.assertEqual(destination_stock.average_unit_cost, Decimal('3.000000000000'))
        self.assertEqual(StockTransferReceipt.objects.filter(transfer=transfer).count(), 2)

    def test_dispatch_is_idempotent_and_finalize_accepts_no_received_lines(self):
        transfer = transfer_fixture(
            self.origin, self.destination, self.product, self.user, quantity='3'
        )
        key = uuid.uuid4()
        dispatched = dispatch_stock_transfer(
            transfer=transfer, idempotency_key=key, user=self.user
        )
        replay = dispatch_stock_transfer(
            transfer=transfer, idempotency_key=key, user=self.user
        )
        self.assertEqual(replay.pk, dispatched.pk)
        self.assertTrue(replay._idempotency_replayed)
        with self.assertRaises(DomainValidationError):
            dispatch_stock_transfer(
                transfer=transfer, idempotency_key=uuid.uuid4(), user=self.user
            )

        destination_before = Stock.objects.get(
            branch=self.destination, product=self.product
        ).current_quantity
        receipt_key = uuid.uuid4()
        receipt = receive_stock_transfer(
            transfer=transfer,
            idempotency_key=receipt_key,
            items=[],
            finalize=True,
            user=self.user,
        )
        replay_receipt = receive_stock_transfer(
            transfer=transfer,
            idempotency_key=receipt_key,
            items=[],
            finalize=True,
            user=self.user,
        )
        transfer.refresh_from_db()
        self.assertEqual(receipt.pk, replay_receipt.pk)
        self.assertFalse(receipt.items.exists())
        self.assertEqual(transfer.status, StockTransferStatus.RECEIVED_WITH_DIVERGENCE)
        self.assertEqual(transfer.items.get().divergence.pending_quantity, Decimal('3'))
        self.assertEqual(
            Stock.objects.get(branch=self.destination, product=self.product).current_quantity,
            destination_before,
        )

    def test_final_short_receipt_creates_explicit_divergence_and_all_resolution_paths(self):
        transfer = transfer_fixture(
            self.origin, self.destination, self.product, self.user, quantity='5'
        )
        dispatch_stock_transfer(
            transfer=transfer, idempotency_key=uuid.uuid4(), user=self.user
        )
        item = transfer.items.get()
        receive_stock_transfer(
            transfer=transfer,
            idempotency_key=uuid.uuid4(),
            items=[{'transfer_item': item.pk, 'quantity': '3'}],
            finalize=True,
            notes='Conferencia fisica encerrada',
            user=self.user,
        )
        transfer.refresh_from_db()
        divergence = item.divergence
        self.assertEqual(transfer.status, StockTransferStatus.RECEIVED_WITH_DIVERGENCE)
        self.assertEqual(divergence.pending_quantity, Decimal('2.000'))

        expected_movements = 0
        for resolution_type in (
            TransferResolutionType.FOUND_RECEIPT,
            TransferResolutionType.RETURN_TO_ORIGIN,
            TransferResolutionType.LOSS_IN_TRANSIT,
            TransferResolutionType.AUTHORIZED_CORRECTION,
        ):
            resolution = resolve_transfer_divergence(
                divergence=divergence,
                idempotency_key=uuid.uuid4(),
                resolution_type=resolution_type,
                quantity='0.5',
                observation=f'Resolucao confirmada {resolution_type}',
                user=self.user,
            )
            if resolution_type == TransferResolutionType.LOSS_IN_TRANSIT:
                self.assertFalse(resolution.stock_movements.exists())
            else:
                expected_movements += 1
                self.assertEqual(resolution.stock_movements.count(), 1)
            divergence.refresh_from_db()
        self.assertEqual(divergence.status, TransferDivergenceStatus.RESOLVED)
        self.assertEqual(divergence.pending_quantity, Decimal('0.000'))
        self.assertEqual(divergence.resolutions.count(), 4)
        self.assertEqual(
            divergence.resolutions.filter(stock_movements__isnull=False).distinct().count(),
            expected_movements,
        )
        transfer.refresh_from_db()
        data = StockTransferSerializer(
            transfer,
            context={'request': SimpleNamespace(
                user=self.user, support_session=None, branch_context=self.destination
            )},
        ).data
        self.assertEqual(data['items'][0]['received_quantity'], '3.500')
        self.assertEqual(data['items'][0]['pending_quantity'], '0.000')
        destination_stock = Stock.objects.get(
            branch=self.destination, product=self.product
        )
        self.assertEqual(destination_stock.current_quantity, Decimal('13.500'))

    def test_transfer_tenant_validation_cancellation_and_manual_bypass_protection(self):
        other = Company.objects.create(trade_name='Outro', legal_name='Outro Ltda')
        other_branch = Branch.objects.create(company=other, name='Matriz', is_matrix=True)
        with self.assertRaises(ValidationError):
            transfer_fixture(self.origin, other_branch, self.product, self.user)
        with self.assertRaises(ValidationError):
            transfer_fixture(self.origin, self.origin, self.product, self.user)
        with self.assertRaises(ValidationError):
            exit(
                self.product, self.origin, '1', self.user,
                nature=MovementNature.TRANSFER,
            )
        with self.assertRaises(ValidationError):
            exit(
                self.product, self.origin, '1', self.user,
                nature=MovementNature.LOSS,
            )

    def test_unit_products_reject_fractional_workflow_quantities(self):
        unit_product = Product.objects.create(
            company=self.company,
            category=self.product.category,
            name='Produto unitario V25',
            internal_code='UN-V25',
            unit='un',
            cost='2',
            sale_price='5',
        )
        set_stock(self.origin, unit_product, '10', '2')
        set_stock(self.destination, unit_product, '0', '2')
        with self.assertRaises(ValidationError):
            transfer_fixture(
                self.origin, self.destination, unit_product, self.user, quantity='0.5'
            )
        transfer = transfer_fixture(
            self.origin, self.destination, unit_product, self.user, quantity='2'
        )
        dispatch_stock_transfer(
            transfer=transfer, idempotency_key=uuid.uuid4(), user=self.user
        )
        with self.assertRaises(ValidationError):
            receive_stock_transfer(
                transfer=transfer,
                idempotency_key=uuid.uuid4(),
                items=[{'transfer_item': transfer.items.get().pk, 'quantity': '0.5'}],
                user=self.user,
            )
        with self.assertRaises(ValidationError):
            record_loss(
                branch=self.origin, product=unit_product,
                idempotency_key=uuid.uuid4(), quantity='0.5', reason='OTHER',
                observation='Fracao nao permitida', user=self.user,
            )
        with self.assertRaises(ValidationError):
            create_inventory_count(
                branch=self.origin,
                items=[{'product': unit_product.pk, 'counted_quantity': '9.5'}],
                observation='Fracao nao permitida', user=self.user,
            )


class LossAndInventoryCountTests(TestCase):
    def setUp(self):
        self.company, self.origin, self.destination, self.product, self.user = fixture('V25B')
        set_stock(self.origin, self.product, '20', '4')

    def test_loss_has_exact_snapshots_audit_and_one_debit(self):
        key = uuid.uuid4()
        loss = record_loss(
            branch=self.origin,
            product=self.product,
            idempotency_key=key,
            quantity='2',
            reason='BREAKAGE',
            observation='Duas unidades quebradas na conferencia',
            user=self.user,
        )
        replay = record_loss(
            branch=self.origin,
            product=self.product,
            idempotency_key=key,
            quantity='2',
            reason='BREAKAGE',
            observation='Duas unidades quebradas na conferencia',
            user=self.user,
        )
        stock = Stock.objects.get(branch=self.origin, product=self.product)
        movement = loss.stock_movements.get()
        self.assertEqual(loss.pk, replay.pk)
        self.assertEqual(loss.stock_movements.count(), 1)
        self.assertEqual(stock.current_quantity, Decimal('18.000'))
        self.assertEqual(loss.unit_cost_snapshot, Decimal('4.000000000000'))
        self.assertEqual(loss.sale_price_snapshot, Decimal('15.00'))
        self.assertEqual(loss.cost_impact, Decimal('8.000000000000'))
        self.assertEqual(loss.potential_sale_value, Decimal('30.000000000000'))
        self.assertEqual(movement.domain_origin, MovementDomainOrigin.LOSS)
        self.assertEqual(movement.nature, MovementNature.LOSS)
        self.assertTrue(AuditLog.objects.filter(
            action='inventory.loss.record', object_id=str(loss.pk)
        ).exists())

    def test_count_confirmation_preserves_intervening_entry_and_is_idempotent(self):
        count = create_inventory_count(
            branch=self.origin,
            items=[{'product': self.product.pk, 'counted_quantity': '18'}],
            observation='Contagem fisica do fechamento',
            user=self.user,
        )
        item = count.items.get()
        self.assertEqual(item.theoretical_quantity, Decimal('20.000'))
        self.assertEqual(item.difference_quantity, Decimal('-2.000'))
        with self.assertRaises(DomainValidationError):
            create_inventory_count(
                branch=self.origin,
                items=[{'product': self.product.pk, 'counted_quantity': '18'}],
                observation='Contagem sobreposta',
                user=self.user,
            )
        intervening = entry(
            self.product, self.origin, self.user, quantity='3',
            reason='Entrada ocorrida durante a contagem',
            idempotency_key=uuid.uuid4(),
        )
        key = uuid.uuid4()
        confirmed = confirm_inventory_count(
            inventory_count=count, idempotency_key=key, user=self.user
        )
        replay = confirm_inventory_count(
            inventory_count=count, idempotency_key=key, user=self.user
        )
        stock = Stock.objects.get(branch=self.origin, product=self.product)
        adjustment = item.stock_movements.get()
        self.assertEqual(confirmed.status, InventoryCountStatus.CONFIRMED)
        self.assertTrue(replay._idempotency_replayed)
        self.assertEqual(stock.current_quantity, Decimal('21.000'))
        self.assertEqual(intervening.quantity, Decimal('3.000'))
        self.assertEqual(adjustment.quantity, Decimal('-2.000'))
        self.assertEqual(adjustment.domain_origin, MovementDomainOrigin.INVENTORY_COUNT)
        self.assertFalse(count.items.get().is_open)

    def test_history_is_append_only_and_costs_are_redacted(self):
        loss = record_loss(
            branch=self.origin,
            product=self.product,
            idempotency_key=uuid.uuid4(),
            quantity='1',
            reason='OTHER',
            observation='Perda conhecida e documentada',
            user=self.user,
        )
        with self.assertRaises(ValidationError):
            LossRecord.objects.filter(pk=loss.pk).update(quantity=Decimal('9'))
        with self.assertRaises(ValidationError):
            loss.delete()
        movement = loss.stock_movements.get()
        with self.assertRaises(ValidationError):
            StockMovement.objects.filter(pk=movement.pk).delete()

        limited = User.objects.create_user(
            email='limited-v25@example.com', password='password-123'
        )
        request = SimpleNamespace(user=limited, support_session=None)
        data = LossRecordSerializer(loss, context={'request': request}).data
        self.assertNotIn('unit_cost_snapshot', data)
        self.assertNotIn('cost_impact', data)
        self.assertIn('potential_sale_value', data)

    def test_rbac_requires_action_specific_branch_permission(self):
        operator = User.objects.create_user(
            email='operator-v25@example.com', password='password-123'
        )
        profile = AccessProfile.objects.create(
            company=self.company, name='Somente relatorio V25'
        )
        profile.permissions.add(FunctionalPermission.objects.get(code='inventory.report.view'))
        UserCompanyAccess.objects.create(
            user=operator, company=self.company, access_profile=profile
        )
        UserBranchAccess.objects.create(
            user=operator, branch=self.origin, access_profile=profile
        )
        with self.assertRaises(Exception) as context:
            record_loss(
                branch=self.origin,
                product=self.product,
                idempotency_key=uuid.uuid4(),
                quantity='1',
                reason='OTHER',
                observation='Operador sem permissao de perda',
                user=operator,
            )
        self.assertEqual(context.exception.__class__.__name__, 'PermissionDenied')


class ConcurrentTransferTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.company, self.origin, self.destination, self.product, self.user = fixture('V25C')
        set_stock(self.origin, self.product, '20', '4')
        set_stock(self.destination, self.product, '0', '1')

    @staticmethod
    def _run(callable_):
        close_old_connections()
        try:
            return ('ok', callable_())
        except Exception as error:
            return ('error', error)
        finally:
            close_old_connections()

    def test_concurrent_dispatch_never_debits_twice(self):
        transfer = transfer_fixture(
            self.origin, self.destination, self.product, self.user, quantity='10'
        )
        dispatch_key = uuid.uuid4()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda _: self._run(
                    lambda: dispatch_stock_transfer(
                        transfer=transfer.pk, idempotency_key=dispatch_key,
                        user=self.user,
                    )
                ),
                range(2),
            ))
        self.assertEqual(sum(result[0] == 'ok' for result in results), 2)
        stock = Stock.objects.get(branch=self.origin, product=self.product)
        self.assertEqual(stock.current_quantity, Decimal('10.000'))
        self.assertEqual(StockMovement.objects.filter(
            transfer_item__transfer=transfer,
            domain_origin=MovementDomainOrigin.TRANSFER_DISPATCH,
        ).count(), 1)

    def test_concurrent_same_receipt_key_is_one_physical_credit(self):
        transfer = transfer_fixture(
            self.origin, self.destination, self.product, self.user, quantity='10'
        )
        dispatch_stock_transfer(
            transfer=transfer, idempotency_key=uuid.uuid4(), user=self.user
        )
        item_id = transfer.items.get().pk
        key = uuid.uuid4()

        def receive():
            return receive_stock_transfer(
                transfer=transfer.pk,
                idempotency_key=key,
                items=[{'transfer_item': item_id, 'quantity': '10'}],
                user=self.user,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self._run(receive), range(2)))
        self.assertEqual(sum(result[0] == 'ok' for result in results), 2)
        stock = Stock.objects.get(branch=self.destination, product=self.product)
        self.assertEqual(stock.current_quantity, Decimal('10.000'))
        self.assertEqual(StockTransferReceipt.objects.filter(transfer=transfer).count(), 1)
        self.assertEqual(StockMovement.objects.filter(
            transfer_item_id=item_id,
            domain_origin=MovementDomainOrigin.TRANSFER_RECEIPT,
        ).count(), 1)


class SerializerContractTests(TestCase):
    def test_contract_exposes_drill_down_links_and_redacts_transfer_cost(self):
        company, origin, destination, product, user = fixture('V25D')
        set_stock(origin, product, '10', '7')
        transfer = transfer_fixture(origin, destination, product, user, quantity='2')
        dispatch_stock_transfer(
            transfer=transfer, idempotency_key=uuid.uuid4(), user=user
        )
        transfer.refresh_from_db()
        limited = User.objects.create_user(
            email='contract-v25@example.com', password='password-123'
        )
        request = SimpleNamespace(
            user=limited,
            support_session=None,
            branch_context=origin,
        )
        data = StockTransferSerializer(transfer, context={'request': request}).data
        self.assertEqual(data['status'], StockTransferStatus.IN_TRANSIT)
        self.assertNotIn('origin_unit_cost_snapshot', data['items'][0])
        self.assertIn('movement_ids', data['items'][0])

        count = create_inventory_count(
            branch=origin,
            items=[{'product': product.pk, 'counted_quantity': '8'}],
            observation='Contrato do inventario',
            user=user,
        )
        count_data = InventoryCountSerializer(count, context={'request': request}).data
        self.assertIn('theoretical_quantity', count_data['items'][0])
        self.assertIn('counted_at', count_data['items'][0])
        self.assertNotIn('unit_cost_snapshot', count_data['items'][0])


class InventoryV25ApiTests(TestCase):
    def setUp(self):
        self.company, self.origin, self.destination, self.product, _ = fixture('V25API')
        set_stock(self.origin, self.product, '10', '6')
        self.user = User.objects.create_user(
            email='api-v25@example.com', password='password-123'
        )
        profile = AccessProfile.objects.get(
            company=self.company, name='Administrador', is_system=True
        )
        UserCompanyAccess.objects.create(
            user=self.user, company=self.company, access_profile=profile
        )
        for branch in (self.origin, self.destination):
            UserBranchAccess.objects.create(
                user=self.user, branch=branch, access_profile=profile
            )
        self.profile = profile
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_transfer_api_contract_branch_scope_cost_redaction_and_no_delete(self):
        self.assertTrue(self.profile.permissions.filter(
            code='inventory.transfer.dispatch'
        ).exists())
        created = self.client.post(
            reverse('stock-transfer-list'),
            {
                'origin_branch': self.origin.pk,
                'destination_branch': self.destination.pk,
                'items': [{'product': self.product.pk, 'quantity': '4'}],
                'notes': 'Contrato API V25',
            },
            format='json',
            HTTP_X_BRANCH_ID=str(self.origin.pk),
        )
        self.assertEqual(created.status_code, 201, created.data)
        transfer_id = created.data['id']
        dispatched = self.client.post(
            reverse('stock-transfer-dispatch', args=[transfer_id]),
            {'idempotency_key': str(uuid.uuid4())},
            format='json',
            HTTP_X_BRANCH_ID=str(self.origin.pk),
        )
        self.assertEqual(dispatched.status_code, 200, dispatched.data)
        self.assertEqual(dispatched.data['status'], StockTransferStatus.IN_TRANSIT)
        item_id = dispatched.data['items'][0]['id']
        received = self.client.post(
            reverse('stock-transfer-receive', args=[transfer_id]),
            {
                'idempotency_key': str(uuid.uuid4()),
                'items': [{'transfer_item': item_id, 'quantity': '4'}],
            },
            format='json',
            HTTP_X_BRANCH_ID=str(self.destination.pk),
        )
        self.assertEqual(received.status_code, 201, received.data)
        self.assertEqual(received.data['items'][0]['received_quantity'], '4.000')

        self.profile.permissions.remove(FunctionalPermission.objects.get(
            code='inventory.view_stock_costs'
        ))
        detail = self.client.get(
            reverse('stock-transfer-detail', args=[transfer_id]),
            HTTP_X_BRANCH_ID=str(self.destination.pk),
        )
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertNotIn('origin_unit_cost_snapshot', detail.data['items'][0])
        self.assertEqual(
            self.client.delete(
                reverse('stock-transfer-detail', args=[transfer_id]),
                HTTP_X_BRANCH_ID=str(self.destination.pk),
            ).status_code,
            405,
        )

        other = Company.objects.create(trade_name='Tenant API', legal_name='Tenant API Ltda')
        other_branch = Branch.objects.create(company=other, name='Matriz', is_matrix=True)
        hidden = self.client.get(
            reverse('stock-transfer-detail', args=[transfer_id]),
            HTTP_X_BRANCH_ID=str(other_branch.pk),
        )
        self.assertIn(hidden.status_code, (403, 404))

    def test_transfer_options_use_workflow_permission_without_destination_membership(self):
        selector = User.objects.create_user(
            email='selector-v25@example.com', password='password-123'
        )
        profile = AccessProfile.objects.create(
            company=self.company, name='Criacao de transferencia V25'
        )
        profile.permissions.add(FunctionalPermission.objects.get(
            code='inventory.transfer.create'
        ))
        UserCompanyAccess.objects.create(
            user=selector, company=self.company, access_profile=profile
        )
        UserBranchAccess.objects.create(
            user=selector, branch=self.origin, access_profile=profile
        )
        client = APIClient()
        client.force_authenticate(selector)
        response = client.get(
            reverse('stock-transfer-options'),
            HTTP_X_BRANCH_ID=str(self.origin.pk),
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(
            self.destination.pk,
            [item['id'] for item in response.data['destination_branches']],
        )
        self.assertIn(
            self.product.pk,
            [item['product'] for item in response.data['stocks']],
        )

    def test_loss_and_report_permissions_are_independent(self):
        report_only = AccessProfile.objects.create(
            company=self.company, name='Relatorio API V25'
        )
        report_only.permissions.add(FunctionalPermission.objects.get(
            code='inventory.report.view'
        ))
        for access in (
            self.user.company_accesses.get(),
            self.user.branch_accesses.get(branch=self.origin),
        ):
            access.access_profile = report_only
            access.save()
        response = self.client.post(
            reverse('loss-record-list'),
            {
                'idempotency_key': str(uuid.uuid4()),
                'branch': self.origin.pk,
                'product': self.product.pk,
                'quantity': '1',
                'reason': 'OTHER',
                'observation': 'Tentativa sem permissao especifica',
            },
            format='json',
            HTTP_X_BRANCH_ID=str(self.origin.pk),
        )
        self.assertEqual(response.status_code, 403, response.data)
        report = self.client.get(
            reverse('advanced-inventory-report-list'),
            HTTP_X_BRANCH_ID=str(self.origin.pk),
        )
        self.assertEqual(report.status_code, 200, report.data)
        self.assertNotIn('loss_cost_impact', report.data['financials'])
        self.assertIn('movements', report.data['drill_down'])
