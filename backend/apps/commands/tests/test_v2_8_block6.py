"""BLOCO 6 — Tests for Tables, Commands, Inventory, Financial Engine, and Traceability.

Covers mandatory test areas 6-12:
  6  TABLES_COMMANDS
  7  COMMAND_CASH
  8  COMMAND_FINANCIAL_ENGINE
  9  COMMAND_FINALIZE_PERMISSION
  10 COMMAND_INVENTORY
  11 COMMAND_CANCELLATION
  12 TRACEABILITY
"""
import uuid
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import (
    AccessProfile, BranchSettings, FunctionalPermission, Status,
    UserBranchAccess, UserCompanyAccess,
)
from apps.companies.rbac import PERMISSION_CATALOG
from apps.companies.services import (
    create_company_with_matrix, ensure_permission_catalog,
)
from apps.cash.models import CashRegister, CashSession, CashSessionStatus
from apps.cash.services import open_session
from apps.commands.models import (
    Command, CommandStatus, Order, OrderItem, OrderItemStatus, OrderStatus,
    Table, TableStatus,
)
from apps.commands.services import (
    create_table, open_command, add_order_item, confirm_order_item,
    cancel_order_item, finalize_command,
)
from apps.inventory.models import (
    MovementType, MovementDomainOrigin, Stock, StockMovement,
)
from apps.products.models import (
    Category, Product, SalesChannel, Unit, InventoryBehavior,
)
from apps.sales.models import OperationType, Sale, SaleItem, SaleStatus
from apps.sales.services import (
    calculate_preview, calculate_command_preview, finalize_sale, cancel_sale,
    ensure_default_payment_methods,
)

PASSWORD = 'Block6-test-password-123!'


def create_user(email):
    return User.objects.create_user(email=email, password=PASSWORD)


def make_profile(company, name, codes):
    perms = []
    for code in codes:
        obj, _ = FunctionalPermission.objects.get_or_create(
            code=code,
            defaults={'module': code.split('.')[0], 'label': code, 'description': '', 'status': 'active'},
        )
        perms.append(obj)
    profile, _ = AccessProfile.objects.get_or_create(
        company=company, name=name,
        defaults={'description': name, 'is_system': False, 'status': 'active'},
    )
    profile.permissions.set(perms)
    return profile


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


class Block6Fixture:
    def setUp(self):
        super().setUp()
        ensure_permission_catalog()
        self.owner = create_user('owner@block6.com')
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='Block6 Co', legal_name='Block6 Co Legal',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        settings = self.branch.settings
        settings.uses_tables = True
        settings.uses_commands = True
        settings.uses_cash_register = True
        settings.uses_counter = True
        settings.uses_consumption = True
        settings.save()
        self.category = Category.objects.create(company=self.company, name='Bebidas')
        self.product = Product.objects.create(
            company=self.company, category=self.category, name='Cerveja',
            internal_code='CERV01', unit=Unit.UNIT, cost=Decimal('5.00'),
            sale_price=Decimal('10.00'), inventory_behavior=InventoryBehavior.DIRECT,
        )
        set_stock(self.branch, self.product, '100', '5.00')
        self.cash_register = CashRegister.objects.create(branch=self.branch, name='Caixa 1')
        self.payment_methods = ensure_default_payment_methods(self.company)
        self.cash_method = next(m for m in self.payment_methods if m.code == 'cash')

    def open_cash_session(self, user=None):
        return open_session(
            cash_register=self.cash_register, opening_amount=Decimal('100.00'),
            user=user or self.owner, current_branch=self.branch,
        )

    def finalize_cmd(self, cmd, user=None):
        """Helper to finalize a command with simple cash payment."""
        return finalize_command(
            command=cmd, user=user or self.owner, idempotency_key=uuid.uuid4(),
            cash_session=self.open_cash_session(user).pk,
            payments=[{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '1000.00'}],
        )


