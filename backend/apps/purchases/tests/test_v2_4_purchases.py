from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
import uuid

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
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
from apps.inventory.models import MovementNature, Stock, StockMovement
from apps.inventory.serializers import StockSerializer
from apps.inventory.services import exit as stock_exit
from apps.products.models import (
    Category, InventoryBehavior, Product, ProductBranchConfig, ProductComponent,
)
from apps.sales.services import _prepare_products
from apps.reports.selectors import inventory_kpis, stock_consumption_report
from apps.saas.models import SupportSession
from apps.saas.services import create_support_session
from apps.saas.tests.test_v2_2_saas import (
    PASSWORD,
    create_plan,
    create_tenant,
    create_user,
)
from apps.suppliers.models import (
    PresentationPreset, ProductPurchasePresentation, ProductSupplier,
    ProductSupplierUnit, Supplier,
)
from apps.suppliers.services import _save_product_supplier_unit

from ..models import (
    PayableInstallment,
    PayableInstallmentStatus,
    PurchaseOrder,
    PurchaseAttachment,
    PurchaseOrderStatus,
    PurchaseReceipt,
)
from ..serializers import PurchaseReceiptItemSerializer
from ..services import (
    cancel_installment,
    close_partial_purchase_order,
    create_purchase_order,
    add_purchase_attachment,
    pay_installment,
    place_purchase_order,
    receive_purchase_order,
    remove_purchase_attachment,
)


def company_fixture(name='V24'):
    company = Company.objects.create(trade_name=name, legal_name=f'{name} Ltda')
    branch = Branch.objects.create(company=company, name='Matriz', is_matrix=True)
    category = Category.objects.create(
        company=company, branch=branch, name=f'Compras {uuid.uuid4()}'
    )
    return company, branch, category


def user_fixture(company, branch, email='v24@example.com', *, superuser=False):
    user = User.objects.create_user(email=email, password='password-123')
    if superuser:
        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=('is_superuser', 'is_staff'))
        return user
    profile = AccessProfile.objects.get(
        company=company, name='Administrador', is_system=True
    )
    UserCompanyAccess.objects.create(
        user=user, company=company, access_profile=profile
    )
    UserBranchAccess.objects.create(
        user=user, branch=branch, access_profile=profile
    )
    return user


def product_fixture(company, category, name='Produto', code='P1', cost='2.00'):
    product = Product.objects.create(
        company=company,
        category=category,
        name=name,
        internal_code=code,
        cost=cost,
        sale_price='20.00',
    )
    ProductBranchConfig.objects.create(
        product=product, branch=category.branch, category=category,
    )
    return product


def supplier_unit_fixture(company, product, name='Fornecedor', factor='1', **relation):
    supplier = Supplier.objects.create(
        company=company, branch=company.branches.order_by('pk').first(),
        legal_name=f'{name} Ltda', trade_name=name
    )
    link = ProductSupplier.objects.create(
        company=company, product=product, supplier=supplier, **relation
    )
    unit = ProductSupplierUnit.objects.create(
        company=company,
        product_supplier=link,
        unit_code='CX',
        description=f'Caixa {factor}',
        conversion_factor=factor,
        is_default=True,
    )
    return supplier, link, unit


def create_order(branch, supplier, unit, user, *, order_type='ORDER', quantity='2',
                 price='10.00', **values):
    return create_purchase_order(
        branch=branch,
        supplier=supplier,
        order_type=order_type,
        items=[{
            'product_supplier_unit': unit.pk,
            'ordered_quantity': quantity,
            'purchase_unit_price': price,
        }],
        user=user,
        **values,
    )


