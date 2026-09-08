from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.urls import reverse

from apps.pos.serializers import POSDiscountAuthorizationValidationSerializer
from apps.pos.services import validate_pos_authorization
from apps.sales.services import (
    _authorization_identity, _discount_approver, _service_fee_waiver,
    catalog_products_with_available_stock,
)


class POSDiscountAuthorizationTests(SimpleTestCase):
    def _authorizer_queryset(self, approver):
        queryset = MagicMock()
        queryset.filter.return_value.first.return_value = approver
        return queryset

    def test_pos_contract_accepts_pin_and_rejects_web_password(self):
        serializer = POSDiscountAuthorizationValidationSerializer(data={
            'type': 'sale', 'user': 7, 'method': 'pin', 'credential': '123456',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertFalse(POSDiscountAuthorizationValidationSerializer(data={
            'type': 'sale', 'user': 7, 'method': 'password', 'credential': 'web-password',
        }).is_valid())
        self.assertEqual(
            reverse('pos:sale-discount-authorization-validate'),
            '/api/v1/pos/sales/discount-authorizations/validate/',
        )

    def test_pos_authorization_uses_six_digit_pin_not_web_password(self):
        device = SimpleNamespace(pk='device', branch_id=1)
        branch = SimpleNamespace(pk=1)
        approver = SimpleNamespace(pk=7, pos_pin_hash='pos-pin-hash')
        with patch('apps.pos.services.validate_device_operational', return_value=device), \
                patch('apps.pos.services.eligible_pos_authorizers', return_value=self._authorizer_queryset(approver)), \
                patch('apps.pos.services._limited', return_value=False), \
                patch('apps.pos.services.check_password', return_value=True) as check_pin, \
                patch('apps.pos.services._clear_limit'), \
                patch('apps.pos.services._authorization_audit'):
            self.assertIs(validate_pos_authorization(
                device, branch, {'user': 7, 'method': 'pin', 'credential': '123456'},
                permission_code='sales.apply_discount', authorization_field='authorization',
            ), approver)
        check_pin.assert_called_once_with('123456', 'pos-pin-hash')

    def test_pos_authorization_rejects_wrong_pin_and_records_separate_limiter(self):
        device = SimpleNamespace(pk='device', branch_id=1)
        branch = SimpleNamespace(pk=1)
        approver = SimpleNamespace(pk=7, pos_pin_hash='pos-pin-hash')
        with patch('apps.pos.services.validate_device_operational', return_value=device), \
                patch('apps.pos.services.eligible_pos_authorizers', return_value=self._authorizer_queryset(approver)), \
                patch('apps.pos.services._limited', return_value=False), \
                patch('apps.pos.services.check_password', return_value=False), \
                patch('apps.pos.services._record_limit_failure', return_value=False) as limited, \
                patch('apps.pos.services._authorization_audit'):
            with self.assertRaisesMessage(ValidationError, 'PIN inválido.'):
                validate_pos_authorization(
                    device, branch, {'user': 7, 'method': 'pin', 'credential': '000000'},
                    permission_code='sales.apply_discount', authorization_field='authorization',
                )
        limited.assert_called_once()

    def test_pos_delegated_permissions_do_not_mix(self):
        operator = SimpleNamespace(is_superuser=False)
        branch = SimpleNamespace(pk=1)
        device = SimpleNamespace(pk='device', branch_id=1)
        approver = SimpleNamespace(pk=7)
        with patch('apps.sales.services.user_has_branch_permission', return_value=False), \
                patch('apps.pos.services.validate_pos_authorization', return_value=approver) as validate:
            self.assertIs(_discount_approver(
                branch, operator, Decimal('1.00'),
                {'user': 7, 'method': 'pin', 'credential': '123456'},
                permission_code='sales.apply_item_discount', authorization_field='authorization',
                allow_pos_only=True, pos_device=device,
            ), approver)
            self.assertIs(_service_fee_waiver(
                branch, operator, True,
                {'user': 7, 'method': 'pin', 'credential': '123456'},
                allow_pos_only=True, pos_device=device,
            ), approver)
        self.assertEqual(
            [call.kwargs['permission_code'] for call in validate.call_args_list],
            ['sales.apply_item_discount', 'sales.waive_service_fee'],
        )

    def test_pin_is_excluded_from_sale_idempotency_identity(self):
        self.assertEqual(
            _authorization_identity(
                {'user': 7, 'method': 'pin', 'credential': '123456'},
            ),
            {'user': 7, 'method': 'pin'},
        )

    def test_pos_superuser_does_not_bypass_effective_branch_permission(self):
        operator = SimpleNamespace(is_superuser=True)
        with patch('apps.sales.services.user_has_branch_permission', return_value=False) as permission, \
                patch('apps.pos.services.validate_pos_authorization', side_effect=ValidationError('PIN inválido.')):
            with self.assertRaises(ValidationError):
                _discount_approver(
                    SimpleNamespace(pk=1), operator, Decimal('1.00'), None,
                    permission_code='sales.apply_discount', authorization_field='authorization',
                    allow_pos_only=True, pos_device=SimpleNamespace(pk='device', branch_id=1),
                )
        self.assertEqual(permission.call_args.kwargs['allow_superuser'], False)


class POSCatalogVisibilityTests(SimpleTestCase):
    def test_hidden_catalog_uses_physical_stock_not_negative_stock_sale_capability(self):
        stocked = SimpleNamespace(pk=1)
        unavailable_negative_allowed = SimpleNamespace(pk=2)
        inventory_none = SimpleNamespace(pk=3)
        states = {
            1: {'stock_applicable': True, 'stock_available': True, 'can_sell': True},
            2: {'stock_applicable': True, 'stock_available': False, 'can_sell': True},
            3: {'stock_applicable': False, 'stock_available': True, 'can_sell': True},
        }
        with patch('apps.sales.services.catalog_product_operational_states', return_value=states):
            visible = catalog_products_with_available_stock(
                SimpleNamespace(), [stocked, unavailable_negative_allowed, inventory_none],
            )
        self.assertEqual(visible, [stocked, inventory_none])
