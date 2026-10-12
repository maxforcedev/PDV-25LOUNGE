from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [('attendance', '0019_alter_attendanceoperation_operation_type')]

    operations = [
        migrations.AddField(
            model_name='attendanceorderitem',
            name='financial_snapshot',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
