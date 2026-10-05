from django.db import migrations


CAPABILITIES = (
    ('feature.tables', 'Mesas'),
    ('feature.commands', 'Comandas'),
    ('feature.counter', 'Balcao'),
    ('feature.consumption', 'Consumacao interna'),
    ('feature.cash_register', 'Caixa'),
    ('feature.production', 'Producao e impressao'),
    ('feature.products', 'Produtos e catalogo'),
    ('feature.inventory', 'Estoque'),
    ('feature.purchases', 'Compras'),
    ('feature.suppliers', 'Fornecedores'),
    ('feature.customers', 'Clientes'),
    ('feature.promotions', 'Promocoes'),
    ('feature.reports', 'Relatorios'),
    ('feature.audit', 'Auditoria'),
    ('feature.financial', 'Financeiro'),
)


def seed_commercial_feature_capabilities(apps, schema_editor):
    Capability = apps.get_model('saas', 'Capability')
    PlanVersion = apps.get_model('saas', 'PlanVersion')
    PlanEntitlement = apps.get_model('saas', 'PlanEntitlement')
    capabilities = {}
    for code, name in CAPABILITIES:
        capability, _ = Capability.objects.update_or_create(
            code=code,
            defaults={'name': name, 'value_type': 'BOOLEAN', 'is_active': True},
        )
        capabilities[code] = capability
    for plan_version in PlanVersion.objects.all().iterator():
        for capability in capabilities.values():
            PlanEntitlement.objects.get_or_create(
                plan_version=plan_version,
                capability=capability,
                defaults={'enabled': True, 'unlimited': True, 'limit_value': None},
            )


class Migration(migrations.Migration):
    dependencies = [('saas', '0011_preserve_existing_pos_entitlements')]

    operations = [
        migrations.RunPython(
            seed_commercial_feature_capabilities,
            migrations.RunPython.noop,
        ),
    ]
