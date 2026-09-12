from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('attendance', '0008_table_equal_split_snapshot')]
    operations = [
        migrations.AddField(model_name='tableattendance', name='equal_split_cycle', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='tablepaymentallocation', name='equal_split_cycle', field=models.PositiveIntegerField(blank=True, null=True)),
    ]
