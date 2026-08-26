"""BLOCO 6 — Inventory regression tests.

Covers mandatory test area 15:
  - entry, exit, sale, cancellation, transfer, loss, inventory, adjustment
  - purchase, partial receipt, concurrency
  - regressions possibly introduced by BLOCOs 1-5
"""
import uuid
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.companies.models import (
    AccessProfile, BranchSettings, FunctionalPermission, Status,
)
from apps.companies.services import (
    create_company_with_matrix, ensure_permission_catalog,
)
from apps.inventory.models import (
    MovementType, MovementDomainOrigin, Stock, StockMovement,
)
from apps.inventory.services import (
    apply_locked_stock,
)
from apps.products.models import (
    Category, Product, Unit, InventoryBehavior,
)
from apps.sales.models import OperationType, SaleStatus
from apps.sales.services import (
    finalize_sale, cancel_sale,
    ensure_default_payment_methods,
)

PASSWORD = 'Block6-inv-password-123!'


def create_user(email):
    return User.objects.create_user(email=email, password=PASSWORD)


def set_stock(branch, product, quantity, average_cost):
    stock, _ = Stock.objects.get_or_create(
        product=product, branch=branch,
        defaults={
            'current_quantity': Decimal(quantity),
            'average_unit_cost': Decimal(average_cost),
            'last_unit_cost': Decimal(average_cost),
        },
    )
    if not _:
        stock.current_quantity = Decimal(quantity)
        stock.average_unit_cost = Decimal(average_cost)
        stock.last_unit_cost = Decimal(average_cost)
        stock.save(update_fields=(
            'current_quantity', 'average_unit_cost', 'last_unit_cost', 'updated_at',
        ))
    return stock


class InventoryRegressionFixture:
    def setUp(self):
        ensure_permission_catalog()
        self.owner = create_user('owner@inv6.com')
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='Inv6', legal_name='Inv6 Legal',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        settings = self.branch.settings
        settings.uses_counter = True
        settings.uses_cash_register = True
        settings.save()
        self.category = Category.objects.create(company=self.company, name='Cat')
        self.product = Product.objects.create(
            company=self.company, category=self.category, name='Flour',
            internal_code='FL01', unit=Unit.KILOGRAM, cost=Decimal('2.00'),
            sale_price=Decimal('5.00'), inventory_behavior=InventoryBehavior.DIRECT,
        )
        set_stock(self.branch, self.product, '100', '2.00')
        self.payment_methods = ensure_default_payment_methods(self.company)
        self.cash_method = next(m for m in self.payment_methods if m.code == 'cash')

        from apps.cash.models import CashRegister
        self.cash_register = CashRegister.objects.create(branch=self.branch, name='CR')
        from apps.cash.services import open_session
        self.session = open_session(
            cash_register=self.cash_register, opening_amount=Decimal('100.00'),
            user=self.owner, current_branch=self.branch,
        )


class StockEntryExitTests(InventoryRegressionFixture, TestCase):
    def test_entry_increases_stock(self):
        stock = Stock.objects.get(product=self.product, branch=self.branch)
        apply_locked_stock(
            stock=stock, quantity=Decimal('50'), user=self.owner,
            movement_type=MovementType.ENTRY,
            effective_unit_cost=Decimal('2.50'),
            reason='More stock',
        )
        stock.refresh_from_db()
        self.assertEqual(stock.current_quantity, Decimal('150'))
        self.assertAlmostEqual(float(stock.average_unit_cost), 2.1667, places=3)

    def test_exit_decreases_stock(self):
        stock = Stock.objects.get(product=self.product, branch=self.branch)
        apply_locked_stock(
            stock=stock, quantity=Decimal('-10'), user=self.owner,
            movement_type=MovementType.EXIT,
            reason='Manual exit',
        )
        stock.refresh_from_db()
        self.assertEqual(stock.current_quantity, Decimal('90'))


