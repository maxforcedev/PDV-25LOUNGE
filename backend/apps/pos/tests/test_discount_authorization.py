from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.urls import reverse

from apps.pos.serializers import POSDiscountAuthorizationValidationSerializer
from apps.sales.services import _discount_approver


class POSDiscountAuthorizationTests(SimpleTestCase):
    permission_codes = ('sales.apply_discount', 'sales.apply_item_discount')

    def _approver(self, *, password_valid=True):
        approver = MagicMock()
        approver.check_password.return_value = password_valid
        queryset = MagicMock()
        queryset.filter.return_value.first.return_value = approver
        return approver, queryset

    def test_validation_adapter_uses_the_canonical_flat_payload(self):
        serializer = POSDiscountAuthorizationValidationSerializer(data={
            'type': 'sale', 'user': 7, 'method': 'password', 'credential': 'secret',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            reverse('pos:sale-discount-authorization-validate'),
            '/api/v1/pos/sales/discount-authorizations/validate/',
        )

    def test_pos_finalization_guard_rejects_missing_authorization(self):
        operator = SimpleNamespace(is_superuser=False)
        with patch('apps.sales.services.user_has_branch_permission', return_value=False):
            for permission_code in self.permission_codes:
                with self.subTest(permission_code=permission_code):
                    with self.assertRaises(ValidationError):
                        _discount_approver(
                            SimpleNamespace(pk=1), operator, Decimal('1.00'), None,
                            permission_code=permission_code,
                            authorization_field='authorization', allow_pos_only=True,
                        )

    def test_pos_finalization_guard_rejects_wrong_password(self):
        operator = SimpleNamespace(is_superuser=False)
        for permission_code in self.permission_codes:
            approver, queryset = self._approver(password_valid=False)
            with self.subTest(permission_code=permission_code), \
                    patch('apps.sales.services.user_has_branch_permission', return_value=False), \
                    patch('apps.sales.services.eligible_branch_users', return_value=queryset):
                with self.assertRaisesMessage(ValidationError, 'Senha inválida.'):
                    _discount_approver(
                        SimpleNamespace(pk=1), operator, Decimal('1.00'),
                        {'user': 7, 'method': 'password', 'credential': 'wrong'},
                        permission_code=permission_code,
                        authorization_field='authorization', allow_pos_only=True,
                    )
            approver.check_password.assert_called_once_with('wrong')

    def test_pos_finalization_guard_accepts_eligible_authorizer_with_password(self):
        operator = SimpleNamespace(is_superuser=False)
        for permission_code in self.permission_codes:
            approver, queryset = self._approver(password_valid=True)
            with self.subTest(permission_code=permission_code), \
                    patch('apps.sales.services.user_has_branch_permission', return_value=False), \
                    patch('apps.sales.services.eligible_branch_users', return_value=queryset):
                self.assertIs(
                    _discount_approver(
                        SimpleNamespace(pk=1), operator, Decimal('1.00'),
                        {'user': 7, 'method': 'password', 'credential': 'correct'},
                        permission_code=permission_code,
                        authorization_field='authorization', allow_pos_only=True,
                    ),
                    approver,
                )

    def test_pos_finalization_guard_rejects_authorizer_outside_branch_or_permission(self):
        operator = SimpleNamespace(is_superuser=False)
        for permission_code in self.permission_codes:
            queryset = MagicMock()
            queryset.filter.return_value.first.return_value = None
            with self.subTest(permission_code=permission_code), \
                    patch('apps.sales.services.user_has_branch_permission', return_value=False), \
                    patch('apps.sales.services.eligible_branch_users', return_value=queryset):
                with self.assertRaises(ValidationError):
                    _discount_approver(
                        SimpleNamespace(pk=1), operator, Decimal('1.00'),
                        {'user': 99, 'method': 'password', 'credential': 'irrelevant'},
                        permission_code=permission_code,
                        authorization_field='authorization', allow_pos_only=True,
                    )

    def test_pos_superuser_does_not_bypass_effective_branch_permission(self):
        operator = SimpleNamespace(is_superuser=True)
        with patch('apps.sales.services.user_has_branch_permission', return_value=False) as permission:
            with self.assertRaises(ValidationError):
                _discount_approver(
                    SimpleNamespace(pk=1), operator, Decimal('1.00'), None,
                    permission_code='sales.apply_discount',
                    authorization_field='authorization', allow_pos_only=True,
                )
        self.assertEqual(permission.call_args.kwargs['allow_superuser'], False)
