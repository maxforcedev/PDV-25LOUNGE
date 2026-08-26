"""BLOCO 6 — Tests for Sales, Cash, Payments, Service Fee, and Seller/Commission.

Covers mandatory test areas:
  1  RBAC_MULTI_TENANT (Sales, Cash)
  4  SERVICE_FEE
  8  COMMAND_FINANCIAL_ENGINE (PDV side)
  13 SALES_CASH_PAYMENTS
  14 SELLER_COMMISSION
"""
import uuid
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.cash.models import CashRegister, CashSession, CashSessionStatus
from apps.cash.services import (
    open_session, record_manual_entry, record_withdrawal, close_session,
)
from apps.companies.models import (
    AccessProfile, BranchSettings, FunctionalPermission, Status,
    UserBranchAccess, UserCompanyAccess,
)
from apps.companies.services import (
    create_company_with_matrix, ensure_permission_catalog,
)
from apps.inventory.models import Stock, MovementType
from apps.products.models import (
    Category, Product, SalesChannel, Unit, InventoryBehavior,
)
from apps.sales.models import OperationType, Sale, SaleStatus, Payment
from apps.sales.services import (
    calculate_preview, finalize_sale, cancel_sale,
    ensure_default_payment_methods,
)

PASSWORD = 'Block6-sales-password-123!'


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


class SalesFixture:
    def setUp(self):
        ensure_permission_catalog()
        self.owner = create_user('owner@sales6.com')
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='Sales6', legal_name='Sales6 Legal',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        settings = self.branch.settings
        settings.uses_counter = True
        settings.uses_cash_register = True
        settings.uses_consumption = True
        settings.save()
        self.category = Category.objects.create(company=self.company, name='Food')
        self.product = Product.objects.create(
            company=self.company, category=self.category, name='Burger',
            internal_code='BURG01', unit=Unit.UNIT, cost=Decimal('10.00'),
            sale_price=Decimal('20.00'), inventory_behavior=InventoryBehavior.DIRECT,
        )
        set_stock(self.branch, self.product, '100', '10.00')
        self.cash_register = CashRegister.objects.create(branch=self.branch, name='Main')
        self.payment_methods = ensure_default_payment_methods(self.company)
        self.cash_method = next(m for m in self.payment_methods if m.code == 'cash')
        self.pix_method = next(m for m in self.payment_methods if m.code == 'pix')

    def open_session(self, user=None):
        return open_session(
            cash_register=self.cash_register,
            opening_amount=Decimal('100.00'),
            user=user or self.owner,
            current_branch=self.branch,
        )

    def finalize_sale_via_service(self, user=None, session=None, quantity=Decimal('1'),
                                  discount=Decimal('0.00'), payments=None,
                                  idempotency_key=None):
        if session is None:
            session = self.open_session(user or self.owner)
        if payments is None:
            payments = [{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '1000.00'}]
        return finalize_sale(
            branch=self.branch,
            user=user or self.owner,
            operation_type=OperationType.SALE,
            cash_session=session.pk,
            items=[{'product': self.product.pk, 'quantity': str(quantity)}],
            discount=discount,
            payments=payments,
            seller_user=(user or self.owner).pk,
            idempotency_key=idempotency_key or uuid.uuid4(),
            channel=SalesChannel.COUNTER,
        )


# ---------------------------------------------------------------------------
# Area 4: SERVICE_FEE
# ---------------------------------------------------------------------------

class ServiceFeeTests(SalesFixture, TestCase):
    def test_charges_false_rate_10_fee_zero(self):
        settings = self.branch.settings
        settings.charges_service_fee = False
        settings.service_fee_rate = Decimal('10')
        settings.save()
        preview = calculate_preview(
            company=self.company, operation_type=OperationType.SALE,
            raw_items=[{'product': self.product.pk, 'quantity': '1'}],
            discount='0', charged_amount=None, beneficiary_user=None,
            branch=self.branch, channel=SalesChannel.COUNTER,
        )
        self.assertEqual(preview['service_fee_amount'], Decimal('0.00'))

    def test_charges_true_rate_10_fee_applied(self):
        settings = self.branch.settings
        settings.charges_service_fee = True
        settings.service_fee_rate = Decimal('10')
        settings.save()
        preview = calculate_preview(
            company=self.company, operation_type=OperationType.SALE,
            raw_items=[{'product': self.product.pk, 'quantity': '1'}],
            discount='0', charged_amount=None, beneficiary_user=None,
            branch=self.branch, channel=SalesChannel.COUNTER,
        )
        self.assertEqual(preview['service_fee_rate'], Decimal('10'))
        self.assertEqual(preview['service_fee_amount'], Decimal('2.00'))

    def test_disabling_does_not_erase_rate(self):
        settings = self.branch.settings
        settings.charges_service_fee = True
        settings.service_fee_rate = Decimal('10')
        settings.save()
        settings.charges_service_fee = False
        settings.save()
        settings.refresh_from_db()
        self.assertEqual(settings.service_fee_rate, Decimal('10'))


