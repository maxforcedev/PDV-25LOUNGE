from threading import Barrier, Thread

from django.db import close_old_connections
from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase

from apps.accounts.models import User
from apps.companies.selectors import customer_search_queryset, inactive_customer_identity_match
from apps.companies.services import (
    CustomerIdentityConflict, create_company_with_matrix, create_customer, set_customer_status,
)


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

    def test_identity_values_remain_unique_after_deactivation(self):
        customer = create_customer(
            company=self.company,
            name='Ana Souza',
            phone='(21) 99876-5432',
            document='529.982.247-25',
        )
        set_customer_status(customer=customer, status='inactive')

        with self.assertRaises(CustomerIdentityConflict) as context:
            create_customer(
                company=self.company,
                name='Outra Ana',
                phone='21998765432',
                document='52998224725',
            )
        self.assertEqual(context.exception.code, 'customer_inactive_identity_conflict')
        self.assertEqual(context.exception.details['customer']['status'], 'inactive')

        matches = customer_search_queryset(
            company=self.company, term='529.982.247-25', active_only=False,
        )
        self.assertEqual(list(matches.values_list('name', flat=True)), ['Ana Souza'])
        self.assertEqual(
            inactive_customer_identity_match(self.company, '529.982.247-25').pk,
            customer.pk,
        )

        other_company = create_company_with_matrix(
            creator=self.owner, trade_name='Other Customer Domain', legal_name='Other Customer Domain Ltda',
        )
        other_customer = create_customer(
            company=other_company,
            name='Ana de Outra Empresa',
            phone='21998765432',
            document='52998224725',
        )
        self.assertEqual(other_customer.company_id, other_company.pk)

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

    def test_phone_and_cpf_from_different_customers_are_rejected(self):
        create_customer(company=self.company, name='Cliente A', phone='21999999999')
        create_customer(
            company=self.company,
            name='Cliente B', phone='21888888888', document='52998224725',
        )

        with self.assertRaises(CustomerIdentityConflict) as context:
            create_customer(
                company=self.company,
                name='Dados Cruzados',
                phone='21999999999',
                document='52998224725',
            )

        self.assertEqual(context.exception.code, 'customer_identity_mismatch')
        self.assertEqual(context.exception.details, {})


class CustomerConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='customer-concurrency@example.com', password='Strong-password-123!',
        )
        self.company = create_company_with_matrix(
            creator=self.owner,
            trade_name='Customer Concurrency',
            legal_name='Customer Concurrency Ltda',
        )

    def test_concurrent_creates_return_a_domain_conflict_for_one_request(self):
        barrier = Barrier(2)
        results = []

        def create_in_parallel(name):
            close_old_connections()
            try:
                barrier.wait()
                create_customer(
                    company=self.company, name=name, phone='21999999999',
                )
                results.append('created')
            except CustomerIdentityConflict as error:
                results.append(error.code)
            finally:
                close_old_connections()

        first = Thread(target=create_in_parallel, args=('Cliente Concorrente A',))
        second = Thread(target=create_in_parallel, args=('Cliente Concorrente B',))
        first.start()
        second.start()
        first.join(timeout=10)
        second.join(timeout=10)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertCountEqual(results, ['created', 'customer_identity_conflict'])
