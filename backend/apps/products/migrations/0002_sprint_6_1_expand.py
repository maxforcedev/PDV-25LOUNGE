from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('products', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='category',
            name='sort_order',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='product',
            name='is_favorite',
            field=models.BooleanField(default=False),
        ),
    ]