# ---------------------------------------------------------------------------
# Area 13: SALES_CASH_PAYMENTS
# ---------------------------------------------------------------------------

class SalesFinalizeIdempotencyTests(SalesFixture, TestCase):
    def test_finalize_is_idempotent(self):
        session = self.open_session()
        key = uuid.uuid4()
        sale1 = self.finalize_sale_via_service(session=session, idempotency_key=key)
        sale2 = self.finalize_sale_via_service(session=session, idempotency_key=key)
        self.assertEqual(sale1.pk, sale2.pk)
        self.assertTrue(getattr(sale2, '_idempotency_replayed', False))

    def test_different_key_same_data_creates_new_sale(self):
        session = self.open_session()
        sale1 = self.finalize_sale_via_service(session=session)
        sale2 = self.finalize_sale_via_service(session=session)
        self.assertNotEqual(sale1.pk, sale2.pk)

    def test_same_key_different_data_raises(self):
        session = self.open_session()
        key = uuid.uuid4()
        self.finalize_sale_via_service(session=session, idempotency_key=key, quantity=Decimal('1'))
        with self.assertRaises(Exception):
            self.finalize_sale_via_service(session=session, idempotency_key=key, quantity=Decimal('2'))

    def test_cancel_sale(self):
        sale = self.finalize_sale_via_service()
        cancel_sale(sale=sale, branch=self.branch, user=self.owner, reason='Test')
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CANCELLED)

    def test_cancel_already_cancelled_raises(self):
        sale = self.finalize_sale_via_service()
        cancel_sale(sale=sale, branch=self.branch, user=self.owner, reason='First')
        with self.assertRaises(Exception):
            cancel_sale(sale=sale, branch=self.branch, user=self.owner, reason='Second')


