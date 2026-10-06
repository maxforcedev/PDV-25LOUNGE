import apps.products.storage
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0018_category_soft_delete_financial_overrides'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='image_file',
            field=models.FileField(
                blank=True,
                max_length=500,
                storage=apps.products.storage.PrivateProductImageStorage(),
                upload_to=apps.products.storage.product_image_path,
                validators=[apps.products.storage.validate_product_image],
            ),
        ),
    ]