class PurchaseFlowTests(TestCase):
    def setUp(self):
        self.company, self.branch, self.category = company_fixture()
        self.user = user_fixture(self.company, self.branch, superuser=True)
        self.product = product_fixture(self.company, self.category)
        self.supplier, self.link, self.unit = supplier_unit_fixture(
            self.company, self.product, factor='12'
        )

    def test_purchase_attachments_are_preserved_and_logically_removed(self):
        order = create_order(self.branch, self.supplier, self.unit, self.user)
        first = add_purchase_attachment(
            purchase_order=order,
            attachment=SimpleUploadedFile('nota.pdf', b'%PDF-1.4\nnota', 'application/pdf'),
            user=self.user,
        )
        second = add_purchase_attachment(
            purchase_order=order,
            attachment=SimpleUploadedFile('boleto.pdf', b'%PDF-1.4\nboleto', 'application/pdf'),
            user=self.user,
        )

        self.assertEqual(PurchaseAttachment.objects.filter(purchase_order=order, status='active').count(), 2)
        remove_purchase_attachment(purchase_order=order, attachment_id=first.pk, user=self.user)
        self.assertEqual(PurchaseAttachment.objects.get(pk=first.pk).status, 'inactive')
        self.assertEqual(PurchaseAttachment.objects.get(pk=second.pk).status, 'active')

    def test_direct_full_receipt_uses_locked_stock_engine_and_branch_cost(self):
        order = create_order(
            self.branch, self.supplier, self.unit, self.user,
            order_type='DIRECT', quantity='2', price='120.00',
            global_discount='1.00', freight_total='2.00',
            other_expenses_total='1.00', document_number='NF-1',
        )
        item = order.items.get()
        self.assertEqual(order.payable_total, Decimal('242.00'))
        self.assertEqual(
            item.allocated_discount + Decimal('242.00'),
            item.gross_subtotal + item.allocated_freight + item.allocated_other_expenses,
        )

        receipt = receive_purchase_order(
            purchase_order=order,
            idempotency_key=uuid.uuid4(),
            items=[{'purchase_order_item': item.pk, 'received_quantity': '2'}],
            user=self.user,
        )
        order.refresh_from_db()
        stock = Stock.objects.get(branch=self.branch, product=self.product)
        self.assertEqual(order.status, PurchaseOrderStatus.RECEIVED)
        self.assertEqual(stock.current_quantity, Decimal('24.000'))
        self.assertEqual(stock.average_unit_cost, item.effective_stock_unit_cost)
        self.assertEqual(stock.last_unit_cost, item.effective_stock_unit_cost)
        movement = StockMovement.objects.get(operation_reference=receipt.pk)
        self.assertEqual(movement.nature, MovementNature.PURCHASE)
        self.assertEqual(movement.quantity, Decimal('24.000'))
        self.assertEqual(
            movement.unit_cost_snapshot, item.effective_stock_unit_cost
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.cost, Decimal('2.00'))

    def test_package_price_preserves_exact_base_unit_cost_and_subtotal(self):
        unit = supplier_unit_fixture(
            self.company,
            self.product,
            name='Fornecedor pacote',
            factor='10',
        )[2]
        order = create_order(
            self.branch,
            unit.product_supplier.supplier,
            unit,
            self.user,
            quantity='2',
            price='30.00',
        )
        item = order.items.get()

        self.assertEqual(item.purchase_unit_price, Decimal('30.000000'))
        self.assertEqual(item.conversion_factor, Decimal('10.000000'))
        self.assertEqual(item.effective_stock_unit_cost, Decimal('3.000000000000'))
        self.assertEqual(item.gross_subtotal, Decimal('60.00'))
        self.assertEqual(order.payable_total, Decimal('60.00'))

    def test_purchase_uses_cx24_preset_without_changing_historical_snapshots(self):
        preset = PresentationPreset.objects.create(
            company=self.company, presentation_type='CX', conversion_factor='24'
        )
        unit = _save_product_supplier_unit(
            company=self.company, product_supplier=self.link, presentation_preset=preset,
            barcode='789', is_default=False,
        )
        order = create_purchase_order(
            branch=self.branch, supplier=self.supplier, order_type='DIRECT', user=self.user,
            items=[{
                'product_supplier_unit': unit.pk,
                'ordered_quantity': '3',
                'purchase_unit_price': '120.00',
            }],
        )
        item = order.items.get()
        receive_purchase_order(
            purchase_order=order, idempotency_key=uuid.uuid4(),
            items=[{'purchase_order_item': item.pk, 'received_quantity': '3'}], user=self.user,
        )
        self.assertEqual(item.presentation_unit_code, 'CX24')
        self.assertEqual(item.conversion_factor, Decimal('24.000000'))
        self.assertEqual(Stock.objects.get(branch=self.branch, product=self.product).current_quantity, Decimal('72.000'))
        preset.conversion_factor = Decimal('12')
        preset.save()
        item.refresh_from_db()
        self.assertEqual(item.conversion_factor, Decimal('24.000000'))

    def test_partial_receipt_requires_reason_is_idempotent_and_can_finish(self):
        order = create_order(
            self.branch, self.supplier, self.unit, self.user, quantity='2', price='120'
        )
        place_purchase_order(purchase_order=order, user=self.user)
        item = order.items.get()
        key = uuid.uuid4()
        with self.assertRaises(ValidationError):
            receive_purchase_order(
                purchase_order=order,
                idempotency_key=key,
                items=[{'purchase_order_item': item.pk, 'received_quantity': '1'}],
                user=self.user,
            )
        receipt = receive_purchase_order(
            purchase_order=order,
            idempotency_key=key,
            items=[{'purchase_order_item': item.pk, 'received_quantity': '1'}],
            divergence_reason='Entrega parcial do fornecedor',
            user=self.user,
        )
        replay = receive_purchase_order(
            purchase_order=order,
            idempotency_key=key,
            items=[{'purchase_order_item': item.pk, 'received_quantity': '1'}],
            divergence_reason='Entrega parcial do fornecedor',
            user=self.user,
        )
        self.assertEqual(replay.pk, receipt.pk)
        self.assertTrue(replay._idempotency_replayed)
        self.assertEqual(StockMovement.objects.filter(operation_reference=receipt.pk).count(), 1)
        with self.assertRaises(DomainValidationError):
            receive_purchase_order(
                purchase_order=order,
                idempotency_key=key,
                items=[{'purchase_order_item': item.pk, 'received_quantity': '2'}],
                user=self.user,
            )

        second = receive_purchase_order(
            purchase_order=order,
            idempotency_key=uuid.uuid4(),
            items=[{'purchase_order_item': item.pk, 'received_quantity': '1'}],
            user=self.user,
        )
        order.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrderStatus.RECEIVED)
        second_item = second.items.get()
        self.assertEqual(second_item.previously_received_quantity, Decimal('1.000000'))
        self.assertEqual(second_item.pending_quantity, Decimal('0.000000'))

    def test_partial_can_be_closed_without_changing_confirmed_receipt(self):
        order = create_order(self.branch, self.supplier, self.unit, self.user)
        place_purchase_order(purchase_order=order, user=self.user)
        item = order.items.get()
        receipt = receive_purchase_order(
            purchase_order=order,
            idempotency_key=uuid.uuid4(),
            items=[{'purchase_order_item': item.pk, 'received_quantity': '1'}],
            divergence_reason='Fornecedor nao entregara o restante',
            user=self.user,
        )
        close_partial_purchase_order(
            purchase_order=order, user=self.user, reason='Saldo cancelado pelo fornecedor'
        )
        order.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrderStatus.CLOSED_PARTIAL)
        self.assertTrue(PurchaseReceipt.objects.filter(pk=receipt.pk).exists())
        with self.assertRaises(ValidationError):
            receipt.delete()

    def test_allocations_reconcile_cent_residue_to_stable_largest_item(self):
        products = [self.product]
        units = [self.unit]
        for index in range(2):
            product = product_fixture(
                self.company, self.category, name=f'Produto {index}', code=f'PX{index}'
            )
            link = ProductSupplier.objects.create(
                company=self.company, product=product, supplier=self.supplier
            )
            unit = ProductSupplierUnit.objects.create(
                company=self.company, product_supplier=link, unit_code='UN',
                description='Unidade', conversion_factor='1',
            )
            products.append(product)
            units.append(unit)
        order = create_purchase_order(
            branch=self.branch,
            supplier=self.supplier,
            order_type='ORDER',
            items=[{
                'product_supplier_unit': unit.pk,
                'ordered_quantity': '1',
                'purchase_unit_price': '0.01',
            } for unit in units],
            freight_total='0.01',
            user=self.user,
        )
        items = list(order.items.all())
        self.assertEqual(sum((row.allocated_freight for row in items)), Decimal('0.01'))
        self.assertEqual(items[0].allocated_freight, Decimal('0.01'))
        self.assertEqual(
            sum((row.effective_total for row in items)), order.payable_total
        )

    def test_active_exclusive_supplier_is_enforced(self):
        exclusive_supplier, _exclusive_link, _exclusive_unit = supplier_unit_fixture(
            self.company, self.product, name='Exclusivo', factor='1',
            is_exclusive=True, is_preferred=True,
        )
        with self.assertRaises(ValidationError):
            create_order(self.branch, self.supplier, self.unit, self.user)
        self.assertNotEqual(exclusive_supplier, self.supplier)

    def test_purchase_presentation_is_canonical_across_suppliers(self):
        suppliers = [self.supplier]
        units = [self.unit]
        for name in ('Fornecedor B', 'Fornecedor C', 'Fornecedor D'):
            supplier, _link, unit = supplier_unit_fixture(
                self.company, self.product, name=name, factor='12',
            )
            suppliers.append(supplier)
            units.append(unit)

        orders = [
            create_order(self.branch, supplier, unit, self.user)
            for supplier, unit in zip(suppliers, units)
        ]

        self.assertEqual(
            ProductPurchasePresentation.objects.filter(product=self.product).count(), 1,
        )
        self.assertEqual(
            {order.items.get().presentation_description for order in orders},
            {self.unit.description},
        )

    def test_confirmed_exclusive_supplier_override_is_persisted_and_required_on_placement(self):
        exclusive_supplier, _exclusive_link, _exclusive_unit = supplier_unit_fixture(
            self.company, self.product, name='Exclusivo', factor='1',
            is_exclusive=True, is_preferred=True,
        )
        order = create_order(
            self.branch, self.supplier, self.unit, self.user,
            exclusive_supplier_override=True,
        )
        self.assertTrue(order.exclusive_supplier_override)
        with self.assertRaises(ValidationError):
            place_purchase_order(purchase_order=order, user=self.user)

        placed = place_purchase_order(
            purchase_order=order, user=self.user,
            exclusive_supplier_override=True,
        )
        self.assertEqual(placed.status, PurchaseOrderStatus.PLACED)
        audit = AuditLog.objects.filter(action='purchase.place', object_id=order.pk).latest('id')
        details = audit.metadata['exclusive_supplier_overrides'][0]
        self.assertEqual(details['product_name'], self.product.name)
        self.assertEqual(details['exclusive_supplier_name'], exclusive_supplier.trade_name)
        self.assertEqual(details['selected_supplier_name'], self.supplier.trade_name)
        self.assertTrue(details['override_confirmed'])

    def test_confirmed_exclusive_supplier_override_allows_direct_receipt(self):
        supplier_unit_fixture(
            self.company, self.product, name='Exclusivo', factor='1',
            is_exclusive=True, is_preferred=True,
        )
        order = create_order(
            self.branch, self.supplier, self.unit, self.user,
            order_type='DIRECT', exclusive_supplier_override=True,
        )
        receipt = receive_purchase_order(
            purchase_order=order, user=self.user, idempotency_key=uuid.uuid4(),
            items=[{
                'purchase_order_item': order.items.get().pk,
                'received_quantity': '2',
            }],
        )
        self.assertEqual(receipt.purchase_order_id, order.pk)

    def test_payables_reconcile_and_manual_transitions_are_audited(self):
        due = date.today() + timedelta(days=10)
        with self.assertRaises(ValidationError):
            create_order(
                self.branch, self.supplier, self.unit, self.user,
                installments=[{'amount': '19.99', 'due_date': due}],
            )
        order = create_order(
            self.branch, self.supplier, self.unit, self.user,
            installments=[
                {'amount': '10.00', 'due_date': due},
                {'amount': '10.00', 'due_date': due + timedelta(days=30)},
            ],
        )
        place_purchase_order(purchase_order=order, user=self.user)
        first, second = list(order.installments.all())
        pay_installment(installment=first, user=self.user, notes='PIX manual')
        cancel_installment(
            installment=second, user=self.user, reason='Renegociada fora desta compra'
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, PayableInstallmentStatus.PAID)
        self.assertEqual(second.status, PayableInstallmentStatus.CANCELLED)
        self.assertTrue(AuditLog.objects.filter(action='purchase.payable.pay').exists())
        self.assertTrue(AuditLog.objects.filter(action='purchase.payable.cancel').exists())
        creation_logs = AuditLog.objects.filter(
            action='purchase.payable.create', object_id__in=(str(first.pk), str(second.pk))
        )
        self.assertEqual(creation_logs.count(), 2)
        payment_log = AuditLog.objects.get(
            action='purchase.payable.pay', object_id=str(first.pk)
        )
        self.assertEqual(payment_log.before['status'], PayableInstallmentStatus.PENDING)
        self.assertEqual(payment_log.after['status'], PayableInstallmentStatus.PAID)

    def test_purchase_accepts_product_without_supplier_presentation(self):
        order = create_purchase_order(
            branch=self.branch,
            supplier=self.supplier,
            order_type='ORDER',
            items=[{
                'product': self.product.pk,
                'ordered_quantity': '2',
                'purchase_unit_price': '10.00',
            }],
            user=self.user,
        )

        item = order.items.get()
        self.assertIsNone(item.product_supplier_unit)
        self.assertEqual(item.conversion_factor, Decimal('1.000000'))
        self.assertEqual(item.ordered_stock_quantity, Decimal('2.000000'))

    def test_automatic_installments_distribute_remainder_cents(self):
        due = date.today() + timedelta(days=10)
        order = create_order(
            self.branch, self.supplier, self.unit, self.user,
            quantity='1', price='10.01',
            installment_count=3,
            first_due_date=due,
        )

        installments = list(order.installments.order_by('installment_number'))
        self.assertEqual([item.amount for item in installments], [
            Decimal('3.34'), Decimal('3.34'), Decimal('3.33'),
        ])
        self.assertEqual(installments[0].due_date, due)
        self.assertEqual(
            [item.due_date.month for item in installments],
            [due.month, due.month % 12 + 1, (due.month + 1) % 12 + 1],
        )
        self.assertEqual(sum((item.amount for item in installments)), order.payable_total)

    def test_purchase_models_block_bulk_and_physical_deletion(self):
        order = create_order(self.branch, self.supplier, self.unit, self.user)
        with self.assertRaises(ValidationError):
            PurchaseOrder.objects.filter(pk=order.pk).update(status='CANCELLED')
        with self.assertRaises(ValidationError):
            PurchaseOrder.objects.filter(pk=order.pk).delete()
        with self.assertRaises(ValidationError):
            order.delete()