class MultipleCommandsPerTableTests(Block6Fixture, TestCase):
    def test_two_open_commands_same_table_both_remain_open(self):
        table = create_table(branch=self.branch, name='Mesa 3', user=self.owner)
        cmd_j = open_command(branch=self.branch, user=self.owner, table=table, identifier='Junior')
        cmd_v = open_command(branch=self.branch, user=self.owner, table=table, identifier='Vanessa')
        self.assertEqual(cmd_j.status, CommandStatus.OPEN)
        self.assertEqual(cmd_v.status, CommandStatus.OPEN)
        self.assertEqual(table.commands.filter(status=CommandStatus.OPEN).count(), 2)

    def test_table_with_zero_open_commands_is_free(self):
        table = create_table(branch=self.branch, name='Mesa 4', user=self.owner)
        self.assertEqual(table.commands.filter(status=CommandStatus.OPEN).count(), 0)

    def test_table_remains_occupied_when_one_of_two_finalizes(self):
        table = create_table(branch=self.branch, name='Mesa 5', user=self.owner)
        cmd1 = open_command(branch=self.branch, user=self.owner, table=table, identifier='A')
        cmd2 = open_command(branch=self.branch, user=self.owner, table=table, identifier='B')
        item = add_order_item(command=cmd1, user=self.owner, product_id=self.product.pk, quantity=Decimal('1'))
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        self.finalize_cmd(cmd1)
        self.assertEqual(table.commands.filter(status=CommandStatus.OPEN).count(), 1)

    def test_table_frees_when_last_command_finalizes(self):
        table = create_table(branch=self.branch, name='Mesa 6', user=self.owner)
        cmd = open_command(branch=self.branch, user=self.owner, table=table, identifier='Solo')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=Decimal('1'))
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        self.finalize_cmd(cmd)
        self.assertEqual(table.commands.filter(status=CommandStatus.OPEN).count(), 0)

    def test_command_identifier_preserved(self):
        cmd = open_command(branch=self.branch, user=self.owner, identifier='Comanda 42')
        self.assertEqual(cmd.identifier, 'Comanda 42')
        self.assertTrue(cmd.command_number.startswith('C'))


class CommandCashSessionTests(Block6Fixture, TestCase):
    def test_open_add_confirm_without_cash_session_allowed(self):
        cmd = open_command(branch=self.branch, user=self.owner, identifier='NoCash')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=Decimal('2'))
        item = confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        self.assertEqual(item.status, OrderItemStatus.CONFIRMED)

    def test_finalize_without_cash_session_raises(self):
        cmd = open_command(branch=self.branch, user=self.owner, identifier='NoFinal')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=Decimal('1'))
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        with self.assertRaises(Exception):
            finalize_command(
                command=cmd, user=self.owner, idempotency_key=uuid.uuid4(),
                cash_session=999999,
                payments=[{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '100.00'}],
            )

    def test_finalize_with_open_cash_session_allowed(self):
        cmd = open_command(branch=self.branch, user=self.owner, identifier='WithCash')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=Decimal('1'))
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        result = self.finalize_cmd(cmd)
        self.assertEqual(result.status, CommandStatus.CLOSED)
        self.assertIsNotNone(result.sale)


class CommandFinancialEngineTests(Block6Fixture, TestCase):
    def test_pdv_and_command_produce_same_total(self):
        quantity = Decimal('2')
        pdv_preview = calculate_preview(
            company=self.company, operation_type=OperationType.SALE,
            raw_items=[{'product': self.product.pk, 'quantity': str(quantity)}],
            discount=Decimal('0.00'), charged_amount=None, beneficiary_user=None,
            branch=self.branch, channel=SalesChannel.COUNTER,
        )
        cmd = open_command(branch=self.branch, user=self.owner, identifier='FinTest')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=quantity)
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        cmd_preview = calculate_command_preview(
            branch=self.branch, order_items=[item], discount=Decimal('0.00'),
        )
        self.assertEqual(pdv_preview['subtotal'], cmd_preview['subtotal'])
        self.assertEqual(pdv_preview['total'], cmd_preview['total'])

    def test_command_with_discount_and_service_fee_consistent(self):
        s = self.branch.settings
        s.charges_service_fee = True
        s.service_fee_rate = Decimal('10')
        s.save()
        quantity = Decimal('3')
        discount = Decimal('5.00')
        pdv_preview = calculate_preview(
            company=self.company, operation_type=OperationType.SALE,
            raw_items=[{'product': self.product.pk, 'quantity': str(quantity)}],
            discount=discount, charged_amount=None, beneficiary_user=None,
            branch=self.branch, channel=SalesChannel.COUNTER,
        )
        cmd = open_command(branch=self.branch, user=self.owner, identifier='DiscFee')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=quantity)
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        cmd_preview = calculate_command_preview(
            branch=self.branch, order_items=[item], discount=discount,
        )
        self.assertEqual(pdv_preview['subtotal'], cmd_preview['subtotal'])
        self.assertEqual(pdv_preview['total'], cmd_preview['total'])


