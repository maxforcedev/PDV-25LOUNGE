from decimal import Decimal
from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import User
from apps.attendance.models import AttendanceOrderItem
from apps.attendance.services import (
    AttendanceConflict, add_order_items, command_summary, confirm_order_item,
    finalize_command, financial_state, open_command, record_payment, reverse_payment,
    set_command_seller, transfer_items,
)
from apps.cash.models import CashRegister
from apps.cash.services import open_session
from apps.companies.models import Status, UserBranchAccess, UserCommissionOverride, UserCompanyAccess
from apps.inventory.models import Stock, StockMovement
from apps.products.models import (
    Category, InventoryBehavior, Product, ProductBranchConfig, Unit,
)
from apps.production.models import Ticket
from apps.sales.models import Promotion, PromotionDiscountType, Sale
from apps.sales.services import ensure_default_payment_methods
from apps.saas.tests.helpers import create_complete_test_plan, create_operational_test_tenant


class POS5AttendanceTests(TestCase):
    def setUp(self):
        self.owner, self.company, self.subscription = create_operational_test_tenant(
            code='pos5-attendance',
            email='pos5-owner@example.com',
            password='POS5-owner-password-123!',
            trade_name='POS5',
            legal_name='POS5 Legal',
            plan_version=create_complete_test_plan(
                'pos5-attendance',
                enabled_features=(
                    'tables', 'commands', 'cash_register', 'production', 'products', 'inventory',
                    'financial', 'promotions',
                ),
            ),
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

    def seller(self, *, commission_rate=None, receives_commission=True):
        seller = User.objects.create_user(
            email=f'pos5-seller-{uuid4()}@example.com', password='POS5-seller-password-123!',
        )
        profile = self.owner.company_accesses.get(company=self.company).access_profile
        UserCompanyAccess.objects.create(
            user=seller, company=self.company, access_profile=profile,
        )
        UserBranchAccess.objects.create(
            user=seller, branch=self.branch, access_profile=profile,
        )
        UserCommissionOverride.objects.create(
            branch=self.branch, user=seller, updated_by=self.owner,
            receives_commission=receives_commission, commission_rate=commission_rate,
        )
        return seller

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

    def test_finalized_command_uses_the_seller_commission_rate(self):
        settings = self.branch.settings
        settings.commission_rate = Decimal('5.00')
        settings.save(update_fields=('commission_rate', 'updated_at'))
        command, _ = self.open_standalone()
        self.add_confirmed_item(command)

        closed = self.close(command)

        self.assertEqual(closed.sale.commission_rate, Decimal('5.00'))
        self.assertEqual(closed.sale.commission_amount, Decimal('0.50'))

    def test_command_commission_uses_responsible_seller_and_frozen_override(self):
        seller = self.seller(commission_rate=Decimal('7.00'))
        command, _ = open_command(
            branch=self.branch, user=self.owner, seller_user=seller.pk,
            idempotency_key=uuid4(), identifier='Seller owner',
        )
        self.add_confirmed_item(command)
        record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )
        override = seller.commission_overrides.get(branch=self.branch)
        override.commission_rate = Decimal('11.00')
        override.save(update_fields=('commission_rate', 'updated_at'))

        closed = self.close(command)

        self.assertEqual(closed.sale.seller_user_id, seller.pk)
        self.assertEqual(closed.sale.created_by_id, self.owner.pk)
        self.assertEqual(closed.closed_by_id, self.owner.pk)
        self.assertEqual(closed.sale.commission_rate, Decimal('7.00'))
        self.assertEqual(closed.sale.commission_amount, Decimal('0.70'))

    def test_command_seller_without_commission_keeps_zero_rate(self):
        seller = self.seller(receives_commission=False)
        command, _ = open_command(
            branch=self.branch, user=self.owner, seller_user=seller.pk,
            idempotency_key=uuid4(), identifier='No commission',
        )
        self.add_confirmed_item(command)

        closed = self.close(command)

        self.assertEqual(closed.sale.seller_user_id, seller.pk)
        self.assertEqual(closed.sale.commission_rate, Decimal('0.00'))
        self.assertEqual(closed.sale.commission_amount, Decimal('0.00'))

    def test_historical_paid_command_requires_assignment_without_retroactive_commission(self):
        seller = self.seller(commission_rate=Decimal('9.00'))
        command, _ = self.open_standalone(identifier='Historical')
        self.add_confirmed_item(command)
        record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )
        type(command).objects.filter(pk=command.pk).update(
            seller_user=None, commission_rate_snapshot=None,
        )
        command.refresh_from_db()
        assigned, replayed = set_command_seller(
            command=command, user=self.owner, seller_user=seller.pk, idempotency_key=uuid4(),
        )

        closed = self.close(assigned)

        self.assertFalse(replayed)
        self.assertEqual(closed.sale.seller_user_id, seller.pk)
        self.assertEqual(closed.sale.commission_rate, Decimal('0.00'))
        self.assertEqual(closed.sale.commission_amount, Decimal('0.00'))

    def test_new_command_without_seller_cannot_record_first_payment(self):
        command, _ = self.open_standalone(identifier='Missing seller')
        type(command).objects.filter(pk=command.pk).update(seller_user=None)
        command.refresh_from_db()
        self.add_confirmed_item(command)

        with self.assertRaises(ValidationError) as error:
            record_payment(
                command=command, user=self.owner, payment_method_id=self.cash_method.pk,
                amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
                idempotency_key=uuid4(),
            )

        self.assertIn('seller_user', error.exception.message_dict)

    def test_payment_idempotency_replay_remains_valid_after_seller_data_is_missing(self):
        command, _ = self.open_standalone(identifier='Payment replay')
        self.add_confirmed_item(command)
        key = uuid4()
        first = record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=key,
        )
        type(command).objects.filter(pk=command.pk).update(seller_user=None)
        command.refresh_from_db()

        replay = record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=key,
        )

        self.assertEqual(replay.pk, first.pk)

    def test_historical_unpaid_command_can_be_regularized_before_payment(self):
        seller = self.seller(commission_rate=Decimal('9.00'))
        command, _ = self.open_standalone(identifier='Historical unpaid')
        type(command).objects.filter(pk=command.pk).update(
            seller_user=None, commission_rate_snapshot=None,
        )
        command.refresh_from_db()
        self.add_confirmed_item(command)
        with self.assertRaises(ValidationError):
            record_payment(
                command=command, user=self.owner, payment_method_id=self.cash_method.pk,
                amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
                idempotency_key=uuid4(),
            )

        regularized, _ = set_command_seller(
            command=command, user=self.owner, seller_user=seller.pk, idempotency_key=uuid4(),
        )
        record_payment(
            command=regularized, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )
        closed = self.close(regularized)

        self.assertEqual(closed.sale.commission_rate, Decimal('9.00'))

    def test_seller_cannot_change_after_payment_starts(self):
        command, _ = self.open_standalone(identifier='Locked seller')
        self.add_confirmed_item(command)
        record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )

        with self.assertRaises(AttendanceConflict) as error:
            set_command_seller(
                command=command, user=self.owner, seller_user=self.seller().pk,
                idempotency_key=uuid4(),
            )

        self.assertEqual(error.exception.code, 'command_seller_locked')

    def test_first_payment_freezes_item_financial_participation(self):
        config = ProductBranchConfig.objects.get(product=self.product, branch=self.branch)
        config.participates_in_service_fee = True
        config.participates_in_commission = True
        config.save(update_fields=(
            'participates_in_service_fee', 'participates_in_commission', 'updated_at',
        ))
        command, _ = self.open_standalone(identifier='Frozen participation')
        self.add_confirmed_item(command)
        record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )
        config.participates_in_service_fee = False
        config.participates_in_commission = False
        config.save(update_fields=(
            'participates_in_service_fee', 'participates_in_commission', 'updated_at',
        ))

        closed = self.close(command)
        item = closed.sale.items.get()

        self.assertTrue(item.participates_in_service_fee)
        self.assertTrue(item.participates_in_commission)

    def test_paid_command_keeps_ended_promotion_and_only_applies_new_promotion_to_new_item(self):
        promotion = Promotion.objects.create(
            company=self.company, branch=self.branch, name='POS5 initial promotion',
            discount_type=PromotionDiscountType.PERCENTAGE, discount_value=Decimal('10.00'),
            starts_at=timezone.now() - timedelta(minutes=1), status=Status.ACTIVE,
        )
        promotion.products.add(self.product)
        command, _ = self.open_standalone(identifier='Frozen promotion')
        self.add_confirmed_item(command)
        record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )
        promotion.status = Status.INACTIVE
        promotion.save(update_fields=('status', 'updated_at'))
        later_promotion = Promotion.objects.create(
            company=self.company, branch=self.branch, name='POS5 later promotion',
            discount_type=PromotionDiscountType.PERCENTAGE, discount_value=Decimal('50.00'),
            starts_at=timezone.now() - timedelta(minutes=1), status=Status.ACTIVE,
        )
        later_promotion.products.add(self.product)
        _order, items, _ = add_order_items(
            command=command, user=self.owner,
            items=[{'product': self.product.pk, 'quantity': Decimal('1.000')}],
            idempotency_key=uuid4(),
        )
        confirm_order_item(item=items[0], user=self.owner, idempotency_key=uuid4())

        preview, _paid, _remaining = financial_state(command)

        self.assertEqual(preview['promotion_discount_total'], Decimal('6.00'))
        self.assertEqual(
            [item['promotion_benefit'] for item in preview['items']],
            [Decimal('1.00'), Decimal('5.00')],
        )
        closed = self.close(command)
        self.assertEqual(closed.sale.promotion_discount_total, Decimal('6.00'))

    def test_first_payment_freezes_service_fee_rate(self):
        settings = self.branch.settings
        settings.charges_service_fee = True
        settings.service_fee_rate = Decimal('10.00')
        settings.save(update_fields=('charges_service_fee', 'service_fee_rate', 'updated_at'))
        command, _ = self.open_standalone(identifier='Frozen service fee')
        self.add_confirmed_item(command)
        record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='5.00', received_amount='5.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )
        command.refresh_from_db()
        settings.service_fee_rate = Decimal('15.00')
        settings.save(update_fields=('service_fee_rate', 'updated_at'))

        preview, _paid, remaining = financial_state(command)

        self.assertEqual(command.service_fee_rate_snapshot, Decimal('10.00'))
        self.assertEqual(preview['service_fee_rate'], Decimal('10.00'))
        self.assertEqual(preview['service_fee_amount'], Decimal('1.00'))
        self.assertEqual(remaining, Decimal('6.00'))
        closed = self.close(command)
        self.assertEqual(closed.sale.service_fee_rate, Decimal('10.00'))
        self.assertEqual(closed.sale.service_fee_amount, Decimal('1.00'))

    def test_disabled_service_fee_freezes_without_charge(self):
        settings = self.branch.settings
        settings.charges_service_fee = False
        settings.service_fee_rate = Decimal('10.00')
        settings.save(update_fields=('charges_service_fee', 'service_fee_rate', 'updated_at'))
        command, _ = self.open_standalone(identifier='No service fee')
        self.add_confirmed_item(command)
        record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )
        command.refresh_from_db()
        settings.charges_service_fee = True
        settings.service_fee_rate = Decimal('15.00')
        settings.save(update_fields=('charges_service_fee', 'service_fee_rate', 'updated_at'))

        preview, _paid, _remaining = financial_state(command)

        self.assertEqual(command.service_fee_rate_snapshot, Decimal('0.00'))
        self.assertEqual(preview['service_fee_amount'], Decimal('0.00'))

    def test_waived_service_fee_remains_zero_with_its_rate_snapshot(self):
        settings = self.branch.settings
        settings.charges_service_fee = True
        settings.service_fee_rate = Decimal('10.00')
        settings.save(update_fields=('charges_service_fee', 'service_fee_rate', 'updated_at'))
        command, _ = self.open_standalone(identifier='Waived service fee')
        self.add_confirmed_item(command)
        record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            service_fee_waived=True, idempotency_key=uuid4(),
        )
        command.refresh_from_db()
        settings.service_fee_rate = Decimal('15.00')
        settings.save(update_fields=('service_fee_rate', 'updated_at'))

        preview, _paid, _remaining = financial_state(command)

        self.assertEqual(command.service_fee_rate_snapshot, Decimal('10.00'))
        self.assertEqual(preview['service_fee_amount'], Decimal('0.00'))

    def test_custom_commission_remains_independent_from_service_fee_snapshot(self):
        seller = self.seller(commission_rate=Decimal('7.00'))
        settings = self.branch.settings
        settings.charges_service_fee = True
        settings.service_fee_rate = Decimal('10.00')
        settings.save(update_fields=('charges_service_fee', 'service_fee_rate', 'updated_at'))
        command, _ = open_command(
            branch=self.branch, user=self.owner, seller_user=seller.pk,
            idempotency_key=uuid4(), identifier='Independent rates',
        )
        self.add_confirmed_item(command)
        record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='5.00', received_amount='5.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )
        command.refresh_from_db()
        settings.service_fee_rate = Decimal('15.00')
        settings.save(update_fields=('service_fee_rate', 'updated_at'))

        preview, _paid, _remaining = financial_state(command)

        self.assertEqual(preview['service_fee_rate'], Decimal('10.00'))
        self.assertEqual(preview['commission_rate'], Decimal('7.00'))
        self.assertEqual(preview['commission_amount'], Decimal('0.70'))

    def test_historical_paid_command_does_not_invent_service_fee_snapshot(self):
        command, _ = self.open_standalone(identifier='Historical service fee')
        self.add_confirmed_item(command)
        payment = record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )
        type(command).objects.filter(pk=command.pk).update(service_fee_rate_snapshot=None)
        command.refresh_from_db()
        reverse_payment(
            payment=payment, user=self.owner, reason='Teste de legado', idempotency_key=uuid4(),
        )

        record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='2.00', received_amount='2.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )
        command.refresh_from_db()

        self.assertIsNone(command.service_fee_rate_snapshot)

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