class PurchaseBaseReceiptTests(TestCase):
    def setUp(self):
        self.company, self.branch, self.category = company_fixture('Recebimento base')
        self.user = user_fixture(self.company, self.branch, superuser=True)
        self.product = product_fixture(self.company, self.category)
        self.supplier, _link, self.unit = supplier_unit_fixture(
            self.company, self.product, factor='12'
        )

    def _placed_order(self):
        order = create_order(
            self.branch, self.supplier, self.unit, self.user,
            quantity='2', price='60.00',
        )
        place_purchase_order(purchase_order=order, user=self.user)
        return order, order.items.get()

    def test_receiving_24_base_units_completes_two_packs(self):
        order, item = self._placed_order()
        receipt = receive_purchase_order(
            purchase_order=order, idempotency_key=uuid.uuid4(),
            items=[{
                'purchase_order_item': item.pk,
                'received_stock_quantity': '24',
            }], user=self.user,
        )
        order.refresh_from_db()
        row = receipt.items.get()
        self.assertEqual(order.status, PurchaseOrderStatus.RECEIVED)
        self.assertEqual(row.stock_quantity, Decimal('24.000'))
        self.assertEqual(row.received_quantity, Decimal('2.000000'))
        self.assertEqual(row.divergence_quantity, Decimal('0.000000'))
        self.assertEqual(
            Stock.objects.get(branch=self.branch, product=self.product).current_quantity,
            Decimal('24.000'),
        )

    def test_receiving_30_base_units_records_divergence_without_rewriting_payable(self):
        order, item = self._placed_order()
        receipt = receive_purchase_order(
            purchase_order=order, idempotency_key=uuid.uuid4(),
            items=[{
                'purchase_order_item': item.pk,
                'received_stock_quantity': '30',
            }], divergence_reason='Fornecedor entregou seis unidades extras', user=self.user,
        )
        replay = receive_purchase_order(
            purchase_order=order, idempotency_key=receipt.idempotency_key,
            items=[{
                'purchase_order_item': item.pk,
                'received_stock_quantity': '30',
            }], divergence_reason='Fornecedor entregou seis unidades extras', user=self.user,
        )
        order.refresh_from_db()
        row = receipt.items.get()
        serialized = PurchaseReceiptItemSerializer(
            row, context={'request': SimpleNamespace(user=self.user)}
        ).data
        self.assertEqual(replay.pk, receipt.pk)
        self.assertEqual(order.status, PurchaseOrderStatus.RECEIVED)
        self.assertEqual(order.payable_total, Decimal('120.00'))
        self.assertEqual(row.stock_quantity, Decimal('30.000'))
        self.assertEqual(serialized['divergence_stock_quantity'], '6.000000')
        self.assertEqual(serialized['ordered_total'], '120.00')
        self.assertEqual(serialized['received_total'], '150.00')
        self.assertEqual(
            Stock.objects.get(branch=self.branch, product=self.product).current_quantity,
            Decimal('30.000'),
        )
        self.assertEqual(StockMovement.objects.filter(operation_reference=receipt.pk).count(), 1)

    def test_receiving_10_base_units_keeps_order_partial_and_reports_difference(self):
        order, item = self._placed_order()
        receipt = receive_purchase_order(
            purchase_order=order, idempotency_key=uuid.uuid4(),
            items=[{
                'purchase_order_item': item.pk,
                'received_stock_quantity': '10',
            }], divergence_reason='Entrega parcial', user=self.user,
        )
        order.refresh_from_db()
        row = receipt.items.get()
        serialized = PurchaseReceiptItemSerializer(
            row, context={'request': SimpleNamespace(user=self.user)}
        ).data
        self.assertEqual(order.status, PurchaseOrderStatus.PARTIALLY_RECEIVED)
        self.assertEqual(row.stock_quantity, Decimal('10.000'))
        self.assertEqual(serialized['pending_stock_quantity'], '14.000000')
        self.assertEqual(serialized['divergence_stock_quantity'], '-14.000000')
        self.assertEqual(serialized['received_total'], '50.00')
        self.assertEqual(serialized['difference_total'], '-70.00')


