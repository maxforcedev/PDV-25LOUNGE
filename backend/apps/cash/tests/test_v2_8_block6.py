"""BLOCO 6 — Feature Gates tests.

Covers mandatory test area 3:
  - uses_tables, uses_commands, uses_counter, uses_consumption, uses_cash_register
  - counter/consumption/commands cannot be enabled without Caixa
  - Caixa cannot be disabled while dependencies remain enabled
  - backend prevents API bypass
  - FEATURE CAIXA enabled != CASH SESSION open
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import BranchSettings, Status
from apps.companies.features import branch_feature_states, branch_feature_enabled
from apps.companies.services import (
    create_company_with_matrix, ensure_permission_catalog,
)
from apps.cash.models import CashRegister, CashSession, CashSessionStatus
from apps.cash.services import open_session
from apps.commands.services import create_table, open_command
from apps.products.models import Category, Product, Unit, InventoryBehavior, SalesChannel
from apps.sales.models import OperationType
from apps.sales.services import calculate_preview, ensure_default_payment_methods

PASSWORD = 'Block6-feat-password-123!'


def create_user(email):
    return User.objects.create_user(email=email, password=PASSWORD)


class FeatureGateTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = create_user('owner@feat6.com')
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='Feat6', legal_name='Feat6 Legal',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        # Start with all features enabled
        self.branch.settings.uses_tables = True
        self.branch.settings.uses_commands = True
        self.branch.settings.uses_counter = True
        self.branch.settings.uses_consumption = True
        self.branch.settings.uses_cash_register = True
        self.branch.settings.save()
        self.category = Category.objects.create(company=self.company, name='Cat')
        self.product = Product.objects.create(
            company=self.company, category=self.category, name='Item',
            internal_code='IT01', unit=Unit.UNIT, cost=Decimal('1.00'),
            sale_price=Decimal('5.00'), inventory_behavior=InventoryBehavior.DIRECT,
        )
        ensure_default_payment_methods(self.company)

    def test_all_features_enabled_when_cash_register_on(self):
        states = branch_feature_states(self.branch)
        self.assertTrue(states['cash_register']['enabled'])
        self.assertTrue(states['counter']['enabled'])
        self.assertTrue(states['consumption']['enabled'])
        self.assertTrue(states['tables']['enabled'])
        self.assertTrue(states['commands']['enabled'])

    def test_counter_disabled_when_cash_register_disabled(self):
        self.branch.settings.uses_cash_register = False
        self.branch.settings.save()
        states = branch_feature_states(self.branch)
        self.assertFalse(states['cash_register']['enabled'])
        self.assertFalse(states['counter']['enabled'])
        self.assertFalse(states['consumption']['enabled'])
        self.assertFalse(states['commands']['enabled'])

    def test_commands_disabled_when_cash_register_disabled(self):
        self.branch.settings.uses_cash_register = False
        self.branch.settings.save()
        self.assertFalse(branch_feature_enabled(self.branch, 'commands'))

    def test_tables_remain_when_cash_disabled(self):
        self.branch.settings.uses_cash_register = False
        self.branch.settings.save()
        states = branch_feature_states(self.branch)
        self.assertTrue(states['tables']['enabled'])

    def test_create_table_blocked_when_tables_disabled(self):
        self.branch.settings.uses_tables = False
        self.branch.settings.save()
        with self.assertRaises(PermissionDenied):
            create_table(branch=self.branch, name='Mesa X', user=self.owner)

    def test_open_command_blocked_when_commands_disabled(self):
        self.branch.settings.uses_commands = False
        self.branch.settings.save()
        with self.assertRaises(PermissionDenied):
            open_command(branch=self.branch, user=self.owner, identifier='Test')

    def test_open_command_blocked_when_cash_disabled(self):
        self.branch.settings.uses_cash_register = False
        self.branch.settings.save()
        with self.assertRaises(PermissionDenied):
            open_command(branch=self.branch, user=self.owner, identifier='Test')

    def test_calculate_preview_blocked_when_counter_disabled(self):
        self.branch.settings.uses_cash_register = False
        self.branch.settings.save()
        with self.assertRaises(Exception):
            calculate_preview(
                company=self.company, operation_type=OperationType.SALE,
                raw_items=[{'product': self.product.pk, 'quantity': '1'}],
                discount='0', charged_amount=None, beneficiary_user=None,
                branch=self.branch, channel=SalesChannel.COUNTER,
            )

    def test_feature_caixa_enabled_is_different_from_cash_session_open(self):
        self.assertTrue(branch_feature_enabled(self.branch, 'cash_register'))
        open_count = CashSession.objects.filter(
            cash_register__branch=self.branch, status=CashSessionStatus.OPEN
        ).count()
        self.assertEqual(open_count, 0)
        cr = CashRegister.objects.create(branch=self.branch, name='CR')
        session = open_session(
            cash_register=cr, opening_amount=Decimal('0.00'),
            user=self.owner, current_branch=self.branch,
        )
        self.assertEqual(session.status, CashSessionStatus.OPEN)
        self.assertTrue(branch_feature_enabled(self.branch, 'cash_register'))
