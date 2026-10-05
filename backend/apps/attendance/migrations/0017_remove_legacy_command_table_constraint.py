from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('attendance', '0016_table_attendance_checkout_discount_type')]

    operations = [
        migrations.RemoveConstraint(
            model_name='attendancecommand',
            name='attendance_one_open_primary_per_table',
        ),
    ]
