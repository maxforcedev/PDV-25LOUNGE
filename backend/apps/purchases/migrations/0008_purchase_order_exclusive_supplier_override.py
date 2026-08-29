from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('purchases', '0007_purchase_attachment')]

    operations = [
        migrations.AddField(
            model_name='purchaseorder',
            name='exclusive_supplier_override',
            field=models.BooleanField(default=False),
        ),
    ]
