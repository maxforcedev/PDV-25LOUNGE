from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('sales', '0021_saleitem_notes')]

    operations = [
        migrations.AddField(
            model_name='sale', name='discount_intent_type',
            field=models.CharField(
                blank=True,
                choices=[('amount', 'Valor'), ('percentage', 'Percentual')],
                max_length=12, null=True,
            ),
        ),
        migrations.AddField(
            model_name='sale', name='discount_intent_value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name='saleitem', name='manual_discount_intent_type',
            field=models.CharField(
                blank=True,
                choices=[('amount', 'Valor'), ('percentage', 'Percentual')],
                max_length=12, null=True,
            ),
        ),
        migrations.AddField(
            model_name='saleitem', name='manual_discount_intent_value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True),
        ),
    ]
