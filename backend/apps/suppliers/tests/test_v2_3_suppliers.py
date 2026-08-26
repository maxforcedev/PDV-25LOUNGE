from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.base.labels import audit_labels
from apps.base.models import AuditLog
from apps.companies.models import (
    AccessProfile,
    Company,
    FunctionalPermission,
    UserCompanyAccess,
    UserPermissionBlock,
)
from apps.companies.services import create_company_with_matrix
from apps.products.models import Category, Product
from apps.saas.models import PlatformPermission, SupportSession
from apps.saas.services import create_support_session
from apps.saas.tests.test_v2_2_saas import (
    PASSWORD,
    create_plan,
    create_tenant,
    create_user,
)

from ..admin import ProductSupplierAdmin, ProductSupplierUnitAdmin, SupplierAdmin
from ..models import ProductSupplier, ProductSupplierUnit, Supplier
from ..serializers import SupplierSerializer
from ..services import _save_product_supplier
from ..views import SupplierViewSet


def create_company(name):
    return Company.objects.create(trade_name=name, legal_name=f'{name} Legal')


def create_product(company, name, code):
    category, _ = Category.objects.get_or_create(company=company, name='Bebidas')
    return Product.objects.create(
        company=company,
        category=category,
        name=name,
        internal_code=code,
        cost='1.00',
        sale_price='2.00',
    )


def create_supplier(company, name, tax_id=None):
    return Supplier.objects.create(
        company=company,
        legal_name=f'{name} Ltda',
        trade_name=name,
        tax_id=tax_id,
    )


class SupplierModelTests(TestCase):
    def setUp(self):
        self.company = create_company('Tenant A')
        self.other_company = create_company('Tenant B')

    def test_tax_id_is_validated_normalized_and_unique_only_per_company(self):
        supplier = create_supplier(self.company, 'Primeiro', '529.982.247-25')
        self.assertEqual(supplier.tax_id, '52998224725')

        with self.assertRaises(ValidationError):
            create_supplier(self.company, 'Duplicado', '52998224725')

        other = create_supplier(self.other_company, 'Outro tenant', '529.982.247-25')
        self.assertEqual(other.tax_id, supplier.tax_id)
        with self.assertRaises(ValidationError):
            create_supplier(self.company, 'Inválido', '111.111.111-11')
        with self.assertRaises(ValidationError):
            create_supplier(self.company, 'Somente texto', 'CPF pendente')

    def test_cross_company_relations_and_relation_identity_changes_are_rejected(self):
        product = create_product(self.company, 'Água', 'A-1')
        outsider = create_supplier(self.other_company, 'Externo')
        with self.assertRaises(ValidationError):
            ProductSupplier.objects.create(
                company=self.company, product=product, supplier=outsider
            )

        supplier = create_supplier(self.company, 'Local')
        relation = ProductSupplier.objects.create(
            company=self.company, product=product, supplier=supplier
        )
        other_product = create_product(self.company, 'Suco', 'S-1')
        relation.product = other_product
        with self.assertRaises(ValidationError):
            relation.save()

        unit = ProductSupplierUnit.objects.create(
            company=self.company,
            product_supplier=ProductSupplier.objects.get(pk=relation.pk),
            unit_code='cx',
            description='Caixa',
            conversion_factor='12',
        )
        other_relation = ProductSupplier.objects.create(
            company=self.company, product=other_product, supplier=supplier
        )
        unit.product_supplier = other_relation
        with self.assertRaises(ValidationError):
            unit.save()

    def test_preferred_exclusive_and_default_constraints(self):
        product = create_product(self.company, 'Cerveja', 'C-1')
        first = create_supplier(self.company, 'Fornecedor A')
        second = create_supplier(self.company, 'Fornecedor B')
        ProductSupplier.objects.create(
            company=self.company,
            product=product,
            supplier=first,
            is_preferred=True,
        )
        with self.assertRaises(ValidationError):
            ProductSupplier.objects.create(
                company=self.company,
                product=product,
                supplier=second,
                is_preferred=True,
            )

        exclusive_product = create_product(self.company, 'Vinho', 'V-1')
        exclusive = _save_product_supplier(
            company=self.company,
            product=exclusive_product,
            supplier=first,
            is_exclusive=True,
        )
        self.assertTrue(exclusive.is_preferred)
        self.assertTrue(exclusive.is_exclusive)

        first_unit = ProductSupplierUnit.objects.create(
            company=self.company,
            product_supplier=exclusive,
            unit_code='CX',
            description='Caixa com 6',
            conversion_factor='6',
            is_default=True,
        )
        ProductSupplierUnit.objects.create(
            company=self.company,
            product_supplier=exclusive,
            unit_code='FD',
            description='Fardo com 12',
            conversion_factor='12',
        )
        self.assertEqual(exclusive.units.count(), 2)
        with self.assertRaises(ValidationError):
            ProductSupplierUnit.objects.create(
                company=self.company,
                product_supplier=exclusive,
                unit_code='UN',
                description='Unidade',
                conversion_factor='1',
                is_default=True,
            )
        first_unit.status = 'inactive'
        first_unit.save()
        ProductSupplierUnit.objects.create(
            company=self.company,
            product_supplier=exclusive,
            unit_code='UN',
            description='Unidade',
            conversion_factor='1',
            is_default=True,
        )

    def test_bulk_mutations_and_physical_deletion_are_blocked(self):
        product = create_product(self.company, 'Protegido', 'P-1')
        supplier = create_supplier(self.company, 'Protegido')
        relation = ProductSupplier.objects.create(
            company=self.company, product=product, supplier=supplier
        )
        unit = ProductSupplierUnit.objects.create(
            company=self.company,
            product_supplier=relation,
            unit_code='CX',
            description='Caixa',
            conversion_factor='2',
        )

        for instance in (supplier, relation, unit):
            model = type(instance)
            with self.assertRaises(ValidationError):
                model.objects.filter(pk=instance.pk).update(status='inactive')
            instance.status = 'inactive'
            with self.assertRaises(ValidationError):
                model.objects.bulk_update([instance], ['status'])
            with self.assertRaises(ValidationError):
                model.objects.bulk_create([])
            with self.assertRaises(ValidationError):
                model.objects.filter(pk=instance.pk).delete()
            with self.assertRaises(ValidationError):
                instance.delete()

    def test_supplier_admin_is_read_only(self):
        for model, admin_class in (
            (Supplier, SupplierAdmin),
            (ProductSupplier, ProductSupplierAdmin),
            (ProductSupplierUnit, ProductSupplierUnitAdmin),
        ):
            model_admin = admin_class(model, admin.site)
            self.assertFalse(model_admin.has_add_permission(None))
            self.assertFalse(model_admin.has_change_permission(None))
            self.assertFalse(model_admin.has_delete_permission(None))

    def test_conversion_factor_must_be_positive_and_multiple_suppliers_are_allowed(self):
        product = create_product(self.company, 'Refrigerante', 'R-1')
        relations = [
            ProductSupplier.objects.create(
                company=self.company,
                product=product,
                supplier=create_supplier(self.company, f'Fornecedor {index}'),
            )
            for index in range(2)
        ]
        self.assertEqual(product.product_suppliers.count(), 2)
        with self.assertRaises(ValidationError):
            ProductSupplierUnit.objects.create(
                company=self.company,
                product_supplier=relations[0],
                unit_code='CX',
                description='Caixa inválida',
                conversion_factor=Decimal('0'),
            )


class SupplierApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='supplier-admin@example.com', password='password-123'
        )
        self.company = create_company_with_matrix(
            creator=self.user, trade_name='API Tenant', legal_name='API Tenant Legal',
        )
        self.other_company = create_company_with_matrix(
            creator=User.objects.create_user(email='other-admin@example.com', password='password-123'),
            trade_name='Outro API Tenant', legal_name='Outro API Tenant Legal',
        )
        admin_profile = AccessProfile.objects.get(
            company=self.company, name='Administrador', is_system=True
        )
        UserCompanyAccess.objects.filter(
            user=self.user, company=self.company
        ).update(access_profile=admin_profile)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.branch = self.company.branches.get(is_matrix=True)
        self.client.defaults['HTTP_X_BRANCH_ID'] = str(self.branch.pk)
        self.product = create_product(self.company, 'Produto API', 'API-1')

    def supplier_payload(self, **overrides):
        payload = {
            'company': self.company.pk,
            'legal_name': 'Fornecedor API Ltda',
            'trade_name': 'Fornecedor API',
            'tax_id': '04.252.011/0001-10',
            'phone': '11999999999',
            'email': 'contato@example.com',
            'contact_name': 'Maria',
            'address': {'city': 'São Paulo', 'state': 'SP'},
            'notes': 'Entrega semanal',
        }
        payload.update(overrides)
        return payload

    def test_tenant_isolation_rbac_block_cross_tenant_rejection_and_pagination(self):
        own = create_supplier(self.company, 'Visível')
        create_supplier(self.other_company, 'Oculto')
        response = self.client.get(reverse('supplier-list'))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], own.pk)

        permission = FunctionalPermission.objects.get(code='suppliers.view')
        UserPermissionBlock.objects.create(
            company=self.company,
            user=self.user,
            permission=permission,
            reason='Teste',
        )
        response = self.client.get(reverse('supplier-list'))
        self.assertEqual(response.status_code, 403)

        UserPermissionBlock.objects.filter(user=self.user).delete()
        outsider = create_supplier(self.other_company, 'Fornecedor externo')
        response = self.client.post(
            reverse('product-supplier-list'),
            {
                'company': self.company.pk,
                'product': self.product.pk,
                'supplier': outsider.pk,
            },
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('supplier', response.data)

    def test_all_mutations_are_audited_and_delete_is_not_available(self):
        response = self.client.post(
            reverse('supplier-list'), self.supplier_payload(), format='json'
        )
        self.assertEqual(response.status_code, 201, response.data)
        supplier_id = response.data['id']
        self.assertTrue(AuditLog.objects.filter(
            action='supplier.create', object_id=str(supplier_id), company=self.company
        ).exists())

        response = self.client.patch(
            reverse('supplier-detail', args=[supplier_id]),
            {'notes': 'Nova observação'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.post(reverse('supplier-deactivate', args=[supplier_id]))
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.post(reverse('supplier-activate', args=[supplier_id]))
        self.assertEqual(response.status_code, 200, response.data)
        self.assertQuerySetEqual(
            AuditLog.objects.filter(object_id=str(supplier_id)).values_list(
                'action', flat=True
            ).order_by('id'),
            ['supplier.create', 'supplier.update', 'supplier.deactivate', 'supplier.activate'],
        )
        labels = audit_labels(AuditLog.objects.get(
            action='supplier.update', object_id=str(supplier_id)
        ))
        self.assertEqual(labels['module_label'], 'Fornecedores')
        self.assertEqual(labels['object_label'], 'Fornecedor')
        self.assertEqual(labels['action_label'], 'Fornecedor alterado')

        response = self.client.delete(reverse('supplier-detail', args=[supplier_id]))
        self.assertEqual(response.status_code, 405)

    def test_tax_id_and_address_contract(self):
        response = self.client.post(
            reverse('supplier-list'),
            self.supplier_payload(tax_id='CPF ainda não informado'),
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('tax_id', response.data)

        payload = self.supplier_payload(tax_id='')
        payload.pop('address')
        response = self.client.post(reverse('supplier-list'), payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['address'], {})
        self.assertIsNone(response.data['tax_id'])

        response = self.client.post(
            reverse('supplier-list'),
            self.supplier_payload(
                trade_name='Endereço nulo', legal_name='Endereço nulo Ltda',
                tax_id='', address=None,
            ),
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('address', response.data)

    def test_legal_name_is_optional_and_trade_name_is_required(self):
        payload = self.supplier_payload(tax_id='')
        payload.pop('legal_name')
        response = self.client.post(reverse('supplier-list'), payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['legal_name'], '')

        response = self.client.post(
            reverse('supplier-list'),
            self.supplier_payload(legal_name='', trade_name='   ', tax_id=''),
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('trade_name', response.data)

    def test_presentation_description_is_required(self):
        supplier = create_supplier(self.company, 'Fornecedor apresentação')
        relation = ProductSupplier.objects.create(
            company=self.company, product=self.product, supplier=supplier
        )
        payload = {
            'company': self.company.pk,
            'product_supplier': relation.pk,
            'unit_code': 'CX',
            'conversion_factor': '24',
        }
        response = self.client.post(
            reverse('product-supplier-unit-list'), payload, format='json'
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('description', response.data)

        response = self.client.post(
            reverse('product-supplier-unit-list'),
            {**payload, 'description': '   '},
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('description', response.data)

    def test_update_audit_uses_locked_current_snapshot(self):
        supplier = create_supplier(self.company, 'Snapshot')
        stale = Supplier.objects.get(pk=supplier.pk)
        current = Supplier.objects.get(pk=supplier.pk)
        current.notes = 'Valor corrente'
        current.save()

        serializer = SupplierSerializer(
            stale, data={'notes': 'Valor novo'}, partial=True
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        view = SupplierViewSet()
        view.request = SimpleNamespace(user=self.user)
        view.perform_update(serializer)

        log = AuditLog.objects.get(
            action='supplier.update', object_id=str(supplier.pk)
        )
        self.assertEqual(log.before['notes'], 'Valor corrente')
        self.assertEqual(log.after['notes'], 'Valor novo')

    def test_relation_and_multiple_presentations_crud(self):
        supplier_response = self.client.post(
            reverse('supplier-list'), self.supplier_payload(tax_id=''), format='json'
        )
        self.assertEqual(supplier_response.status_code, 201, supplier_response.data)
        relation_response = self.client.post(
            reverse('product-supplier-list'),
            {
                'company': self.company.pk,
                'product': self.product.pk,
                'supplier': supplier_response.data['id'],
                'supplier_code': 'REF-01',
                'is_exclusive': True,
            },
            format='json',
        )
        self.assertEqual(relation_response.status_code, 201, relation_response.data)
        self.assertTrue(relation_response.data['is_preferred'])
        relation_id = relation_response.data['id']

        for unit_code, factor, is_default in (
            ('CX', '24', True),
            ('FD', '12', False),
        ):
            response = self.client.post(
                reverse('product-supplier-unit-list'),
                {
                    'company': self.company.pk,
                    'product_supplier': relation_id,
                    'unit_code': unit_code,
                    'description': f'{unit_code} apresentação',
                    'conversion_factor': factor,
                    'is_default': is_default,
                },
                format='json',
            )
            self.assertEqual(response.status_code, 201, response.data)

        response = self.client.get(
            reverse('product-supplier-unit-list'),
            {'product_supplier': relation_id, 'company': self.company.pk},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(
            AuditLog.objects.filter(
                action='product_supplier_unit.create', company=self.company
            ).count(),
            2,
        )

        response = self.client.patch(
            reverse('product-supplier-detail', args=[relation_id]),
            {'supplier': create_supplier(self.company, 'Tentativa').pk},
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('supplier', response.data)

        response = self.client.delete(
            reverse('product-supplier-detail', args=[relation_id])
        )
        self.assertEqual(response.status_code, 405)


class SupplierSupportSessionTests(TestCase):
    def setUp(self):
        version = create_plan(code='supplier-support')
        self.owner, self.company, _ = create_tenant(
            'Supplier Support', plan_version=version
        )
        self.agent = create_user('supplier-support-agent-v23@example.com')
        call_command(
            'bootstrap_platform_admin', email=self.agent.email, stdout=StringIO()
        )
        create_supplier(self.company, 'Fornecedor em suporte')
        self.session = create_support_session(
            actor=self.agent,
            company=self.company,
            mode=SupportSession.Mode.READ_WRITE,
            reason='Corrigir fornecedor',
            current_password=PASSWORD,
        )
        self.client = APIClient()
        self.assertTrue(self.client.login(email=self.agent.email, password=PASSWORD))

    def support_headers(self):
        return {'HTTP_X_SUPPORT_SESSION_ID': str(self.session.pk)}

    def test_non_impersonated_support_gets_scoped_supplier_and_me_context(self):
        response = self.client.get(reverse('supplier-list'), **self.support_headers())
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)

        response = self.client.get(reverse('accounts:me'), **self.support_headers())
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['companies']), 1)
        context = response.data['companies'][0]
        self.assertEqual(context['id'], self.company.pk)
        self.assertTrue(context['support_context'])
        self.assertFalse(context['is_owner'])
        branch_context = response.data['branches'][0]
        self.assertIn('suppliers.view', branch_context['permissions'])
        self.assertIn('suppliers.change', branch_context['permissions'])
        self.assertFalse(UserCompanyAccess.objects.filter(
            user=self.agent, company=self.company
        ).exists())

        response = self.client.get(
            reverse('saas-owner-subscription'),
            {'company': self.company.pk},
            **self.support_headers(),
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            reverse('company-transfer-owner', args=[self.company.pk]),
            {},
            format='json',
            **self.support_headers(),
        )
        self.assertEqual(response.status_code, 403)

    def test_support_write_is_audited_and_requires_live_platform_permission(self):
        response = self.client.post(
            reverse('supplier-list'),
            {
                'company': self.company.pk,
                'legal_name': 'Novo suporte Ltda',
                'trade_name': 'Novo suporte',
                'tax_id': '',
            },
            format='json',
            **self.support_headers(),
        )
        self.assertEqual(response.status_code, 201, response.data)
        log = AuditLog.objects.get(
            action='supplier.create', object_id=str(response.data['id'])
        )
        self.assertEqual(log.actor, self.agent)
        self.assertEqual(log.metadata['support_session_id'], self.session.pk)
        self.assertFalse(UserCompanyAccess.objects.filter(
            user=self.agent, company=self.company
        ).exists())

        permission = PlatformPermission.objects.get(code='platform.support.manage')
        self.agent.platform_access.role.permissions.remove(permission)
        response = self.client.get(reverse('supplier-list'), **self.support_headers())
        self.assertIn(response.status_code, (401, 403))