class PaymentTests(SalesFixture, TestCase):
    def test_single_cash_payment(self):
        sale = self.finalize_sale_via_service(
            payments=[{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '50.00'}],
        )
        self.assertEqual(sale.total, Decimal('20.00'))
        payment = Payment.objects.get(sale=sale)
        self.assertEqual(payment.amount, Decimal('20.00'))
        self.assertEqual(payment.received_amount, Decimal('50.00'))
        self.assertEqual(payment.change_amount, Decimal('30.00'))

    def test_multiple_payment_methods(self):
        sale = self.finalize_sale_via_service(
            quantity=Decimal('2'),
            payments=[
                {'payment_method': self.pix_method.pk, 'amount': '20.00'},
                {'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '100.00'},
            ],
        )
        self.assertEqual(sale.total, Decimal('40.00'))
        payments = Payment.objects.filter(sale=sale).order_by('payment_method__code')
        self.assertEqual(payments.count(), 2)

    def test_payment_total_must_match_sale_total(self):
        with self.assertRaises(Exception):
            self.finalize_sale_via_service(
                payments=[{'payment_method': self.cash_method.pk, 'amount': '10.00', 'received_amount': '10.00'}],
            )

    def test_non_cash_rejects_received_amount(self):
        with self.assertRaises(Exception):
            self.finalize_sale_via_service(
                payments=[{'payment_method': self.pix_method.pk, 'amount': '20.00', 'received_amount': '30.00'}],
            )


class CashSessionTests(SalesFixture, TestCase):
    def test_open_session(self):
        session = self.open_session()
        self.assertEqual(session.status, CashSessionStatus.OPEN)
        self.assertEqual(session.opening_amount, Decimal('100.00'))

    def test_manual_entry(self):
        session = self.open_session()
        record_manual_entry(
            cash_session=session, amount=Decimal('50.00'),
            user=self.owner, reason='Test entry',
            current_branch=self.branch, idempotency_key=uuid.uuid4(),
        )

    def test_withdrawal(self):
        session = self.open_session()
        record_withdrawal(
            cash_session=session, amount=Decimal('30.00'),
            user=self.owner, reason='Test withdrawal',
            current_branch=self.branch, idempotency_key=uuid.uuid4(),
            category='supplier', result_effect='operating_expense',
        )

    def test_close_session(self):
        session = self.open_session()
        record_manual_entry(
            cash_session=session, amount=Decimal('50.00'),
            user=self.owner, reason='Entry',
            current_branch=self.branch, idempotency_key=uuid.uuid4(),
        )
        close_session(
            cash_session=session,
            closing_amount_informed=Decimal('150.00'),
            user=self.owner, current_branch=self.branch,
        )
        session.refresh_from_db()
        self.assertEqual(session.status, CashSessionStatus.CLOSED)

    def test_cash_session_idempotency(self):
        key = uuid.uuid4()
        session = self.open_session()
        record_manual_entry(
            cash_session=session, amount=Decimal('50.00'),
            user=self.owner, reason='Entry',
            current_branch=self.branch, idempotency_key=key,
        )
        record_manual_entry(
            cash_session=session, amount=Decimal('50.00'),
            user=self.owner, reason='Entry',
            current_branch=self.branch, idempotency_key=key,
        )
        from apps.cash.models import CashMovement
        self.assertEqual(
            CashMovement.objects.filter(cash_session=session, operation_reference=str(key)).count(), 1
        )


# ---------------------------------------------------------------------------
# Area 14: SELLER_COMMISSION
# ---------------------------------------------------------------------------

class SellerCommissionTests(SalesFixture, TestCase):
    def test_seller_valid_resolved(self):
        sale = self.finalize_sale_via_service()
        self.assertEqual(sale.seller_user_id, self.owner.pk)

    def test_seller_from_other_branch_rejected(self):
        other_owner = create_user('other@sales6.com')
        other_company = create_company_with_matrix(
            creator=other_owner, trade_name='Other', legal_name='Other Legal',
        )
        other_branch = other_company.branches.get(is_matrix=True)
        other_branch.settings.uses_counter = True
        other_branch.settings.uses_cash_register = True
        other_branch.settings.save()
        session = self.open_session()
        with self.assertRaises(Exception):
            finalize_sale(
                branch=self.branch, user=self.owner,
                operation_type=OperationType.SALE,
                cash_session=session.pk,
                items=[{'product': self.product.pk, 'quantity': '1'}],
                payments=[{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '1000.00'}],
                idempotency_key=uuid.uuid4(),
                channel=SalesChannel.COUNTER,
                seller_user=other_owner.pk,
            )

    def test_commission_calculated(self):
        settings = self.branch.settings
        settings.commission_rate = Decimal('5')
        settings.save()
        sale = self.finalize_sale_via_service()
        self.assertEqual(sale.commission_rate, Decimal('5'))
        self.assertEqual(sale.commission_amount, Decimal('1.00'))

    def test_cancel_sale_reverses_stock_and_sets_cancelled(self):
        sale = self.finalize_sale_via_service()
        stock_before = Stock.objects.get(product=self.product, branch=self.branch)
        self.assertEqual(stock_before.current_quantity, Decimal('99'))
        cancel_sale(sale=sale, branch=self.branch, user=self.owner, reason='Test')
        stock_after = Stock.objects.get(product=self.product, branch=self.branch)
        self.assertEqual(stock_after.current_quantity, Decimal('100'))
        sale.refresh_from_db()
        self.assertEqual(sale.status, SaleStatus.CANCELLED)


# ---------------------------------------------------------------------------
# Area 1: RBAC_MULTI_TENANT — Sales API
# ---------------------------------------------------------------------------

class SalesCrossTenantTests(SalesFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_b = create_user('owner_b@sales6.com')
        self.company_b = create_company_with_matrix(
            creator=self.owner_b, trade_name='Sales6B', legal_name='Sales6B Legal',
        )
        self.branch_b = self.company_b.branches.get(is_matrix=True)
        self.branch_b.settings.uses_counter = True
        self.branch_b.settings.uses_cash_register = True
        self.branch_b.settings.save()
        self.cat_b = Category.objects.create(company=self.company_b, name='CatB')
        self.product_b = Product.objects.create(
            company=self.company_b, category=self.cat_b, name='ProdB',
            internal_code='PB01', unit=Unit.UNIT, cost=Decimal('1.00'),
            sale_price=Decimal('3.00'), inventory_behavior=InventoryBehavior.DIRECT,
        )
        set_stock(self.branch_b, self.product_b, '50', '1.00')
        ensure_default_payment_methods(self.company_b)
        self.cash_register_b = CashRegister.objects.create(branch=self.branch_b, name='CRB')
        self.cash_method_b = self.company_b.payment_methods.get(code='cash')

    def test_user_a_cannot_list_sales_from_company_b(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)
        resp = client.get(f'/api/v1/sales/?company={self.company_b.pk}')
        self.assertEqual(resp.data.get('count', 0), 0)

    def test_user_a_cannot_finalize_sale_with_product_from_company_b(self):
        session = open_session(
            cash_register=self.cash_register, opening_amount=Decimal('100.00'),
            user=self.owner, current_branch=self.branch,
        )
        with self.assertRaises(Exception):
            finalize_sale(
                branch=self.branch, user=self.owner,
                operation_type=OperationType.SALE,
                cash_session=session.pk,
                items=[{'product': self.product_b.pk, 'quantity': '1'}],
                payments=[{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '1000.00'}],
                idempotency_key=uuid.uuid4(),
                channel=SalesChannel.COUNTER,
            )

    def test_cash_session_from_other_branch_rejected(self):
        session_b = open_session(
            cash_register=self.cash_register_b, opening_amount=Decimal('100.00'),
            user=self.owner_b, current_branch=self.branch_b,
        )
        with self.assertRaises(Exception):
            finalize_sale(
                branch=self.branch, user=self.owner,
                operation_type=OperationType.SALE,
                cash_session=session_b.pk,
                items=[{'product': self.product.pk, 'quantity': '1'}],
                payments=[{'payment_method': self.cash_method.pk, 'amount': 'auto', 'received_amount': '1000.00'}],
                idempotency_key=uuid.uuid4(),
                channel=SalesChannel.COUNTER,
            )
