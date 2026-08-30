from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models.functions import Lower
from django.test import TransactionTestCase


class ModifierSoftDeleteMigrationTests(TransactionTestCase):
    migrate_from = [('products', '0013_intelligent_modifier_stock_links')]
    migrate_to = [('products', '0014_modifier_soft_delete')]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Company = old_apps.get_model('companies', 'Company')
        ModifierGroup = old_apps.get_model('products', 'ModifierGroup')
        ModifierOption = old_apps.get_model('products', 'ModifierOption')
        company = Company.objects.create(
            trade_name='Migration modifiers', legal_name='Migration modifiers Ltda',
        )
        archived = ModifierGroup.objects.create(
            company=company, name='Archived', status='inactive',
        )
        active = ModifierGroup.objects.create(company=company, name='Flavours')
        ModifierOption.objects.create(
            modifier_group=archived, name='Legacy child', status='active',
        )
        ModifierOption.objects.create(modifier_group=active, name='Bacon')
        ModifierOption.objects.create(modifier_group=active, name='BACON')

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(self.migrate_to)
        super().tearDown()

    def test_migration_converts_inactive_tree_and_disambiguates_ci_names(self):
        ModifierGroup = self.apps.get_model('products', 'ModifierGroup')
        ModifierOption = self.apps.get_model('products', 'ModifierOption')

        archived = ModifierGroup.objects.get(name='Archived')
        child = ModifierOption.objects.get(modifier_group=archived)
        active_names = list(ModifierOption.objects.filter(
            modifier_group__name='Flavours', deleted_at__isnull=True,
        ).annotate(normalized_name=Lower('name')).values_list(
            'normalized_name', flat=True
        ))

        self.assertIsNotNone(archived.deleted_at)
        self.assertEqual(archived.status, 'inactive')
        self.assertIsNotNone(child.deleted_at)
        self.assertEqual(child.status, 'inactive')
        self.assertEqual(len(set(active_names)), 2)