class CommandFinalizePermissionTests(Block6Fixture, TestCase):
    def setUp(self):
        super().setUp()
        self.finalize_user = create_user('finalize@block6.com')
        profile = make_profile(self.company, 'Comanda Finalizer', [
            'commands.view', 'commands.open', 'commands.add_items',
            'commands.cancel_items', 'commands.finalize',
            'cash_registers.view', 'cash_registers.open',
            'payment_methods.view', 'products.view',
        ])
        UserCompanyAccess.objects.create(
            user=self.finalize_user, company=self.company,
            access_profile=profile, is_active=True,
        )
        UserBranchAccess.objects.create(
            user=self.finalize_user, branch=self.branch, access_profile=profile,
        )

    def test_user_with_commands_finalize_can_finalize(self):
        cmd = open_command(branch=self.branch, user=self.finalize_user, identifier='FinalUser')
        item = add_order_item(command=cmd, user=self.finalize_user, product_id=self.product.pk, quantity=Decimal('1'))
        confirm_order_item(item=item, user=self.finalize_user, idempotency_key=uuid.uuid4())
        session = open_session(
            cash_register=self.cash_register, opening_amount=Decimal('100.00'),
            user=self.finalize_user, current_branch=self.branch,
        )
        result = finalize_command(
            command=cmd, user=self.finalize_user, idempotency_key=uuid.uuid4(),
            cash_session=session.pk,
            payments=[{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '1000.00'}],
            seller_user=self.owner.pk,
        )
        self.assertEqual(result.status, CommandStatus.CLOSED)

    def test_same_user_cannot_create_sale_directly_via_api(self):
        client = APIClient()
        client.force_authenticate(user=self.finalize_user)
        resp = client.post('/api/v1/sales/finalize/', {
            'operation_type': 'sale',
            'items': [{'product': self.product.pk, 'quantity': '1'}],
            'payments': [{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '1000.00'}],
            'idempotency_key': str(uuid.uuid4()),
        }, format='json', HTTP_X_BRANCH_ID=str(self.branch.pk))
        self.assertIn(resp.status_code, (403, 400))


class CommandInventoryTests(Block6Fixture, TestCase):
    def test_confirm_deducts_once_finalize_does_not_deduct_again(self):
        cmd = open_command(branch=self.branch, user=self.owner, identifier='InvTest')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=Decimal('3'))
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        stock = Stock.objects.get(product=self.product, branch=self.branch)
        self.assertEqual(stock.current_quantity, Decimal('97'))
        sale_movements = StockMovement.objects.filter(
            order_item=item, movement_type=MovementType.SALE,
        )
        self.assertEqual(sale_movements.count(), 1)
        self.finalize_cmd(cmd)
        stock.refresh_from_db()
        self.assertEqual(stock.current_quantity, Decimal('97'))
        self.assertEqual(StockMovement.objects.filter(movement_type=MovementType.SALE).count(), 1)


