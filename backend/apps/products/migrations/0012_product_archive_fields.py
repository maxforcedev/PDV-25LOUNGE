from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0011_product_emits_ticket'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='archived_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='product',
            name='archived_by',
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name='archived_products',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
