from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('purchases', '0003_private_attachment'),
        ('products', '0008_v2_6_product_configuration'),
    ]
    operations = [
        migrations.AddField(model_name='purchasereceiptitem', name='stock_content_quantity', field=models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
        migrations.AddField(model_name='purchasereceiptitem', name='stock_content_unit', field=models.CharField(blank=True, max_length=2)),
        migrations.AddField(model_name='purchasereceiptitem', name='stock_package_content_snapshot', field=models.DecimalField(blank=True, decimal_places=9, max_digits=24, null=True)),
    ]
