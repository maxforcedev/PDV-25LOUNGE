from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.attendance.models import AttendanceCommand, TableAttendance, TableAttendanceStatus, TablePayment
from apps.attendance.services import (
    AttendanceConflict, close_table_attendance, open_table_attendance,
    record_table_payment, reverse_table_payment, save_table_order, table_summary,
)
from apps.cash.models import CashRegister
from apps.cash.services import close_session, open_session
from apps.commands.services import create_table
from apps.companies.services import create_company_with_matrix
from apps.inventory.models import Stock
from apps.pos.models import POSDevice
from apps.products.models import Category, InventoryBehavior, Product, ProductBranchConfig, Unit
from apps.sales.services import ensure_default_payment_methods


class TableAttendanceRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='table-regression@example.com', password='table-regression-password')
        self.company = create_company_with_matrix(creator=self.user, trade_name='Tables', legal_name='Tables Legal')
        self.branch = self.company.branches.get(is_matrix=True)
        self.branch.settings.uses_tables = True
        self.branch.settings.uses_commands = False
        self.branch.settings.uses_cash_register = True
        self.branch.settings.save()
        category = Category.objects.create(company=self.company, branch=self.branch, name='Table category')
        self.product = Product.objects.create(company=self.company, category=category, name='Table item', internal_code='TABLE-ITEM', unit=Unit.UNIT, cost=Decimal('2.00'), sale_price=Decimal('10.00'), inventory_behavior=InventoryBehavior.DIRECT)
        ProductBranchConfig.objects.create(product=self.product, branch=self.branch, category=category, available_table=True)
        Stock.objects.create(product=self.product, branch=self.branch, current_quantity=Decimal('20.000'), average_unit_cost=Decimal('2.00'), last_unit_cost=Decimal('2.00'))
        register = CashRegister.objects.create(branch=self.branch, name='Table cash')
        self.cash_session = open_session(register, Decimal('0.00'), self.user, self.branch)
        self.device = POSDevice.objects.create(
            branch=self.branch, name='Table POS', status=POSDevice.Status.ACTIVE,
            active_cash_session=self.cash_session,
        )
        self.cash_method = next(method for method in ensure_default_payment_methods(self.company) if method.code == 'cash')
        self.pix_method = next(method for method in ensure_default_payment_methods(self.company) if method.code == 'pix')
        self.credit_method = next(method for method in ensure_default_payment_methods(self.company) if method.code == 'credit_card')

    def _table_with_order(self, name):
        table = create_table(branch=self.branch, name=name, user=self.user)
        attendance, _ = open_table_attendance(
            branch=self.branch, table_id=table.pk, user=self.user, idempotency_key=uuid4(),
        )
        save_table_order(
            attendance=attendance, user=self.user,
            items=[{'product': self.product.pk, 'quantity': Decimal('1.000')}],
            idempotency_key=uuid4(),
        )
        return attendance

    def test_empty_table_closes_without_sale_or_command(self):
        table = create_table(branch=self.branch, name='Empty table', user=self.user)
        attendance, _ = open_table_attendance(branch=self.branch, table_id=table.pk, user=self.user, idempotency_key=uuid4())
        closed, _ = close_table_attendance(attendance=attendance, user=self.user, idempotency_key=uuid4(), pos_device=self.device)
        self.assertEqual(closed.status, TableAttendanceStatus.CLOSED)
        self.assertIsNone(closed.sale_id)
        self.assertFalse(AttendanceCommand.objects.filter(table=table).exists())

    def test_paid_table_closes_to_sale_without_command(self):
        table = create_table(branch=self.branch, name='Paid table', user=self.user)
        attendance, _ = open_table_attendance(branch=self.branch, table_id=table.pk, user=self.user, idempotency_key=uuid4())
        save_table_order(attendance=attendance, user=self.user, items=[{'product': self.product.pk, 'quantity': Decimal('1.000')}], idempotency_key=uuid4())
        payment, _ = record_table_payment(attendance=attendance, user=self.user, payment_method_id=self.cash_method.pk, pos_device=self.device, amount=Decimal('10.00'), received_amount=Decimal('10.00'), idempotency_key=uuid4())
        self.assertEqual(payment.change_amount, Decimal('0.00'))
        closed, _ = close_table_attendance(attendance=attendance, user=self.user, idempotency_key=uuid4(), pos_device=self.device)
        self.assertEqual(closed.status, TableAttendanceStatus.CLOSED)
        self.assertIsNotNone(closed.sale_id)
        self.assertFalse(AttendanceCommand.objects.filter(table=table).exists())

    def test_close_rejects_historical_non_cash_payment_from_another_device_context(self):
        table = create_table(branch=self.branch, name='Context table', user=self.user)
        attendance, _ = open_table_attendance(branch=self.branch, table_id=table.pk, user=self.user, idempotency_key=uuid4())
        save_table_order(attendance=attendance, user=self.user, items=[{'product': self.product.pk, 'quantity': Decimal('1.000')}], idempotency_key=uuid4())
        card_method = next(method for method in ensure_default_payment_methods(self.company) if method.code != 'cash')
        payment, _ = record_table_payment(
            attendance=attendance, user=self.user, payment_method_id=card_method.pk,
            pos_device=self.device, amount=Decimal('10.00'), idempotency_key=uuid4(),
        )
        self.assertEqual(payment.cash_session_id, self.cash_session.pk)
        other_register = CashRegister.objects.create(branch=self.branch, name='Other table cash')
        other_session = open_session(other_register, Decimal('0.00'), self.user, self.branch)
        self.device.active_cash_session = other_session
        self.device.save(update_fields=('active_cash_session', 'updated_at'))

        with self.assertRaises(AttendanceConflict) as error:
            close_table_attendance(
                attendance=attendance, user=self.user, idempotency_key=uuid4(), pos_device=self.device,
            )

        self.assertEqual(error.exception.code, 'table_cash_session_mismatch')

    def test_payment_rejects_a_changed_pos_cash_context_before_writing(self):
        table = create_table(branch=self.branch, name='Payment context table', user=self.user)
        attendance, _ = open_table_attendance(
            branch=self.branch, table_id=table.pk, user=self.user, idempotency_key=uuid4(),
        )
        save_table_order(
            attendance=attendance, user=self.user,
            items=[{'product': self.product.pk, 'quantity': Decimal('2.000')}],
            idempotency_key=uuid4(),
        )
        record_table_payment(
            attendance=attendance, user=self.user, payment_method_id=self.cash_method.pk,
            pos_device=self.device, amount=Decimal('10.00'), received_amount=Decimal('10.00'),
            idempotency_key=uuid4(),
        )
        other_register = CashRegister.objects.create(branch=self.branch, name='Other payment cash')
        other_session = open_session(other_register, Decimal('0.00'), self.user, self.branch)
        self.device.active_cash_session = other_session
        self.device.save(update_fields=('active_cash_session', 'updated_at'))

        with self.assertRaises(AttendanceConflict) as error:
            record_table_payment(
                attendance=attendance, user=self.user, payment_method_id=self.cash_method.pk,
                pos_device=self.device, amount=Decimal('10.00'), received_amount=Decimal('10.00'),
                idempotency_key=uuid4(),
            )

        self.assertEqual(error.exception.code, 'table_cash_session_mismatch')
        self.assertEqual(TablePayment.objects.filter(attendance=attendance).count(), 1)

    def test_reversed_payment_allows_new_session_and_table_close(self):
        attendance = self._table_with_order('Reversed payment context table')
        payment, _ = record_table_payment(
            attendance=attendance, user=self.user, payment_method_id=self.cash_method.pk,
            pos_device=self.device, amount=Decimal('10.00'), received_amount=Decimal('10.00'),
            idempotency_key=uuid4(),
        )
        reverse_table_payment(
            payment=payment, user=self.user, reason='Operator correction', idempotency_key=uuid4(),
        )
        other_register = CashRegister.objects.create(branch=self.branch, name='Reversal replacement cash')
        other_session = open_session(other_register, Decimal('0.00'), self.user, self.branch)
        self.device.active_cash_session = other_session
        self.device.save(update_fields=('active_cash_session', 'updated_at'))

        replacement, _ = record_table_payment(
            attendance=attendance, user=self.user, payment_method_id=self.cash_method.pk,
            pos_device=self.device, amount=Decimal('10.00'), received_amount=Decimal('10.00'),
            idempotency_key=uuid4(),
        )
        closed, _ = close_table_attendance(
            attendance=attendance, user=self.user, idempotency_key=uuid4(), pos_device=self.device,
        )

        self.assertEqual(replacement.cash_session_id, other_session.pk)
        self.assertEqual(closed.status, TableAttendanceStatus.CLOSED)
        self.assertEqual(closed.sale.cash_session_id, other_session.pk)

    def test_close_rejects_simultaneous_active_payment_sessions(self):
        table = create_table(branch=self.branch, name='Inconsistent payment context table', user=self.user)
        attendance, _ = open_table_attendance(
            branch=self.branch, table_id=table.pk, user=self.user, idempotency_key=uuid4(),
        )
        save_table_order(
            attendance=attendance, user=self.user,
            items=[{'product': self.product.pk, 'quantity': Decimal('2.000')}],
            idempotency_key=uuid4(),
        )
        record_table_payment(
            attendance=attendance, user=self.user, payment_method_id=self.cash_method.pk,
            pos_device=self.device, amount=Decimal('10.00'), received_amount=Decimal('10.00'),
            idempotency_key=uuid4(),
        )
        other_register = CashRegister.objects.create(branch=self.branch, name='Inconsistent context cash')
        other_session = open_session(other_register, Decimal('0.00'), self.user, self.branch)
        TablePayment.objects.create(
            attendance=attendance, payment_method=self.cash_method, amount=Decimal('10.00'),
            received_amount=Decimal('10.00'), cash_session=other_session, operator=self.user,
        )
        self.device.active_cash_session = other_session
        self.device.save(update_fields=('active_cash_session', 'updated_at'))

        with self.assertRaises(AttendanceConflict) as error:
            close_table_attendance(
                attendance=attendance, user=self.user, idempotency_key=uuid4(), pos_device=self.device,
            )

        self.assertEqual(error.exception.code, 'table_cash_session_mismatch')

    def test_pix_payment_on_open_table_blocks_cash_session_close(self):
        attendance = self._table_with_order('PIX cash-close block table')
        record_table_payment(
            attendance=attendance, user=self.user, payment_method_id=self.pix_method.pk,
            pos_device=self.device, amount=Decimal('10.00'), idempotency_key=uuid4(),
        )

        with self.assertRaises(ValidationError):
            close_session(self.cash_session, Decimal('0.00'), self.user, self.branch)

        close_table_attendance(
            attendance=attendance, user=self.user, idempotency_key=uuid4(), pos_device=self.device,
        )
        closed = close_session(self.cash_session, Decimal('0.00'), self.user, self.branch)

        self.assertEqual(closed.status, 'closed')

    def test_credit_payment_on_open_table_blocks_cash_session_close(self):
        attendance = self._table_with_order('Credit cash-close block table')
        record_table_payment(
            attendance=attendance, user=self.user, payment_method_id=self.credit_method.pk,
            pos_device=self.device, amount=Decimal('10.00'), idempotency_key=uuid4(),
        )

        with self.assertRaises(ValidationError):
            close_session(self.cash_session, Decimal('0.00'), self.user, self.branch)

    def test_prospective_equal_split_is_available_but_not_active(self):
        table = create_table(branch=self.branch, name='Equal split table', user=self.user)
        attendance, _ = open_table_attendance(
            branch=self.branch, table_id=table.pk, user=self.user, people_count=2,
            idempotency_key=uuid4(),
        )
        save_table_order(
            attendance=attendance, user=self.user,
            items=[{'product': self.product.pk, 'quantity': Decimal('1.000')}],
            idempotency_key=uuid4(),
        )

        split = table_summary(attendance)['equal_split']

        self.assertTrue(split['available'])
        self.assertFalse(split['active'])
