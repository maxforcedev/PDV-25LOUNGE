from decimal import Decimal
import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.commands.services import (
    add_order_item, cancel_order_item, confirm_order_item, open_command,
)
from apps.companies.services import create_company_with_matrix, ensure_permission_catalog
from apps.inventory.models import Stock, StockMovement
from apps.products.models import (
    Category, InventoryBehavior, ModifierGroup, ModifierOption,
    ModifierOptionType, Product, ProductComponent, ProductModifierGroup, Unit,
)
from apps.sales.services import resolve_modifiers


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
        self.branch.settings.save()
        self.category = Category.objects.create(company=self.company, name='Bebidas M6')
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
        self.group = ModifierGroup.objects.create(
            company=self.company, name='Sabores de Red Bull', is_required=True,
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
        ProductModifierGroup.objects.create(product=self.red_bull, modifier_group=self.group)
        self.extra_group = ModifierGroup.objects.create(
            company=self.company, name='Adicionais M6', allow_option_quantity=True,
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
        return Product.objects.create(
            company=self.company, category=self.category, name=name, internal_code=code,
            unit=Unit.UNIT, cost=Decimal('1.00'), sale_price=Decimal('5.00'),
        )

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

        cancel_order_item(item=item, user=self.owner, idempotency_key=uuid.uuid4(), reason='Teste')
        self.assertEqual(Stock.objects.get(product=self.black, branch=self.branch).current_quantity, Decimal('10'))
        self.assertEqual(Stock.objects.get(product=self.red_bull, branch=self.branch).current_quantity, Decimal('10'))
        self.assertEqual(Stock.objects.get(product=self.watermelon, branch=self.branch).current_quantity, Decimal('10'))
        self.assertEqual(Stock.objects.get(product=self.tropical, branch=self.branch).current_quantity, Decimal('10'))

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

    def test_inactive_or_cross_tenant_option_is_blocked(self):
        self.melancia.status = 'inactive'
        self.melancia.save()
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