class BranchCostAndSaleSnapshotTests(TestCase):
    def setUp(self):
        self.company, self.branch, self.category = company_fixture('Custos')
        self.other_branch = Branch.objects.create(company=self.company, name='Filial 2')
        self.user = user_fixture(self.company, self.branch, superuser=True)
        self.product = product_fixture(self.company, self.category, cost='2.00')
        self.supplier, _link, self.unit = supplier_unit_fixture(
            self.company, self.product, factor='1'
        )

    def test_weighted_average_is_isolated_by_branch_and_sale_uses_branch_cost(self):
        other_category = Category.objects.create(
            company=self.company, branch=self.other_branch, name='Categoria filial 2'
        )
        ProductBranchConfig.objects.create(
            product=self.product,
            branch=self.other_branch,
            category=other_category,
        )
        own = Stock.objects.get(branch=self.branch, product=self.product)
        own.current_quantity = Decimal('10')
        own.average_unit_cost = Decimal('5')
        own.last_unit_cost = Decimal('5')
        own.save()
        other = Stock.objects.get(branch=self.other_branch, product=self.product)
        other.current_quantity = Decimal('4')
        other.average_unit_cost = Decimal('3')
        other.last_unit_cost = Decimal('3')
        other.save()
        order = create_order(
            self.branch, self.supplier, self.unit, self.user,
            order_type='DIRECT', quantity='10', price='10',
        )
        item = order.items.get()
        receive_purchase_order(
            purchase_order=order, idempotency_key=uuid.uuid4(),
            items=[{'purchase_order_item': item.pk, 'received_quantity': '10'}],
            user=self.user,
        )
        own = Stock.objects.get(branch=self.branch, product=self.product)
        other = Stock.objects.get(branch=self.other_branch, product=self.product)
        self.assertEqual(own.average_unit_cost, Decimal('7.500000000000'))
        self.assertEqual(other.average_unit_cost, Decimal('3.000000000000'))
        self.assertEqual(
            inventory_kpis(self.branch, include_value=True)['inventory_value'],
            Decimal('150.00'),
        )
        serialized = StockSerializer(
            own, context={'request': SimpleNamespace(user=self.user)}
        ).data
        self.assertEqual(serialized['unit_cost'], '7.500000000000')
        self.assertEqual(serialized['total_cost'], '150.00')

        snapshots, _requirements, _content_req, _subtotal = _prepare_products(
            self.company,
            [{'product': self.product.pk, 'quantity': '1'}],
            branch=self.branch,
        )
        self.assertEqual(snapshots[0]['unit_cost'], own.average_unit_cost)

    def test_component_snapshot_uses_each_component_branch_cost(self):
        stock = Stock.objects.get(branch=self.branch, product=self.product)
        stock.current_quantity = Decimal('10')
        stock.average_unit_cost = Decimal('7.25')
        stock.last_unit_cost = Decimal('7.25')
        stock.save()
        parent = Product.objects.create(
            company=self.company, category=self.category, name='Combo',
            internal_code='COMBO', cost='1', sale_price='30',
            inventory_behavior=InventoryBehavior.COMPONENTS, is_sellable=False,
        )
        ProductComponent.objects.create(
            parent_product=parent, component_product=self.product, quantity='2'
        )
        parent.is_sellable = True
        parent.save()
        ProductBranchConfig.objects.create(
            product=parent, branch=self.branch, category=self.category
        )
        snapshots, _requirements, _content_req, _subtotal = _prepare_products(
            self.company,
            [{'product': parent.pk, 'quantity': '1'}],
            branch=self.branch,
        )
        self.assertEqual(snapshots[0]['unit_cost'], Decimal('14.50'))
        self.assertEqual(
            snapshots[0]['component_cost_snapshot'][0]['unit_cost'],
            '7.250000000000',
        )


