from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('attendance', '0007_table_operation_types')]

    operations = [
        migrations.AddField(
            model_name='tableattendance', name='equal_split_total',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='tableattendance', name='equal_split_people_count',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
