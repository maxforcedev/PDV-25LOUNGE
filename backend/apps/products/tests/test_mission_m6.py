from decimal import Decimal
import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.cash.models import CashRegister
from apps.cash.services import open_session
from apps.commands.services import (
    add_order_item, cancel_order_item, confirm_order_item, open_command,
)
from apps.companies.services import create_company_with_matrix, ensure_permission_catalog
from apps.companies.models import Branch
from apps.inventory.models import Stock, StockMovement
from apps.products.models import (
    Category, InventoryBehavior, ModifierGroup, ModifierOption,
    ModifierOptionType, Product, ProductComponent, ProductModifierGroup, Unit,
    ProductBranchConfig,
)
from apps.sales.services import resolve_modifiers
from apps.sales.models import OperationType
from apps.sales.services import cancel_sale, ensure_default_payment_methods, finalize_sale
from apps.suppliers.models import Supplier


PASSWORD = 'Mission-m6-password-123!'


class IntelligentModifierMissionTests(TestCase):
    def setUp(self):
        ensure_permission_catalog()
        self.owner = User.objects.create_user(email='m6-owner@example.com', password=PASSWORD)
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='M6', legal_name='Mission Six',
        )
        self.branch = self.company.branches.get(is_matrix=True)
        self.branch.settings.uses_commands = True
        self.branch.settings.uses_counter = True
        self.branch.settings.uses_cash_register = True
        self.branch.settings.save()
        self.category = Category.objects.create(
            company=self.company, branch=self.branch, name='Bebidas M6'
        )
        self.black = self.product('Black Label', 'M6-BLACK')
        self.red_bull = self.product('Red Bull', 'M6-RB')
        self.watermelon = self.product('Red Bull Melancia', 'M6-WATER')
        self.tropical = self.product('Red Bull Tropical', 'M6-TROP')
        self.original = self.product('Red Bull Original', 'M6-ORIG')
        self.bacon = self.product('Bacon extra', 'M6-BACON')
        self.combo = Product.objects.create(
            company=self.company, category=self.category, name='Combo Black',
            internal_code='M6-COMBO', unit=Unit.UNIT, cost=Decimal('30.00'),
            sale_price=Decimal('100.00'), inventory_behavior=InventoryBehavior.COMPONENTS,
            is_sellable=False,
        )
        ProductComponent.objects.create(
            parent_product=self.combo, component_product=self.black, quantity=Decimal('1'),
        )
        ProductComponent.objects.create(
            parent_product=self.combo, component_product=self.red_bull, quantity=Decimal('5'),
        )
        self.combo.is_sellable = True
        self.combo.save()
        ProductBranchConfig.objects.create(
            product=self.combo, branch=self.branch, category=self.category,
        )
        self.group = ModifierGroup.objects.create(
            company=self.company, branch=self.branch, name='Sabores de Red Bull', is_required=True,
            min_selections=1, allow_option_quantity=True,
            substitution_component=self.red_bull,
        )
        self.melancia = ModifierOption.objects.create(
            modifier_group=self.group, name='Melancia',
            option_type=ModifierOptionType.COMPONENT_SUBSTITUTION,
            stock_product=self.watermelon,
        )
        self.tropical_option = ModifierOption.objects.create(
            modifier_group=self.group, name='Tropical',
            option_type=ModifierOptionType.COMPONENT_SUBSTITUTION,
            stock_product=self.tropical,
        )
        self.original_option = ModifierOption.objects.create(
            modifier_group=self.group, name='Original',
            option_type=ModifierOptionType.COMPONENT_SUBSTITUTION,
            stock_product=self.original,
        )
        self.traditional_option = ModifierOption.objects.create(
            modifier_group=self.group, name='Tradicional',
            option_type=ModifierOptionType.COMPONENT_SUBSTITUTION,
            stock_product=self.red_bull,
        )
        ProductModifierGroup.objects.create(product=self.red_bull, modifier_group=self.group)
        self.extra_group = ModifierGroup.objects.create(
            company=self.company, branch=self.branch, name='Adicionais M6', allow_option_quantity=True,
        )
        self.bacon_option = ModifierOption.objects.create(
            modifier_group=self.extra_group, name='Bacon extra',
            option_type=ModifierOptionType.PRODUCT_INPUT, stock_product=self.bacon,
        )
        ProductModifierGroup.objects.create(product=self.red_bull, modifier_group=self.extra_group)
        for product, quantity in (
            (self.black, '10'), (self.red_bull, '10'), (self.watermelon, '10'),
            (self.tropical, '10'), (self.original, '10'), (self.bacon, '10'),
        ):
            stock, _created = Stock.objects.get_or_create(product=product, branch=self.branch)
            stock.current_quantity = Decimal(quantity)
            stock.average_unit_cost = Decimal('1.00')
            stock.last_unit_cost = Decimal('1.00')
            stock.save(update_fields=(
                'current_quantity', 'average_unit_cost', 'last_unit_cost', 'updated_at',
            ))

    def product(self, name, code):
        product = Product.objects.create(
            company=self.company, category=self.category, name=name, internal_code=code,
            unit=Unit.UNIT, cost=Decimal('1.00'), sale_price=Decimal('5.00'),
        )
        ProductBranchConfig.objects.create(
            product=product, branch=self.branch, category=self.category,
        )
        return product

    def selections(self, watermelon, tropical):
        return [
            {'option': self.melancia.pk, 'quantity': str(watermelon)},
            {'option': self.tropical_option.pk, 'quantity': str(tropical)},
        ]

    def test_standalone_requires_one_substitution_and_preserves_snapshot(self):
        command = open_command(branch=self.branch, user=self.owner, identifier='M6 avulso')
        item = add_order_item(
            command=command, user=self.owner, product_id=self.red_bull.pk,
            quantity=Decimal('1'), modifiers=[{'option': self.melancia.pk, 'quantity': '1'}],
        )
        snapshot = item.modifier_snapshot

        self.assertEqual(snapshot[0]['substituted_component_id'], self.red_bull.pk)
        self.assertEqual(snapshot[0]['stock_product_id'], self.watermelon.pk)
        self.assertEqual(snapshot[0]['selected_quantity'], '1')
        self.melancia.name = 'Nome alterado depois da venda'
        self.melancia.save()
        item.refresh_from_db()
        self.assertEqual(item.modifier_snapshot[0]['option_name'], 'Melancia')

    def test_combo_requires_exact_inherited_component_quantity(self):
        self.assertFalse(ProductModifierGroup.objects.filter(
            product=self.combo, modifier_group=self.group,
        ).exists())
        _total, snapshot = resolve_modifiers(
            self.combo, self.selections(3, 2), self.company.pk,
            branch=self.branch, item_quantity=Decimal('1'),
        )
        self.assertEqual(sum(Decimal(row['selected_quantity']) for row in snapshot), Decimal('5'))
        with self.assertRaisesRegex(
            ValidationError, r'exige 5 unidade\(s\); recebido 4',
        ):
            resolve_modifiers(
                self.combo, [{'option': self.melancia.pk, 'quantity': '4'}],
                self.company.pk, branch=self.branch, item_quantity=Decimal('1'),
            )
        with self.assertRaises(ValidationError):
            resolve_modifiers(
                self.combo, self.selections(3, 3), self.company.pk,
                branch=self.branch, item_quantity=Decimal('1'),
            )

    def test_combo_scales_inherited_component_quantity(self):
        _total, snapshot = resolve_modifiers(
            self.combo, self.selections(6, 4), self.company.pk,
            branch=self.branch, item_quantity=Decimal('2'),
        )
        self.assertEqual(
            sum(Decimal(row['selected_quantity']) for row in snapshot), Decimal('10'),
        )

    def test_confirm_and_cancel_replace_generic_component_without_duplication(self):
        command = open_command(branch=self.branch, user=self.owner, identifier='M6')
        item = add_order_item(
            command=command, user=self.owner, product_id=self.combo.pk,
            quantity=Decimal('1'), modifiers=self.selections(3, 2),
        )
        confirmation_key = uuid.uuid4()
        confirmed = confirm_order_item(item=item, user=self.owner, idempotency_key=confirmation_key)
        confirm_order_item(item=confirmed, user=self.owner, idempotency_key=confirmation_key)

        self.assertEqual(Stock.objects.get(product=self.black, branch=self.branch).current_quantity, Decimal('9'))
        self.assertEqual(Stock.objects.get(product=self.red_bull, branch=self.branch).current_quantity, Decimal('10'))
        self.assertEqual(Stock.objects.get(product=self.watermelon, branch=self.branch).current_quantity, Decimal('7'))
        self.assertEqual(Stock.objects.get(product=self.tropical, branch=self.branch).current_quantity, Decimal('8'))
        self.assertEqual(StockMovement.objects.filter(order_item=item).count(), 3)
        self.assertEqual(
            {row['product'] for row in confirmed.component_cost_snapshot},
            {self.black.pk, self.watermelon.pk, self.tropical.pk},
        )

        cancel_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4(), reason='Teste')
        self.assertEqual(Stock.objects.get(product=self.black, branch=self.branch).current_quantity, Decimal('10'))
        self.assertEqual(Stock.objects.get(product=self.red_bull, branch=self.branch).current_quantity, Decimal('10'))
        self.assertEqual(Stock.objects.get(product=self.watermelon, branch=self.branch).current_quantity, Decimal('10'))
        self.assertEqual(Stock.objects.get(product=self.tropical, branch=self.branch).current_quantity, Decimal('10'))

    def test_component_substitution_can_keep_the_original_component(self):
        command = open_command(branch=self.branch, user=self.owner, identifier='M6 Tradicional')
        item = add_order_item(
            command=command, user=self.owner, product_id=self.combo.pk,
            quantity=Decimal('1'), modifiers=[
                {'option': self.traditional_option.pk, 'quantity': '5'},
            ],
        )

        confirmed = confirm_order_item(
            item=item, user=self.owner, idempotency_key=uuid.uuid4(),
        )

        self.assertEqual(Stock.objects.get(product=self.black, branch=self.branch).current_quantity, Decimal('9'))
        self.assertEqual(Stock.objects.get(product=self.red_bull, branch=self.branch).current_quantity, Decimal('5'))
        self.assertEqual(StockMovement.objects.filter(order_item=item).count(), 2)
        self.assertEqual(
            {row['product'] for row in confirmed.component_cost_snapshot},
            {self.black.pk, self.red_bull.pk},
        )

    def test_product_input_modifier_moves_its_real_stock(self):
        command = open_command(branch=self.branch, user=self.owner, identifier='M6 input')
        item = add_order_item(
            command=command, user=self.owner, product_id=self.red_bull.pk,
            quantity=Decimal('1'), modifiers=[
                {'option': self.melancia.pk, 'quantity': '1'},
                {'option': self.bacon_option.pk, 'quantity': '1'},
            ],
        )
        confirm_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4())

        self.assertEqual(Stock.objects.get(product=self.red_bull, branch=self.branch).current_quantity, Decimal('10'))
        self.assertEqual(Stock.objects.get(product=self.watermelon, branch=self.branch).current_quantity, Decimal('9'))
        self.assertEqual(Stock.objects.get(product=self.bacon, branch=self.branch).current_quantity, Decimal('9'))

    def test_counter_sale_substitution_uses_replacement_cost_and_cancels(self):
        for product, cost in ((self.black, '4.00'), (self.watermelon, '2.00'), (self.tropical, '3.00')):
            stock = Stock.objects.get(product=product, branch=self.branch)
            stock.average_unit_cost = Decimal(cost)
            stock.save(update_fields=('average_unit_cost', 'updated_at'))
        register = CashRegister.objects.create(branch=self.branch, name='M6 Counter')
        session = open_session(
            cash_register=register, opening_amount=Decimal('0.00'), user=self.owner,
            current_branch=self.branch,
        )
        cash = next(method for method in ensure_default_payment_methods(self.company) if method.code == 'cash')
        sale = finalize_sale(
            branch=self.branch, user=self.owner, operation_type=OperationType.SALE,
            cash_session=session.pk, seller_user=self.owner.pk,
            items=[{'product': self.combo.pk, 'quantity': '1', 'modifiers': self.selections(3, 2)}],
            payments=[{'payment_method': cash.pk, 'amount': 'auto', 'received_amount': '100.00'}],
            idempotency_key=uuid.uuid4(),
        )
        components = sale.items.get().component_cost_snapshot
        self.assertEqual({row['product'] for row in components}, {
            self.black.pk, self.watermelon.pk, self.tropical.pk,
        })
        movements = {movement.stock.product_id: movement for movement in sale.stock_movements.select_related('stock__product')}
        self.assertEqual(movements[self.watermelon.pk].unit_cost_snapshot, Decimal('2.000000000000'))
        self.assertEqual(movements[self.tropical.pk].unit_cost_snapshot, Decimal('3.000000000000'))
        cancel_sale(sale=sale, branch=self.branch, user=self.owner, reason='Teste de substituição')
        self.assertEqual(Stock.objects.get(product=self.watermelon, branch=self.branch).current_quantity, Decimal('10'))
        self.assertEqual(Stock.objects.get(product=self.tropical, branch=self.branch).current_quantity, Decimal('10'))

    def test_operational_records_are_independent_between_branches(self):
        other_branch = Branch.objects.create(company=self.company, name='M6 Outra')
        other_category = Category.objects.create(
            company=self.company, branch=other_branch, name=self.category.name,
        )
        ProductBranchConfig.objects.create(
            product=self.red_bull, branch=other_branch, category=other_category,
        )
        other_group = ModifierGroup.objects.create(
            company=self.company, branch=other_branch, name=self.group.name,
        )
        supplier = Supplier.objects.create(
            company=self.company, branch=self.branch, trade_name='Fornecedor M6'
        )

        self.assertFalse(Category.objects.filter(pk=self.category.pk, branch=other_branch).exists())
        self.assertFalse(ModifierGroup.objects.filter(pk=self.group.pk, branch=other_branch).exists())
        self.assertNotEqual(supplier.branch_id, other_branch.pk)

        from apps.products.services import soft_delete_modifier_group

        soft_delete_modifier_group(group=self.group, user=self.owner)
        self.assertFalse(ModifierGroup.objects.filter(pk=self.group.pk).exists())
        self.assertTrue(ModifierGroup.objects.filter(pk=other_group.pk).exists())
        self.assertTrue(ProductBranchConfig.objects.filter(
            product=self.red_bull, branch=other_branch, category=other_category,
        ).exists())

    def test_deleted_or_cross_tenant_option_is_blocked(self):
        from apps.products.services import soft_delete_modifier_option

        soft_delete_modifier_option(option=self.melancia, user=self.owner)
        with self.assertRaises(ValidationError):
            resolve_modifiers(
                self.red_bull, [{'option': self.melancia.pk, 'quantity': '1'}],
                self.company.pk, branch=self.branch,
            )
        other_owner = User.objects.create_user(
            email='m6-other@example.com', password=PASSWORD,
        )
        other_company = create_company_with_matrix(
            creator=other_owner, trade_name='M6 Other', legal_name='M6 Other Legal',
        )
        other_group = ModifierGroup.objects.create(
            company=other_company, name='Outro grupo',
        )
        foreign_option = ModifierOption.objects.create(
            modifier_group=other_group, name='Texto', option_type=ModifierOptionType.TEXT,
        )
        with self.assertRaises(ValidationError):
            resolve_modifiers(
                self.red_bull, [{'option': foreign_option.pk, 'quantity': '1'}],
                self.company.pk, branch=self.branch,
            )
