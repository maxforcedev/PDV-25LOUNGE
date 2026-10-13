from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [('attendance', '0020_attendance_order_item_financial_snapshot')]

    operations = [
        migrations.AddField(
            model_name='attendancecommand',
            name='service_fee_rate_snapshot',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
    ]
