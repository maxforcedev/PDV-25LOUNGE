import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('attendance', '0009_table_equal_split_cycle')]
    operations = [migrations.AddField(model_name='tableattendance', name='seller_user', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sold_table_attendances', to=settings.AUTH_USER_MODEL))]
