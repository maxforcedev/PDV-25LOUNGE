from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone


def tombstone_inactive_tables(apps, schema_editor):
    Table = apps.get_model('commands', 'Table')
    Table.objects.filter(status='inactive', deleted_at__isnull=True).update(
        deleted_at=timezone.now(),
    )


class Migration(migrations.Migration):
    dependencies = [('commands', '0007_report_history_snapshots')]

    operations = [
        migrations.AddField(
            model_name='table', name='deleted_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(tombstone_inactive_tables, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='table', name='commands_table_branch_name_active_unique',
        ),
        migrations.AddConstraint(
            model_name='table',
            constraint=models.UniqueConstraint(
                condition=Q(deleted_at__isnull=True), fields=('branch', 'name'),
                name='commands_table_branch_name_operational_unique',
            ),
        ),
    ]
