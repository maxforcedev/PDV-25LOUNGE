from django.db import migrations


def scrub_unsafe_fingerprints(apps, schema_editor):
    Sale = apps.get_model('sales', 'Sale')
    Sale.objects.exclude(idempotency_fingerprint='').update(
        idempotency_fingerprint=''
    )


class Migration(migrations.Migration):
    dependencies = [
        ('sales', '0010_sale_idempotency_fingerprint'),
    ]

    operations = [
        migrations.RunPython(scrub_unsafe_fingerprints, migrations.RunPython.noop),
    ]
