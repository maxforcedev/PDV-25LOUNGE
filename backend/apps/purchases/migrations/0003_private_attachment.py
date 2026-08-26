import apps.purchases.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchases', '0002_remove_purchasereceiptitem_purchases_receipt_item_quantities_valid_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='purchaseorder',
            old_name='attachment_reference',
            new_name='attachment',
        ),
        migrations.AlterField(
            model_name='purchaseorder',
            name='attachment',
            field=models.FileField(
                blank=True,
                max_length=500,
                storage=apps.purchases.storage.PrivatePurchaseStorage(),
                upload_to=apps.purchases.storage.purchase_attachment_path,
                validators=(apps.purchases.storage.validate_purchase_attachment,),
            ),
        ),
    ]
