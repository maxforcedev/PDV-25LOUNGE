from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('sales', '0009_finalize_idempotency_item_discounts_and_cost_snapshots'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='idempotency_fingerprint',
            field=models.CharField(blank=True, default='', editable=False, max_length=64),
        ),
    ]
