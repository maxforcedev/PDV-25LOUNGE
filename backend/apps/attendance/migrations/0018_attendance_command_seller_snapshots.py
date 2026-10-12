from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [('attendance', '0017_remove_legacy_command_table_constraint')]

    operations = [
        migrations.AddField(
            model_name='attendancecommand',
            name='commission_rate_snapshot',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='attendancecommand',
            name='seller_user',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='sold_attendance_commands', to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
