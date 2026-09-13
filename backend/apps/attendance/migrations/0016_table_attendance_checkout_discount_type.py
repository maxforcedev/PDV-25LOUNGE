from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0015_table_checkout_approvals'),
    ]

    operations = [
        migrations.AddField(
            model_name='tableattendance',
            name='checkout_discount_type',
            field=models.CharField(
                choices=[('amount', 'Valor'), ('percentage', 'Percentual')],
                default='amount', max_length=10,
            ),
        ),
    ]
