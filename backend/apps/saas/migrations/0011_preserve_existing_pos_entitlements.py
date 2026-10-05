from django.db import migrations


def preserve_existing_pos_access(apps, schema_editor):
    Capability = apps.get_model('saas', 'Capability')
    PlanVersion = apps.get_model('saas', 'PlanVersion')
    PlanEntitlement = apps.get_model('saas', 'PlanEntitlement')
    capabilities = {
        capability.code: capability
        for capability in Capability.objects.filter(code__in=('pos.enabled', 'pos.devices.max'))
    }
    if set(capabilities) != {'pos.enabled', 'pos.devices.max'}:
        return
    for version in PlanVersion.objects.all().iterator():
        PlanEntitlement.objects.get_or_create(
            plan_version=version,
            capability=capabilities['pos.enabled'],
            defaults={'enabled': True, 'unlimited': True, 'limit_value': None},
        )
        PlanEntitlement.objects.get_or_create(
            plan_version=version,
            capability=capabilities['pos.devices.max'],
            defaults={'enabled': True, 'unlimited': True, 'limit_value': None},
        )


class Migration(migrations.Migration):
    dependencies = [('saas', '0010_commercial_lead_and_public_signup')]

    operations = [
        migrations.RunPython(preserve_existing_pos_access, migrations.RunPython.noop),
    ]
