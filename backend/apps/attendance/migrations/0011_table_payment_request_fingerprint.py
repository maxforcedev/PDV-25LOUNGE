from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('attendance', '0010_table_attendance_seller')]
    operations = [migrations.AddField(model_name='tablepayment', name='request_fingerprint', field=models.CharField(default='', editable=False, max_length=64))]