class PurchaseApiRbacTests(TestCase):
    def setUp(self):
        self.company, self.branch, self.category = company_fixture('API V24')
        self.user = user_fixture(self.company, self.branch, 'api-v24@example.com')
        self.product = product_fixture(self.company, self.category)
        self.supplier, _link, self.unit = supplier_unit_fixture(
            self.company, self.product
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.headers = {'HTTP_X_BRANCH_ID': str(self.branch.pk)}

    def test_admin_migration_permissions_tenant_scope_cost_redaction_and_audit(self):
        profile = self.user.branch_accesses.get().access_profile
        self.assertTrue(profile.permissions.filter(code='purchases.receive').exists())
        response = self.client.post(
            reverse('purchase-order-list'),
            {
                'branch': self.branch.pk,
                'supplier': self.supplier.pk,
                'order_type': 'DIRECT',
                'items': [{
                    'product_supplier_unit': self.unit.pk,
                    'ordered_quantity': '1',
                    'purchase_unit_price': '10',
                }],
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 201, response.data)
        order_id = response.data['id']
        self.assertTrue(AuditLog.objects.filter(
            action='purchase.create', object_id=str(order_id), branch=self.branch
        ).exists())

        profile.permissions.remove(FunctionalPermission.objects.get(code='purchases.view_costs'))
        response = self.client.get(
            reverse('purchase-order-detail', args=[order_id]), **self.headers
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn('payable_total', response.data)
        self.assertNotIn('purchase_unit_price', response.data['items'][0])
        self.assertEqual(
            self.client.delete(
                reverse('purchase-order-detail', args=[order_id]), **self.headers
            ).status_code,
            405,
        )

        other_company, other_branch, _category = company_fixture('Outro API V24')
        hidden_user = user_fixture(
            other_company, other_branch, 'other-v24@example.com', superuser=True
        )
        self.assertIsNotNone(hidden_user)
        response = self.client.get(
            reverse('purchase-order-detail', args=[order_id]),
            HTTP_X_BRANCH_ID=str(other_branch.pk),
        )
        self.assertIn(response.status_code, (403, 404))

    def test_create_and_receive_permissions_are_separate(self):
        limited = AccessProfile.objects.create(
            company=self.company, name='Comprador limitado'
        )
        limited.permissions.add(
            FunctionalPermission.objects.get(code='purchases.view'),
            FunctionalPermission.objects.get(code='purchases.create'),
        )
        access = self.user.branch_accesses.get()
        access.access_profile = limited
        access.save()
        company_access = self.user.company_accesses.get()
        company_access.access_profile = limited
        company_access.save()
        response = self.client.post(
            reverse('purchase-order-list'),
            {
                'branch': self.branch.pk,
                'supplier': self.supplier.pk,
                'order_type': 'DIRECT',
                'items': [{
                    'product_supplier_unit': self.unit.pk,
                    'ordered_quantity': '1',
                    'purchase_unit_price': '10',
                }],
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 201, response.data)
        response = self.client.post(
            reverse('purchase-order-receive', args=[response.data['id']]),
            {
                'idempotency_key': str(uuid.uuid4()),
                'items': [{
                    'purchase_order_item': response.data['items'][0]['id'],
                    'received_quantity': '1',
                }],
            },
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_creation_options_use_purchase_permission_and_current_branch(self):
        limited = AccessProfile.objects.create(
            company=self.company, name='Somente criar compra'
        )
        limited.permissions.add(
            FunctionalPermission.objects.get(code='purchases.create')
        )
        branch_access = self.user.branch_accesses.get()
        branch_access.access_profile = limited
        branch_access.save()
        company_access = self.user.company_accesses.get()
        company_access.access_profile = limited
        company_access.save()

        other_branch = Branch.objects.create(company=self.company, name='Filial B')
        Supplier.objects.create(
            company=self.company,
            branch=other_branch,
            trade_name='Fornecedor oculto',
        )
        archived = product_fixture(
            self.company, self.category, name='Arquivado', code='ARQ'
        )
        Product.objects.filter(pk=archived.pk).update(archived_at=timezone.now())

        response = self.client.get(
            reverse('purchase-order-creation-options'), **self.headers
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [item['id'] for item in response.data['suppliers']],
            [self.supplier.pk],
        )
        self.assertEqual(
            [item['id'] for item in response.data['products']],
            [self.product.pk],
        )

    def test_nested_installments_require_manage_payables(self):
        limited = AccessProfile.objects.create(
            company=self.company, name='Comprador sem contas a pagar'
        )
        limited.permissions.add(
            FunctionalPermission.objects.get(code='purchases.view'),
            FunctionalPermission.objects.get(code='purchases.create'),
        )
        for access in (
            self.user.branch_accesses.get(), self.user.company_accesses.get()
        ):
            access.access_profile = limited
            access.save()
        payload = {
            'branch': self.branch.pk,
            'supplier': self.supplier.pk,
            'order_type': 'DIRECT',
            'items': [{
                'product_supplier_unit': self.unit.pk,
                'ordered_quantity': '1',
                'purchase_unit_price': '10',
            }],
            'installments': [{
                'amount': '10.00',
                'due_date': str(date.today() + timedelta(days=10)),
            }],
        }
        response = self.client.post(
            reverse('purchase-order-list'), payload, format='json', **self.headers
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(PurchaseOrder.objects.exists())

        payload.pop('installments')
        created = self.client.post(
            reverse('purchase-order-list'), payload, format='json', **self.headers
        )
        self.assertEqual(created.status_code, 201, created.data)
        response = self.client.patch(
            reverse('purchase-order-detail', args=[created.data['id']]),
            {'installments': [{
                'amount': '10.00',
                'due_date': str(date.today() + timedelta(days=10)),
            }]},
            format='json',
            **self.headers,
        )
        self.assertEqual(response.status_code, 403, response.data)

    def test_audit_cost_payload_is_contextually_redacted_without_mutating_log(self):
        limited = AccessProfile.objects.create(
            company=self.company, name='Auditor sem custos'
        )
        limited.permissions.add(
            FunctionalPermission.objects.get(code='audit_logs.view'),
            FunctionalPermission.objects.get(code='purchases.view'),
        )
        for access in (
            self.user.branch_accesses.get(), self.user.company_accesses.get()
        ):
            access.access_profile = limited
            access.save()
        log = AuditLog.objects.create(
            company=self.company,
            branch=self.branch,
            actor=self.user,
            action='purchase.receive',
            object_type='apps.purchases.models.PurchaseReceipt',
            object_id='99',
            before={'status': 'PLACED', 'payable_total': '10.00'},
            after={
                'status': 'RECEIVED',
                'items': [{
                    'product_name': 'Produto',
                    'effective_stock_unit_cost_snapshot': '7.50',
                    'unit_cost_snapshot': '7.50',
                }],
            },
            metadata={'amount': '10.00', 'summary': 'Recebida'},
        )
        response = self.client.get(
            reverse('base:audit-log-detail', args=[log.pk]), **self.headers
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn('payable_total', response.data['before'])
        self.assertNotIn('amount', response.data['metadata'])
        self.assertNotIn(
            'effective_stock_unit_cost_snapshot', response.data['after']['items'][0]
        )
        self.assertNotIn('unit_cost_snapshot', response.data['after']['items'][0])
        self.assertEqual(response.data['after']['items'][0]['product_name'], 'Produto')
        self.assertNotIn(
            'payable_total', [change['field'] for change in response.data['changes']]
        )
        log.refresh_from_db()
        self.assertEqual(log.before['payable_total'], '10.00')
        self.assertEqual(log.metadata['amount'], '10.00')

    def test_private_attachment_upload_download_validation_and_scope(self):
        order = create_order(self.branch, self.supplier, self.unit, self.user)
        url = reverse('purchase-order-attachment', args=[order.pk])
        response = self.client.post(
            url,
            {'attachment': SimpleUploadedFile(
                'nota_fiscal.pdf', b'%PDF-1.7\nprivate', content_type='application/pdf'
            )},
            format='multipart',
            **self.headers,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['attachment']['name'], 'nota_fiscal.pdf')
        order.refresh_from_db()
        stored_name = order.attachment.name
        self.assertNotIn(str(order.attachment.storage.location), stored_name)

        response = self.client.get(url, **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'%PDF-1.7\nprivate')

        response = self.client.post(
            url,
            {'attachment': SimpleUploadedFile(
                'fake.pdf', b'not a pdf', content_type='application/pdf'
            )},
            format='multipart',
            **self.headers,
        )
        self.assertEqual(response.status_code, 400, response.data)

        other_company, other_branch, _category = company_fixture('Anexo oculto')
        other_user = user_fixture(
            other_company, other_branch, 'attachment-other@example.com'
        )
        self.client.force_authenticate(other_user)
        response = self.client.get(
            url, HTTP_X_BRANCH_ID=str(other_branch.pk)
        )
        self.assertIn(response.status_code, (403, 404))
        order.attachment.storage.delete(stored_name)

    def test_stock_consumption_uses_immutable_movement_cost(self):
        stock = Stock.objects.get(branch=self.branch, product=self.product)
        stock.current_quantity = Decimal('10')
        stock.average_unit_cost = Decimal('5')
        stock.last_unit_cost = Decimal('5')
        stock.save()
        movement = stock_exit(
            self.product, self.branch, self.user, quantity='2',
            reason='Uso interno'
        )
        self.assertEqual(movement.unit_cost_snapshot, Decimal('5.000000000000'))
        stock.refresh_from_db()
        stock.average_unit_cost = Decimal('99')
        stock.save()
        _rows, summary = stock_consumption_report(
            branch=self.branch,
            start=timezone.now() - timedelta(days=1),
            end=timezone.now() + timedelta(days=1),
            filters={},
        )
        self.assertEqual(summary[0]['estimated_cost'], Decimal('10.00'))


class ConcurrentReceiptTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.company, self.branch, self.category = company_fixture(
            f'Concorrencia {uuid.uuid4()}'
        )
        self.user = user_fixture(
            self.company,
            self.branch,
            email=f'concorrencia-{uuid.uuid4()}@example.com',
            superuser=True,
        )
        self.product = product_fixture(self.company, self.category)
        self.supplier, _link, self.unit = supplier_unit_fixture(
            self.company, self.product
        )
        order = create_order(
            self.branch, self.supplier, self.unit, self.user, quantity='2'
        )
        place_purchase_order(purchase_order=order, user=self.user)
        self.order_id = order.pk
        self.item_id = order.items.get().pk

    def _receive_all(self):
        close_old_connections()
        try:
            user = User.objects.get(pk=self.user.pk)
            receive_purchase_order(
                purchase_order=self.order_id,
                idempotency_key=uuid.uuid4(),
                items=[{
                    'purchase_order_item': self.item_id,
                    'received_quantity': '2',
                }],
                user=user,
            )
            return 'ok'
        except ValidationError:
            return 'rejected'
        finally:
            close_old_connections()

    def test_concurrent_receipts_cannot_double_enter_stock(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: self._receive_all(), range(2)))
        self.assertCountEqual(results, ('ok', 'rejected'))
        self.assertEqual(PurchaseReceipt.objects.count(), 1)
        self.assertEqual(
            Stock.objects.get(branch=self.branch, product=self.product).current_quantity,
            Decimal('2.000'),
        )


class PurchaseSupportSessionTests(TestCase):
    def setUp(self):
        version = create_plan(code='purchase-support')
        _owner, self.company, _subscription = create_tenant(
            'Purchase Support', plan_version=version
        )
        self.branch = self.company.branches.get(is_matrix=True)
        category = Category.objects.create(
            company=self.company, branch=self.branch, name='Suporte'
        )
        product = product_fixture(self.company, category, name='Suporte', code='SUP')
        self.supplier, _link, self.unit = supplier_unit_fixture(
            self.company, product, name='Fornecedor suporte'
        )
        self.agent = create_user('purchase-support-agent@example.com')
        call_command(
            'bootstrap_platform_admin', email=self.agent.email, stdout=StringIO()
        )
        self.client = APIClient()
        self.assertTrue(self.client.login(email=self.agent.email, password=PASSWORD))

    def _session_headers(self, mode):
        session = create_support_session(
            actor=self.agent,
            company=self.company,
            mode=mode,
            reason='Validar compra da filial',
            current_password=PASSWORD,
        )
        return {
            'HTTP_X_SUPPORT_SESSION_ID': str(session.pk),
            'HTTP_X_BRANCH_ID': str(self.branch.pk),
        }

    def _payload(self):
        return {
            'branch': self.branch.pk,
            'supplier': self.supplier.pk,
            'order_type': 'DIRECT',
            'items': [{
                'product_supplier_unit': self.unit.pk,
                'ordered_quantity': '1',
                'purchase_unit_price': '10',
            }],
        }

    def test_read_only_support_can_read_but_cannot_mutate(self):
        headers = self._session_headers(SupportSession.Mode.READ_ONLY)
        response = self.client.get(reverse('purchase-order-list'), **headers)
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.post(
            reverse('purchase-order-list'), self._payload(), format='json', **headers
        )
        self.assertEqual(response.status_code, 403)

    def test_read_write_support_is_tenant_scoped_and_audited_as_agent(self):
        headers = self._session_headers(SupportSession.Mode.READ_WRITE)
        response = self.client.post(
            reverse('purchase-order-list'), self._payload(), format='json', **headers
        )
        self.assertEqual(response.status_code, 201, response.data)
        log = AuditLog.objects.get(
            action='purchase.create', object_id=str(response.data['id'])
        )
        self.assertEqual(log.actor, self.agent)
        self.assertEqual(log.metadata['support_actor_id'], self.agent.pk)
        self.assertEqual(log.company, self.company)

    def test_non_impersonated_support_me_synthesizes_active_branch_context(self):
        inactive = Branch.objects.create(
            company=self.company, name='Filial inativa', status='inactive'
        )
        session = create_support_session(
            actor=self.agent,
            company=self.company,
            mode=SupportSession.Mode.READ_ONLY,
            reason='Inspecionar contexto da empresa',
        )
        response = self.client.get(
            reverse('accounts:me'), HTTP_X_SUPPORT_SESSION_ID=str(session.pk)
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([row['id'] for row in response.data['branches']], [self.branch.pk])
        self.assertNotIn(inactive.pk, [row['id'] for row in response.data['branches']])
        branch_context = response.data['branches'][0]
        self.assertTrue(branch_context['support_context'])
        self.assertIn('purchases.view', branch_context['permissions'])
        self.assertNotIn('purchases.create', branch_context['permissions'])
        self.assertFalse(response.data['companies'][0]['is_owner'])
        self.assertFalse(UserCompanyAccess.objects.filter(
            user=self.agent, company=self.company
        ).exists())