class CommandCancellationTests(Block6Fixture, TestCase):
    def test_scenario_a_cancel_confirmed_before_finalize(self):
        cmd = open_command(branch=self.branch, user=self.owner, identifier='CancelA')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=Decimal('2'))
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        stock = Stock.objects.get(product=self.product, branch=self.branch)
        self.assertEqual(stock.current_quantity, Decimal('98'))
        item = cancel_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4(), reason='Wrong item')
        self.assertEqual(item.status, OrderItemStatus.CANCELLED)
        stock.refresh_from_db()
        self.assertEqual(stock.current_quantity, Decimal('100'))
        self.assertEqual(
            StockMovement.objects.filter(movement_type=MovementType.SALE, order_item=item).count(), 1,
        )
        self.assertEqual(
            StockMovement.objects.filter(movement_type=MovementType.SALE_CANCELLATION, order_item=item).count(), 1,
        )

    def test_scenario_b_cancel_sale_after_finalize(self):
        cmd = open_command(branch=self.branch, user=self.owner, identifier='CancelB')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=Decimal('2'))
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        self.assertEqual(
            Stock.objects.get(product=self.product, branch=self.branch).current_quantity, Decimal('98'),
        )
        self.finalize_cmd(cmd)
        cmd.refresh_from_db()
        sale = cmd.sale
        self.assertIsNotNone(sale)
        cancel_sale(sale=sale, branch=self.branch, user=self.owner, reason='Customer left')
        self.assertEqual(
            Stock.objects.get(product=self.product, branch=self.branch).current_quantity, Decimal('100'),
        )
        self.assertEqual(StockMovement.objects.filter(movement_type=MovementType.SALE).count(), 1)
        self.assertEqual(StockMovement.objects.filter(movement_type=MovementType.SALE_CANCELLATION).count(), 1)

    def test_cancel_pending_item_no_stock_movement(self):
        cmd = open_command(branch=self.branch, user=self.owner, identifier='CancelPend')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=Decimal('1'))
        item = cancel_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4(), reason='Cancelled pending')
        self.assertEqual(StockMovement.objects.filter(order_item=item).count(), 0)
        self.assertEqual(item.status, OrderItemStatus.CANCELLED)

    def test_cancel_idempotent(self):
        cmd = open_command(branch=self.branch, user=self.owner, identifier='CancelIdem')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=Decimal('1'))
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        key = uuid.uuid4()
        cancel_order_item(item=item, user=self.owner, idempotency_key=key, reason='First')
        result = cancel_order_item(item=item, user=self.owner, idempotency_key=key, reason='Second')
        self.assertEqual(result.status, OrderItemStatus.CANCELLED)


class TraceabilityTests(Block6Fixture, TestCase):
    def test_full_traceability_chain(self):
        cmd = open_command(branch=self.branch, user=self.owner, identifier='Trace')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=Decimal('2'))
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        movement = StockMovement.objects.get(order_item=item, movement_type=MovementType.SALE)
        self.assertEqual(movement.domain_origin, MovementDomainOrigin.ORDER)
        self.assertIsNotNone(movement.operation_reference)
        self.finalize_cmd(cmd)
        cmd.refresh_from_db()
        sale = cmd.sale
        self.assertIsNotNone(sale)
        self.assertEqual(sale.operation_type, OperationType.SALE)
        self.assertEqual(sale.channel, SalesChannel.COMMAND)
        sale_item = SaleItem.objects.get(sale=sale)
        self.assertEqual(sale_item.product_id, self.product.pk)
        self.assertEqual(sale_item.quantity, Decimal('2'))

    def test_cancel_sale_finds_movements_via_order_item_chain(self):
        cmd = open_command(branch=self.branch, user=self.owner, identifier='TraceCancel')
        item = add_order_item(command=cmd, user=self.owner, product_id=self.product.pk, quantity=Decimal('1'))
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())
        self.finalize_cmd(cmd)
        cmd.refresh_from_db()
        sale = cmd.sale
        cancel_sale(sale=sale, branch=self.branch, user=self.owner, reason='Test cancel')
        original = StockMovement.objects.filter(
            movement_type=MovementType.SALE, order_item=item,
        ).first()
        self.assertIsNotNone(original)
        reversal = StockMovement.objects.filter(original_movement=original).first()
        self.assertIsNotNone(reversal)
        self.assertEqual(reversal.order_item_id, item.pk)
