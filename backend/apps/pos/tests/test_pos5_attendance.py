from decimal import Decimal
from uuid import uuid4

from django.test import TestCase

from apps.accounts.models import User
from apps.attendance.models import AttendanceOrderItem
from apps.attendance.services import (
    AttendanceConflict, add_order_items, command_summary, confirm_order_item,
    finalize_command, open_command, record_payment, transfer_items,
)
from apps.cash.models import CashRegister
from apps.cash.services import open_session
from apps.companies.services import create_company_with_matrix
from apps.inventory.models import Stock, StockMovement
from apps.products.models import (
    Category, InventoryBehavior, Product, ProductBranchConfig, Unit,
)
from apps.production.models import Ticket
from apps.sales.models import Sale
from apps.sales.services import ensure_default_payment_methods


class POS5AttendanceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='pos5-owner@example.com', password='POS5-owner-password-123!',
        )
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='POS5', legal_name='POS5 Legal',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        settings = self.branch.settings
        settings.uses_tables = True
        settings.uses_commands = True
        settings.uses_cash_register = True
        settings.save(update_fields=(
            'uses_tables', 'uses_commands', 'uses_cash_register', 'updated_at',
        ))
        self.category = Category.objects.create(
            company=self.company, branch=self.branch, name='POS5 Drinks',
        )
        self.product = Product.objects.create(
            company=self.company, category=self.category, name='POS5 Ticket Drink',
            internal_code='POS5-DRINK', unit=Unit.UNIT, cost=Decimal('5.00'),
            sale_price=Decimal('10.00'), inventory_behavior=InventoryBehavior.DIRECT,
            emits_ticket=True,
        )
        ProductBranchConfig.objects.create(
            product=self.product, branch=self.branch, category=self.category,
        )
        Stock.objects.update_or_create(
            product=self.product, branch=self.branch,
            defaults={
                'current_quantity': Decimal('100.000'),
                'average_unit_cost': Decimal('5.00'),
                'last_unit_cost': Decimal('5.00'),
            },
        )
        self.cash_register = CashRegister.objects.create(branch=self.branch, name='POS5 Cash')
        self.cash_session = open_session(
            self.cash_register, Decimal('0.00'), self.owner, self.branch,
        )
        self.cash_method = next(
            method for method in ensure_default_payment_methods(self.company)
            if method.code == 'cash'
        )

    def open_standalone(self, *, key=None, identifier='Standalone'):
        return open_command(
            branch=self.branch, user=self.owner, idempotency_key=key or uuid4(),
            identifier=identifier,
        )

    def add_confirmed_item(self, command):
        _, items, _ = add_order_items(
            command=command, user=self.owner,
            items=[{'product': self.product.pk, 'quantity': Decimal('1.000')}],
            idempotency_key=uuid4(),
        )
        return confirm_order_item(item=items[0], user=self.owner, idempotency_key=uuid4())

    def close(self, command):
        return finalize_command(
            command=command, user=self.owner, cash_session_id=self.cash_session.pk,
            payments=[{
                'payment_method': self.cash_method.pk, 'amount': 'auto',
                'received_amount': '20.00',
            }],
            idempotency_key=uuid4(),
        )

    def test_standalone_open_is_idempotent(self):
        key = uuid4()
        first, replayed = self.open_standalone(key=key, identifier='Balcao')
        replay, replayed_again = self.open_standalone(key=key, identifier='Balcao')

        self.assertFalse(replayed)
        self.assertTrue(replayed_again)
        self.assertEqual(first.pk, replay.pk)
        self.assertIsNone(first.table_id)

    def test_confirm_and_finalization_do_not_duplicate_stock_or_ticket(self):
        command, _ = self.open_standalone()
        items_key = uuid4()
        _, items, replayed_items = add_order_items(
            command=command, user=self.owner,
            items=[{'product': self.product.pk, 'quantity': Decimal('1.000')}],
            idempotency_key=items_key,
        )
        item = items[0]
        _, replay_items, replayed_again = add_order_items(
            command=command, user=self.owner,
            items=[{'product': self.product.pk, 'quantity': Decimal('1.000')}],
            idempotency_key=items_key,
        )
        self.assertFalse(replayed_items)
        self.assertTrue(replayed_again)
        self.assertEqual([row.pk for row in replay_items], [item.pk])

        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid4())
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid4())
        closed = self.close(command)
        replayed = finalize_command(
            command=closed, user=self.owner, cash_session_id=self.cash_session.pk,
            payments=[], idempotency_key=closed.sale.idempotency_key,
        )

        self.assertEqual(replayed.pk, closed.pk)
        self.assertEqual(StockMovement.objects.filter(attendance_order_item=item).count(), 1)
        self.assertEqual(Ticket.objects.filter(source_attendance_order_item=item).count(), 1)
        self.assertEqual(Sale.objects.filter(attendance_command=command).count(), 1)

    def test_partial_payment_keeps_the_remaining_command_balance(self):
        command, _ = self.open_standalone()
        self.add_confirmed_item(command)

        record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )

        self.assertEqual(command_summary(command)['paid_total'], '4.00')
        self.assertEqual(command_summary(command)['remaining_balance'], '6.00')

    def test_item_transfers_keep_history_between_standalone_commands(self):
        source, _ = self.open_standalone(identifier='Source')
        destination, _ = self.open_standalone(identifier='Destination')
        _, items, _ = add_order_items(
            command=source, user=self.owner,
            items=[{'product': self.product.pk, 'quantity': Decimal('2.000')}],
            idempotency_key=uuid4(),
        )
        destination, moved, replayed = transfer_items(
            command=source, destination_id=destination.pk,
            items=[{'item': items[0].pk, 'quantity': Decimal('1.000')}],
            user=self.owner, idempotency_key=uuid4(),
        )

        self.assertFalse(replayed)
        self.assertEqual(len(moved), 1)
        self.assertEqual(AttendanceOrderItem.objects.get(pk=moved[0]).order.command_id, destination.pk)

    def test_item_transfer_with_partial_payment_is_blocked(self):
        source, _ = self.open_standalone(identifier='Paid source')
        destination, _ = self.open_standalone(identifier='Destination')
        item = self.add_confirmed_item(source)
        record_payment(
            command=source, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )
        with self.assertRaises(AttendanceConflict) as conflict:
            transfer_items(
                command=source, destination_id=destination.pk,
                items=[{'item': item.pk, 'quantity': Decimal('1.000')}],
                user=self.owner, idempotency_key=uuid4(),
            )

        self.assertEqual(conflict.exception.code, 'command_payments_transfer_unsupported')
