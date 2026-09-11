from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [('commands', '0008_table_soft_delete')]

    operations = [
        migrations.AddConstraint(
            model_name='table',
            constraint=models.CheckConstraint(
                condition=(
                    Q(deleted_at__isnull=True, status='active')
                    | Q(deleted_at__isnull=False, status='inactive')
                ),
                name='commands_table_status_tombstone_coherent',
            ),
        ),
    ]
