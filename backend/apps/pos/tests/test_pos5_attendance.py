from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.attendance.models import (
    AttendanceCommand, AttendanceCommandStatus, AttendanceOrderItem,
    AttendanceTableGroupMembership,
)
from apps.attendance.services import (
    AttendanceConflict, add_order_items, command_summary, confirm_order_item,
    finalize_command, open_command, open_table, record_payment, transfer_command,
    transfer_items, group_tables, separate_table_from_group, set_bill_requested,
)
from apps.base.models import AuditLog
from apps.cash.models import CashRegister
from apps.cash.services import open_session
from apps.commands.models import Command
from apps.commands.services import create_table, open_command as open_legacy_command
from apps.companies.models import FunctionalPermission, UserPermissionBlock
from apps.companies.services import create_branch_with_access, create_company_with_matrix
from apps.inventory.models import Stock, StockMovement
from apps.pos.models import POSDevice, POSOperatorSession
from apps.pos.services import _secret_fingerprint, modules_for
from apps.products.models import (
    Category, InventoryBehavior, Product, ProductBranchConfig,
    ProductProductionDestination, ProductionDestination, Unit,
)
from apps.production.models import ProductionJob, Ticket
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
        destination = ProductionDestination.objects.create(
            branch=self.branch, name='POS5 Kitchen', code='pos5-kitchen',
        )
        ProductProductionDestination.objects.create(
            product=self.product, destination=destination,
        )
        self.cash_register = CashRegister.objects.create(branch=self.branch, name='POS5 Cash')
        self.cash_session = open_session(
            self.cash_register, Decimal('0.00'), self.owner, self.branch,
        )
        self.cash_method = next(
            method for method in ensure_default_payment_methods(self.company)
            if method.code == 'cash'
        )

    def open_standalone(self, *, key=None, identifier='Standalone', table_id=None):
        return open_command(
            branch=self.branch, user=self.owner, idempotency_key=key or uuid4(),
            identifier=identifier, table_id=table_id,
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

    def pos_client(self):
        self.owner.can_access_pos = True
        self.owner.pos_pin_hash = make_password('123456')
        self.owner.save(update_fields=('can_access_pos', 'pos_pin_hash', 'updated_at'))
        credential = 'pos5-device-credential'
        token = 'pos5-operator-session'
        device = POSDevice.objects.create(
            branch=self.branch, name='POS5 Device', status=POSDevice.Status.ACTIVE,
            app_version='1.0.0', credential_hash=make_password(credential),
            credential_fingerprint=_secret_fingerprint(credential),
        )
        POSOperatorSession.objects.create(
            device=device, operator=self.owner, token_hash=make_password(token),
            token_fingerprint=_secret_fingerprint(token),
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        client = APIClient()
        client.credentials(
            HTTP_X_POS_DEVICE_CREDENTIAL=credential,
            HTTP_X_POS_OPERATOR_SESSION=token,
        )
        return client, device

    def test_primary_table_open_is_idempotent_and_conflicting_payload_is_rejected(self):
        table = create_table(branch=self.branch, name='POS5 Table', user=self.owner)
        key = uuid4()

        first, replayed = open_table(
            branch=self.branch, table_id=table.pk, user=self.owner,
            idempotency_key=key, identifier='Ana', people_count=2,
        )
        replay, replayed_again = open_table(
            branch=self.branch, table_id=table.pk, user=self.owner,
            idempotency_key=key, identifier='Ana', people_count=2,
        )

        self.assertFalse(replayed)
        self.assertTrue(replayed_again)
        self.assertEqual(first.pk, replay.pk)
        self.assertTrue(first.is_primary)
        self.assertEqual(AttendanceCommand.objects.filter(table=table, status='open').count(), 1)
        with self.assertRaises(AttendanceConflict) as conflict:
            open_table(
                branch=self.branch, table_id=table.pk, user=self.owner,
                idempotency_key=key, identifier='Outro', people_count=2,
            )
        self.assertEqual(conflict.exception.code, 'idempotency_key_conflict')

    def test_standalone_open_accepts_null_table_and_replays_through_pos_api(self):
        client, _ = self.pos_client()
        key = str(uuid4())
        payload = {'idempotency_key': key, 'identifier': 'Balcao', 'table': None}

        created = client.post('/api/v1/pos/commands/', payload, format='json')
        replayed = client.post('/api/v1/pos/commands/', payload, format='json')

        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(replayed.status_code, 200, replayed.data)
        self.assertEqual(created.data['id'], replayed.data['id'])
        self.assertIsNone(created.data['table'])
        self.assertEqual(replayed['Idempotency-Replayed'], 'true')
        self.assertEqual(AttendanceCommand.objects.filter(table__isnull=True).count(), 1)

    def test_tables_module_requires_both_features_needed_to_open_a_table(self):
        device = SimpleNamespace(branch=self.branch)
        permissions = {'tables.view'}

        self.branch.settings.uses_commands = False
        self.branch.settings.save(update_fields=('uses_commands', 'updated_at'))
        _, without_commands = modules_for(self.owner, device, permission_codes=permissions)
        self.branch.settings.uses_commands = True
        self.branch.settings.save(update_fields=('uses_commands', 'updated_at'))
        _, enabled = modules_for(self.owner, device, permission_codes=permissions)

        self.assertFalse(without_commands['tables']['enabled'])
        self.assertTrue(enabled['tables']['enabled'])

    def test_table_aggregate_remains_occupied_until_its_last_command_closes(self):
        table = create_table(branch=self.branch, name='POS5 Aggregate', user=self.owner)
        primary, _ = open_table(
            branch=self.branch, table_id=table.pk, user=self.owner, idempotency_key=uuid4(),
        )
        additional, _ = self.open_standalone(identifier='Guest', table_id=table.pk)
        self.add_confirmed_item(primary)
        self.add_confirmed_item(additional)

        totals = sum(
            (Decimal(command_summary(command)['total_due'])
             for command in AttendanceCommand.objects.filter(table=table, status='open')),
            Decimal('0.00'),
        )
        self.assertEqual(totals, Decimal('20.00'))
        self.close(primary)
        self.assertEqual(AttendanceCommand.objects.filter(table=table, status='open').count(), 1)
        self.close(additional)
        self.assertEqual(AttendanceCommand.objects.filter(table=table, status='open').count(), 0)

    def test_confirm_and_finalization_do_not_duplicate_stock_ticket_or_production(self):
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
        self.assertEqual(ProductionJob.objects.filter(attendance_order_item=item).count(), 1)
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

    def test_transfers_keep_history_and_enforce_branch_scope_and_pos_rbac(self):
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
        self.assertTrue(AuditLog.objects.filter(action='attendance.item.transfer').exists())

        source_table = create_table(branch=self.branch, name='POS5 Source Table', user=self.owner)
        destination_table = create_table(branch=self.branch, name='POS5 Destination Table', user=self.owner)
        source_table_command, _ = open_table(
            branch=self.branch, table_id=source_table.pk, user=self.owner, idempotency_key=uuid4(),
        )
        open_table(
            branch=self.branch, table_id=destination_table.pk, user=self.owner, idempotency_key=uuid4(),
        )
        transferred, replayed = transfer_command(
            command=source_table_command, table_id=destination_table.pk,
            user=self.owner, idempotency_key=uuid4(),
        )
        self.assertFalse(replayed)
        self.assertEqual(transferred.table_id, destination_table.pk)
        self.assertTrue(AuditLog.objects.filter(action='attendance.command.transfer').exists())

        other_branch = create_branch_with_access(
            creator=self.owner, company=self.company, name='POS5 Other', address_pending=True,
        )
        foreign = AttendanceCommand.objects.create(
            company=self.company, branch=other_branch, number='A000001', opened_by=self.owner,
            opened_by_name_snapshot=self.owner.email,
        )
        client, _ = self.pos_client()
        block = UserPermissionBlock.objects.create(
            company=self.company, branch=self.branch, user=self.owner,
            permission=FunctionalPermission.objects.get(code='commands.transfer'),
            created_by=self.owner,
        )
        denied = client.post(
            f'/api/v1/pos/commands/{source.pk}/transfer/',
            {'idempotency_key': str(uuid4()), 'table': None}, format='json',
        )
        block.delete()
        hidden = client.get(f'/api/v1/pos/commands/{foreign.pk}/')

        self.assertEqual(denied.status_code, 403, denied.data)
        self.assertEqual(hidden.status_code, 404, hidden.data)

    def test_legacy_and_attendance_table_flows_remain_mutually_exclusive(self):
        legacy_table = create_table(branch=self.branch, name='POS5 Legacy', user=self.owner)
        open_legacy_command(branch=self.branch, user=self.owner, table=legacy_table)
        with self.assertRaises(AttendanceConflict) as legacy_conflict:
            open_table(
                branch=self.branch, table_id=legacy_table.pk, user=self.owner,
                idempotency_key=uuid4(),
            )
        self.assertEqual(legacy_conflict.exception.code, 'table_in_legacy_use')

        attendance_table = create_table(branch=self.branch, name='POS5 Attendance', user=self.owner)
        command, _ = open_table(
            branch=self.branch, table_id=attendance_table.pk, user=self.owner,
            idempotency_key=uuid4(),
        )
        with self.assertRaisesMessage(Exception, 'atendimento aberto no POS'):
            open_legacy_command(branch=self.branch, user=self.owner, table=attendance_table)
        self.assertEqual(command.status, AttendanceCommandStatus.OPEN)
        self.assertEqual(Command.objects.filter(table=attendance_table, status='open').count(), 0)

    def test_grouping_preserves_table_and_command_identity_and_separation_history(self):
        first_table = create_table(branch=self.branch, name='POS5 Group 1', user=self.owner)
        second_table = create_table(branch=self.branch, name='POS5 Group 2', user=self.owner)
        first_command, _ = open_table(
            branch=self.branch, table_id=first_table.pk, user=self.owner, idempotency_key=uuid4(),
        )
        second_command, _ = open_table(
            branch=self.branch, table_id=second_table.pk, user=self.owner, idempotency_key=uuid4(),
        )
        group, replayed = group_tables(
            branch=self.branch, table_ids=[first_table.pk, second_table.pk], user=self.owner,
            idempotency_key=uuid4(),
        )
        self.assertFalse(replayed)
        self.assertEqual(
            set(group.memberships.filter(left_at__isnull=True).values_list('table_id', flat=True)),
            {first_table.pk, second_table.pk},
        )
        self.assertEqual(AttendanceCommand.objects.get(pk=first_command.pk).table_id, first_table.pk)
        self.assertEqual(AttendanceCommand.objects.get(pk=second_command.pk).table_id, second_table.pk)
        self.assertTrue(AuditLog.objects.filter(action='attendance.table_group.group', object_id=str(group.pk)).exists())
        client, _ = self.pos_client()
        tables = client.get('/api/v1/pos/tables/')
        self.assertEqual(tables.status_code, 200, tables.data)
        first_row = next(row for row in tables.data['tables'] if row['id'] == first_table.pk)
        self.assertEqual(set(first_row['group']['table_ids']), {first_table.pk, second_table.pk})

        separate_table_from_group(
            branch=self.branch, table_id=first_table.pk, user=self.owner, idempotency_key=uuid4(),
        )
        self.assertEqual(AttendanceTableGroupMembership.objects.filter(group=group).count(), 2)
        self.assertFalse(group.memberships.filter(left_at__isnull=True).exists())
        self.assertEqual(AttendanceCommand.objects.get(pk=first_command.pk).table_id, first_table.pk)
        self.assertEqual(AttendanceCommand.objects.get(pk=second_command.pk).table_id, second_table.pk)
        self.assertTrue(AuditLog.objects.filter(action='attendance.table_group.separate', object_id=str(group.pk)).exists())

    def test_bill_request_is_audited_and_clears_without_freeing_open_table(self):
        table = create_table(branch=self.branch, name='POS5 Bill', user=self.owner)
        command, _ = open_table(
            branch=self.branch, table_id=table.pk, user=self.owner, idempotency_key=uuid4(),
        )
        requested, replayed = set_bill_requested(
            command=command, user=self.owner, idempotency_key=uuid4(), requested=True,
        )
        self.assertFalse(replayed)
        self.assertIsNotNone(requested.bill_requested_at)
        self.assertEqual(AttendanceCommand.objects.filter(table=table, status='open').count(), 1)
        client, _ = self.pos_client()
        tables = client.get('/api/v1/pos/tables/')
        self.assertEqual(tables.status_code, 200, tables.data)
        self.assertTrue(next(row for row in tables.data['tables'] if row['id'] == table.pk)['bill_requested'])
        cleared, _ = set_bill_requested(
            command=requested, user=self.owner, idempotency_key=uuid4(), requested=False,
        )
        self.assertIsNone(cleared.bill_requested_at)
        self.assertTrue(AuditLog.objects.filter(action='attendance.bill.request').exists())
        self.assertTrue(AuditLog.objects.filter(action='attendance.bill.clear').exists())

        set_bill_requested(command=cleared, user=self.owner, idempotency_key=uuid4(), requested=True)
        self.add_confirmed_item(cleared)
        closed = self.close(cleared)
        self.assertIsNone(closed.bill_requested_at)

    def test_item_transfer_with_partial_payment_is_blocked_with_explicit_rule(self):
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
        self.assertIn('rateio', conflict.exception.message)

    def test_whole_command_transfer_preserves_partial_payment_and_history(self):
        source_table = create_table(branch=self.branch, name='POS5 Paid Source', user=self.owner)
        destination_table = create_table(branch=self.branch, name='POS5 Paid Target', user=self.owner)
        command, _ = open_table(
            branch=self.branch, table_id=source_table.pk, user=self.owner, idempotency_key=uuid4(),
        )
        open_table(
            branch=self.branch, table_id=destination_table.pk, user=self.owner, idempotency_key=uuid4(),
        )
        self.add_confirmed_item(command)
        payment = record_payment(
            command=command, user=self.owner, payment_method_id=self.cash_method.pk,
            amount='4.00', received_amount='4.00', cash_session_id=self.cash_session.pk,
            idempotency_key=uuid4(),
        )
        transferred, _ = transfer_command(
            command=command, table_id=destination_table.pk, user=self.owner, idempotency_key=uuid4(),
        )
        self.assertEqual(transferred.table_id, destination_table.pk)
        self.assertEqual(transferred.payments.get(pk=payment.pk).amount, Decimal('4.00'))
        self.assertEqual(command_summary(transferred)['remaining_balance'], '6.00')
        self.assertTrue(AuditLog.objects.filter(action='attendance.command.transfer', object_id=str(command.pk)).exists())
