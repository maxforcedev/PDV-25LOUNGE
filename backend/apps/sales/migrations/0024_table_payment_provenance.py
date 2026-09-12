import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('attendance', '0008_table_equal_split_snapshot'), ('sales', '0023_attendance_payment_provenance')]
    operations = [migrations.AddField(model_name='payment', name='source_table_payment', field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='final_payment', to='attendance.tablepayment'))]
