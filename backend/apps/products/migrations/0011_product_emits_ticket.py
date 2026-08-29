from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('products', '0010_category_configuration_fields')]

    operations = [
        migrations.AddField(
            model_name='product', name='emits_ticket', field=models.BooleanField(default=False),
        ),
    ]
