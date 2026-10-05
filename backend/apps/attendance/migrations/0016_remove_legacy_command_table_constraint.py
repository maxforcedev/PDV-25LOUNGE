from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('attendance', '0015_table_checkout_approvals')]

    operations = [
        migrations.RemoveConstraint(
            model_name='attendancecommand',
            name='attendance_one_open_primary_per_table',
        ),
    ]
