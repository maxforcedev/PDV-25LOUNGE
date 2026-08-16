import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('products', '0003_product_category_data')]

    operations = [
        migrations.AlterModelOptions(
            name='category',
            options={'ordering': ('sort_order', 'name', 'id')},
        ),
        migrations.AlterField(
            model_name='product',
            name='category',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='products',
                to='products.category',
            ),
        ),
        migrations.AlterField(
            model_name='product',
            name='unit',
            field=models.CharField(
                choices=[('un', 'UN'), ('kg', 'KG'), ('g', 'G'), ('l', 'L'), ('ml', 'ML')],
                default='un',
                max_length=5,
            ),
        ),
    ]
