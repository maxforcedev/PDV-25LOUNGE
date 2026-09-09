from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import User
from apps.companies.selectors import customer_search_queryset
from apps.companies.services import create_company_with_matrix, create_customer


class CustomerDomainTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='customer-domain@example.com', password='Strong-password-123!',
        )
        self.company = create_company_with_matrix(
            creator=self.owner, trade_name='Customer Domain', legal_name='Customer Domain Ltda',
        )

    def test_create_normalizes_brazilian_phone_and_cpf(self):
        customer = create_customer(
            company=self.company,
            name='  Ana   Souza ',
            phone='(21) 99876-5432',
            document='529.982.247-25',
        )

        self.assertEqual(customer.name, 'Ana Souza')
        self.assertEqual(customer.phone, '21998765432')
        self.assertEqual(customer.document, '52998224725')

    def test_active_identity_values_are_unique_and_search_uses_normalized_digits(self):
        create_customer(
            company=self.company,
            name='Ana Souza',
            phone='(21) 99876-5432',
            document='529.982.247-25',
        )

        with self.assertRaises(ValidationError):
            create_customer(
                company=self.company,
                name='Outra Ana',
                phone='21998765432',
            )

        matches = customer_search_queryset(
            company=self.company, term='529.982.247-25', active_only=True,
        )
        self.assertEqual(list(matches.values_list('name', flat=True)), ['Ana Souza'])

    def test_invalid_cpf_and_phone_are_rejected(self):
        with self.assertRaises(ValidationError):
            create_customer(
                company=self.company,
                name='CPF Invalido', phone='21998765432', document='111.111.111-11',
            )
        with self.assertRaises(ValidationError):
            create_customer(
                company=self.company,
                name='Telefone Invalido', phone='219876-5432',
            )
