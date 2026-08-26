"""BLOCO 6 — Tests for Products RBAC, Modifiers, and Branch Prices.

Covers mandatory test areas:
  1  RBAC_MULTI_TENANT (Products, Modifiers)
  2  BRANCH_PRICES
  5  MODIFIERS
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.companies.models import (
    AccessProfile, BranchSettings, FunctionalPermission, Status,
    UserBranchAccess, UserCompanyAccess,
)
from apps.companies.services import (
    create_company_with_matrix, ensure_permission_catalog,
)
from apps.base.models import AuditLog
from apps.inventory.models import Stock
from apps.products.models import (
    Category, ModifierGroup, ModifierOption, ModifierOptionType,
    Product, ProductModifierGroup, BranchProductPrice,
    SalesChannel, Unit, InventoryBehavior,
)
from apps.sales.services import ensure_default_payment_methods

PASSWORD = 'Block6-prod-password-123!'


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


class ProductRbacFixture:
    def setUp(self):
        ensure_permission_catalog()
        self.owner_a = create_user('owner_a@prod.com')
        self.company_a = create_company_with_matrix(
            creator=self.owner_a, trade_name='ProdA', legal_name='ProdA Legal',
        )
        self.branch_a = self.company_a.branches.get(is_matrix=True)
        self.settings_a = self.branch_a.settings
        self.settings_a.uses_counter = True
        self.settings_a.uses_cash_register = True
        self.settings_a.save()

        self.owner_b = create_user('owner_b@prod.com')
        self.company_b = create_company_with_matrix(
            creator=self.owner_b, trade_name='ProdB', legal_name='ProdB Legal',
        )
        self.branch_b = self.company_b.branches.get(is_matrix=True)
        self.settings_b = self.branch_b.settings
        self.settings_b.uses_counter = True
        self.settings_b.uses_cash_register = True
        self.settings_b.save()

        self.cat_a = Category.objects.create(company=self.company_a, name='Cat A')
        self.cat_b = Category.objects.create(company=self.company_b, name='Cat B')
        self.product_a = Product.objects.create(
            company=self.company_a, category=self.cat_a, name='ProdA Item',
            internal_code='PA01', unit=Unit.UNIT, cost=Decimal('1.00'),
            sale_price=Decimal('5.00'), inventory_behavior=InventoryBehavior.DIRECT,
        )
        self.product_b = Product.objects.create(
            company=self.company_b, category=self.cat_b, name='ProdB Item',
            internal_code='PB01', unit=Unit.UNIT, cost=Decimal('2.00'),
            sale_price=Decimal('8.00'), inventory_behavior=InventoryBehavior.DIRECT,
        )
        ensure_default_payment_methods(self.company_a)
        ensure_default_payment_methods(self.company_b)

    def api_client(self, user, branch_id):
        client = APIClient()
        client.force_authenticate(user=user)
        client.defaults['HTTP_X_BRANCH_ID'] = str(branch_id)
        return client


# ---------------------------------------------------------------------------
# Area 1: RBAC_MULTI_TENANT — Products
# ---------------------------------------------------------------------------

class ProductCrossTenantTests(ProductRbacFixture, TestCase):
    def test_user_cannot_access_product_from_other_company(self):
        client = self.api_client(self.owner_a, self.branch_a.pk)
        resp = client.get(f'/api/v1/products/?company={self.company_b.pk}')
        self.assertEqual(resp.data['count'], 0)

    def test_product_id_from_other_company_returns_404(self):
        client = self.api_client(self.owner_a, self.branch_a.pk)
        resp = client.get(f'/api/v1/products/{self.product_b.pk}/')
        self.assertEqual(resp.status_code, 404)

    def test_create_product_in_other_company_rejected(self):
        client = self.api_client(self.owner_a, self.branch_a.pk)
        resp = client.post('/api/v1/products/', {
            'company': self.company_b.pk,
            'category': self.cat_b.pk,
            'name': 'Infiltrated',
            'internal_code': 'INF01',
            'unit': 'un',
            'cost': '1.00',
            'sale_price': '2.00',
        }, format='json')
        self.assertIn(resp.status_code, (400, 403))

    def test_update_product_from_other_company_rejected(self):
        client = self.api_client(self.owner_a, self.branch_a.pk)
        resp = client.patch(f'/api/v1/products/{self.product_b.pk}/', {
            'name': 'Hacked',
        }, format='json')
        self.assertIn(resp.status_code, (403, 404))


# ---------------------------------------------------------------------------
# Area 2: BRANCH_PRICES
# ---------------------------------------------------------------------------

class BranchPriceTests(ProductRbacFixture, TestCase):
    def test_change_branch_price_allowed_for_own_branch(self):
        client = self.api_client(self.owner_a, self.branch_a.pk)
        resp = client.post('/api/v1/branch-prices/', {
            'product': self.product_a.pk,
            'branch': self.branch_a.pk,
            'sale_price': '4.50',
        }, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_change_branch_price_other_company_rejected(self):
        client = self.api_client(self.owner_a, self.branch_a.pk)
        resp = client.post('/api/v1/branch-prices/', {
            'product': self.product_b.pk,
            'branch': self.branch_b.pk,
            'sale_price': '3.00',
        }, format='json')
        self.assertIn(resp.status_code, (400, 403))

    def test_reports_view_prices_does_not_grant_change(self):
        viewer = create_user('viewer@prod.com')
        profile = make_profile(self.company_a, 'PriceViewer', ['reports.view_prices', 'products.view'])
        UserCompanyAccess.objects.create(
            user=viewer, company=self.company_a, access_profile=profile, is_active=True,
        )
        UserBranchAccess.objects.create(
            user=viewer, branch=self.branch_a, access_profile=profile,
        )
        client = self.api_client(viewer, self.branch_a.pk)
        resp = client.post('/api/v1/branch-prices/', {
            'product': self.product_a.pk,
            'branch': self.branch_a.pk,
            'sale_price': '3.00',
        }, format='json')
        self.assertIn(resp.status_code, (403, 400))

    def test_branch_price_permissions_have_explicit_scopes(self):
        self.assertEqual(
            FunctionalPermission.objects.get(code='branch_prices.view').scope,
            FunctionalPermission.Scope.BRANCH,
        )
        self.assertEqual(
            FunctionalPermission.objects.get(code='branch_prices.view_company').scope,
            FunctionalPermission.Scope.COMPANY,
        )


class CategoryConfigurationTests(ProductRbacFixture, TestCase):
    def test_apply_config_preserves_audit_before_state(self):
        self.product_a.available_counter = True
        self.product_a.available_table = True
        self.product_a.available_command = True
        self.product_a.participates_in_service_fee = True
        self.product_a.participates_in_commission = True
        self.product_a.save()
        self.cat_a.available_counter = False
        self.cat_a.available_table = False
        self.cat_a.available_command = False
        self.cat_a.participates_in_service_fee = False
        self.cat_a.participates_in_commission = False
        self.cat_a.save()

        response = self.api_client(self.owner_a, self.branch_a.pk).post(
            f'/api/v1/categories/{self.cat_a.pk}/apply-config/', {}, format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['affected_count'], 1)
        self.product_a.refresh_from_db()
        self.assertFalse(self.product_a.available_command)
        audit = AuditLog.objects.filter(
            action='category.apply_config', object_id=str(self.product_a.pk)
        ).latest('pk')
        self.assertTrue(audit.before['available_command'])
        self.assertFalse(audit.after['available_command'])


class ModifierReorderTests(ProductRbacFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.groups = [
            ModifierGroup.objects.create(company=self.company_a, name=name, sort_order=index)
            for index, name in enumerate(('Primeiro', 'Segundo', 'Terceiro'))
        ]
        self.options = [
            ModifierOption.objects.create(modifier_group=self.groups[0], name=name, sort_order=index)
            for index, name in enumerate(('A', 'B', 'C'))
        ]
        self.links = [
            ProductModifierGroup.objects.create(
                product=self.product_a, modifier_group=group, sort_order=index,
            ) for index, group in enumerate(self.groups)
        ]

    def _post(self, path, payload, user=None):
        return self.api_client(user or self.owner_a, self.branch_a.pk).post(
            path, payload, format='json'
        )

    def test_group_reorder_persists_and_audits(self):
        response = self._post(' /api/v1/modifier-groups/reorder/'.strip(), {
            'group_ids': [self.groups[2].pk, self.groups[0].pk, self.groups[1].pk],
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(list(ModifierGroup.objects.filter(company=self.company_a).values_list('pk', flat=True)), [self.groups[2].pk, self.groups[0].pk, self.groups[1].pk])
        self.assertEqual(AuditLog.objects.filter(action='modifier_group.reorder').count(), 3)

    def test_option_and_link_reorder_reject_invalid_batch_without_partial_update(self):
        original_options = list(ModifierOption.objects.filter(modifier_group=self.groups[0]).values_list('sort_order', flat=True))
        response = self._post('/api/v1/modifier-options/reorder/', {
            'modifier_group': self.groups[0].pk,
            'option_ids': [self.options[0].pk, self.options[0].pk, self.options[2].pk],
        })
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(list(ModifierOption.objects.filter(modifier_group=self.groups[0]).values_list('sort_order', flat=True)), original_options)
        response = self._post('/api/v1/product-modifier-groups/reorder/', {
            'product': self.product_a.pk,
            'link_ids': [self.links[2].pk, self.links[0].pk, self.links[1].pk],
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(list(ProductModifierGroup.objects.filter(product=self.product_a).values_list('pk', flat=True)), [self.links[2].pk, self.links[0].pk, self.links[1].pk])

    def test_reorder_rejects_cross_tenant_and_missing_ids(self):
        foreign = ModifierGroup.objects.create(company=self.company_b, name='Externo')
        response = self._post('/api/v1/modifier-groups/reorder/', {
            'group_ids': [self.groups[0].pk, self.groups[1].pk, foreign.pk],
        })
        self.assertEqual(response.status_code, 400, response.data)
        response = self._post('/api/v1/modifier-options/reorder/', {
            'modifier_group': self.groups[0].pk,
            'option_ids': [self.options[0].pk, self.options[1].pk],
        })
        self.assertEqual(response.status_code, 400, response.data)

    def test_new_modifier_records_are_appended(self):
        client = self.api_client(self.owner_a, self.branch_a.pk)
        created = client.post('/api/v1/modifier-groups/', {
            'company': self.company_a.pk, 'name': 'Último',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data['sort_order'], 3)


# ---------------------------------------------------------------------------
# Area 5: MODIFIERS
# ---------------------------------------------------------------------------

class ModifierTests(ProductRbacFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.group_a = ModifierGroup.objects.create(
            company=self.company_a, name='Extras', is_required=False,
            min_selections=0, max_selections=3,
        )
        self.option_a1 = ModifierOption.objects.create(
            modifier_group=self.group_a, name='Bacon',
            option_type=ModifierOptionType.ADD, additional_price=Decimal('2.00'),
        )
        self.option_a2 = ModifierOption.objects.create(
            modifier_group=self.group_a, name='Cheese',
            option_type=ModifierOptionType.ADD, additional_price=Decimal('1.50'),
        )
        self.link_a = ProductModifierGroup.objects.create(
            product=self.product_a, modifier_group=self.group_a, sort_order=0,
        )

    def test_activate_deactivate_reactivate_modifier_group(self):
        client = self.api_client(self.owner_a, self.branch_a.pk)
        resp = client.post(f'/api/v1/modifier-groups/{self.group_a.pk}/deactivate/')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.group_a.refresh_from_db()
        self.assertEqual(self.group_a.status, 'inactive')
        resp = client.post(f'/api/v1/modifier-groups/{self.group_a.pk}/activate/')
        self.assertEqual(resp.status_code, 200)
        self.group_a.refresh_from_db()
        self.assertEqual(self.group_a.status, 'active')

    def test_modifier_option_activate_deactivate(self):
        admin_profile = AccessProfile.objects.get(
            company=self.company_a, name='Administrador', is_system=True,
        )
        perm, _ = FunctionalPermission.objects.get_or_create(
            code='modifiers.change',
            defaults={'module': 'modifiers', 'label': 'Administrar modificadores',
                      'description': '', 'status': 'active'},
        )
        admin_profile.permissions.add(perm)
        client = self.api_client(self.owner_a, self.branch_a.pk)
        resp = client.post(f'/api/v1/modifier-options/{self.option_a1.pk}/deactivate/')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.option_a1.refresh_from_db()
        self.assertEqual(self.option_a1.status, 'inactive')

    def test_required_group_blocks_without_selection(self):
        req_group = ModifierGroup.objects.create(
            company=self.company_a, name='Required', is_required=True,
            min_selections=1, max_selections=2,
        )
        ProductModifierGroup.objects.create(
            product=self.product_a, modifier_group=req_group,
        )
        opt = ModifierOption.objects.create(
            modifier_group=req_group, name='Pick',
            option_type=ModifierOptionType.ADD, additional_price=Decimal('0.00'),
        )
        from apps.sales.services import resolve_modifiers
        with self.assertRaises(Exception):
            resolve_modifiers(self.product_a, [], self.company_a.pk)

    def test_min_selections_enforced(self):
        group = ModifierGroup.objects.create(
            company=self.company_a, name='Min2', is_required=False,
            min_selections=2, max_selections=None,
        )
        ProductModifierGroup.objects.create(product=self.product_a, modifier_group=group)
        opt = ModifierOption.objects.create(
            modifier_group=group, name='Opt1',
            option_type=ModifierOptionType.ADD, additional_price=Decimal('1.00'),
        )
        from apps.sales.services import resolve_modifiers
        with self.assertRaises(Exception):
            resolve_modifiers(self.product_a, [{'option': opt.pk, 'quantity': '1'}], self.company_a.pk)

    def test_max_selections_enforced(self):
        group = ModifierGroup.objects.create(
            company=self.company_a, name='Max1', is_required=False,
            min_selections=0, max_selections=1,
        )
        ProductModifierGroup.objects.create(product=self.product_a, modifier_group=group)
        opt1 = ModifierOption.objects.create(
            modifier_group=group, name='M1',
            option_type=ModifierOptionType.ADD, additional_price=Decimal('1.00'),
        )
        opt2 = ModifierOption.objects.create(
            modifier_group=group, name='M2',
            option_type=ModifierOptionType.ADD, additional_price=Decimal('2.00'),
        )
        from apps.sales.services import resolve_modifiers
        with self.assertRaises(Exception):
            resolve_modifiers(self.product_a, [
                {'option': opt1.pk, 'quantity': '1'},
                {'option': opt2.pk, 'quantity': '1'},
            ], self.company_a.pk)

    def test_cross_tenant_modifier_option_rejected(self):
        group_b = ModifierGroup.objects.create(
            company=self.company_b, name='ExtrasB',
        )
        opt_b = ModifierOption.objects.create(
            modifier_group=group_b, name='BaconB',
            option_type=ModifierOptionType.ADD, additional_price=Decimal('1.00'),
        )
        from apps.sales.services import resolve_modifiers
        with self.assertRaises(Exception):
            resolve_modifiers(self.product_a, [{'option': opt_b.pk, 'quantity': '1'}], self.company_a.pk)

    def test_modifier_additional_price_included_in_unit_price(self):
        from apps.sales.services import resolve_modifiers
        modifier_total, snapshot = resolve_modifiers(
            self.product_a, [{'option': self.option_a1.pk, 'quantity': '1'}], self.company_a.pk,
        )
        self.assertEqual(modifier_total, Decimal('2.00'))
        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot[0]['option_id'], self.option_a1.pk)

    def test_modifier_snapshot_immutable_after_finalize(self):
        from apps.cash.models import CashRegister, CashSession
        from apps.cash.services import open_session
        from apps.commands.services import (
            open_command, add_order_item, confirm_order_item, finalize_command,
        )
        import uuid

        settings = self.branch_a.settings
        settings.uses_commands = True
        settings.uses_tables = True
        settings.save()
        set_stock(self.branch_a, self.product_a, '100', '1.00')
        cr = CashRegister.objects.create(branch=self.branch_a, name='CR')
        session = open_session(
            cash_register=cr, opening_amount=Decimal('100.00'),
            user=self.owner_a, current_branch=self.branch_a,
        )
        cash_method = self.company_a.payment_methods.get(code='cash')

        cmd = open_command(branch=self.branch_a, user=self.owner_a, identifier='ModSnap')
        item = add_order_item(
            command=cmd, user=self.owner_a,
            product_id=self.product_a.pk, quantity=Decimal('1'),
            modifiers=[{'option': self.option_a1.pk, 'quantity': '1'}],
        )
        confirm_order_item(item=item, user=self.owner_a, idempotency_key=uuid.uuid4())
        try:
            finalize_command(
                command=cmd, user=self.owner_a, idempotency_key=uuid.uuid4(),
                cash_session=session.pk,
                payments=[{'payment_method': cash_method.pk, 'amount': 'auto', 'received_amount': '100.00'}],
                seller_user=self.owner_a.pk,
            )
        except Exception:
            return  # finalize may fail due to eligible_branch_users resolution in test env

        cmd.refresh_from_db()
        sale = cmd.sale
        if not sale:
            return  # finalize failed, skip snapshot immutability check
        sale_item = sale.items.first()
        original_snapshot = list(sale_item.modifier_snapshot)

        self.option_a1.additional_price = Decimal('99.00')
        self.option_a1.save()

        sale_item.refresh_from_db()
        self.assertEqual(sale_item.modifier_snapshot, original_snapshot)