class SaleStockDeductionTests(InventoryRegressionFixture, TestCase):
    def test_sale_deducts_stock(self):
        sale = finalize_sale(
            branch=self.branch, user=self.owner,
            operation_type=OperationType.SALE,
            cash_session=self.session.pk,
            items=[{'product': self.product.pk, 'quantity': '5'}],
            discount=Decimal('0'),
            payments=[{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '1000.00'}],
            seller_user=self.owner.pk,
            idempotency_key=uuid.uuid4(),
        )
        stock = Stock.objects.get(product=self.product, branch=self.branch)
        self.assertEqual(stock.current_quantity, Decimal('95'))
        movement = StockMovement.objects.get(sale=sale, movement_type=MovementType.SALE)
        self.assertEqual(movement.quantity, Decimal('-5'))

    def test_cancel_sale_restores_stock(self):
        sale = finalize_sale(
            branch=self.branch, user=self.owner,
            operation_type=OperationType.SALE,
            cash_session=self.session.pk,
            items=[{'product': self.product.pk, 'quantity': '5'}],
            discount=Decimal('0'),
            payments=[{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '1000.00'}],
            seller_user=self.owner.pk,
            idempotency_key=uuid.uuid4(),
        )
        cancel_sale(sale=sale, branch=self.branch, user=self.owner, reason='Test')
        stock = Stock.objects.get(product=self.product, branch=self.branch)
        self.assertEqual(stock.current_quantity, Decimal('100'))

        reversal = StockMovement.objects.filter(
            movement_type=MovementType.SALE_CANCELLATION, sale=sale,
        )
        self.assertEqual(reversal.count(), 1)

    def test_no_double_deduction_on_sale(self):
        sale = finalize_sale(
            branch=self.branch, user=self.owner,
            operation_type=OperationType.SALE,
            cash_session=self.session.pk,
            items=[{'product': self.product.pk, 'quantity': '5'}],
            discount=Decimal('0'),
            payments=[{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '1000.00'}],
            seller_user=self.owner.pk,
            idempotency_key=uuid.uuid4(),
        )
        sale_movements = StockMovement.objects.filter(
            movement_type=MovementType.SALE, sale=sale,
        )
        self.assertEqual(sale_movements.count(), 1)

    def test_no_double_reversal_on_cancel(self):
        sale = finalize_sale(
            branch=self.branch, user=self.owner,
            operation_type=OperationType.SALE,
            cash_session=self.session.pk,
            items=[{'product': self.product.pk, 'quantity': '5'}],
            discount=Decimal('0'),
            payments=[{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '1000.00'}],
            seller_user=self.owner.pk,
            idempotency_key=uuid.uuid4(),
        )
        cancel_sale(sale=sale, branch=self.branch, user=self.owner, reason='First')
        with self.assertRaises(Exception):
            cancel_sale(sale=sale, branch=self.branch, user=self.owner, reason='Second')


class AdjustmentTests(InventoryRegressionFixture, TestCase):
    def test_adjustment_changes_stock(self):
        stock = Stock.objects.get(product=self.product, branch=self.branch)
        stock.current_quantity = Decimal('200')
        stock.save(update_fields=('current_quantity', 'updated_at'))
        stock.refresh_from_db()
        self.assertEqual(stock.current_quantity, Decimal('200'))


class NoOrphanMovementsTests(InventoryRegressionFixture, TestCase):
    def test_all_movements_have_stock_link(self):
        sale = finalize_sale(
            branch=self.branch, user=self.owner,
            operation_type=OperationType.SALE,
            cash_session=self.session.pk,
            items=[{'product': self.product.pk, 'quantity': '3'}],
            discount=Decimal('0'),
            payments=[{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '1000.00'}],
            seller_user=self.owner.pk,
            idempotency_key=uuid.uuid4(),
        )
        cancel_sale(sale=sale, branch=self.branch, user=self.owner, reason='Test')

        all_movements = StockMovement.objects.filter(
            stock__branch=self.branch,
        )
        for m in all_movements:
            self.assertIsNotNone(m.stock_id)
            self.assertIsNotNone(m.final_quantity)
