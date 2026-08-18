import uuid

from django.db import migrations, models


def populate_operation_references(apps, schema_editor):
    CashMovement = apps.get_model('cash', 'CashMovement')
    for movement in CashMovement.objects.filter(operation_reference__isnull=True).iterator():
        movement.operation_reference = uuid.uuid4()
        movement.save(update_fields=('operation_reference',))


class Migration(migrations.Migration):
    dependencies = [('cash', '0003_result_effect')]

    operations = [
        migrations.AddField(
            model_name='cashmovement',
            name='operation_reference',
            field=models.UUIDField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.RunPython(populate_operation_references, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='cashmovement',
            name='operation_reference',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
        ),
        migrations.AddConstraint(
            model_name='cashmovement',
            constraint=models.UniqueConstraint(
                fields=('cash_session', 'movement_type', 'operation_reference'),
                name='cash_movement_operation_reference_unique',
            ),
        ),
    ]
