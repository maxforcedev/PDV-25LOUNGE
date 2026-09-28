import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payment_integrations', '0002_paymentintent_application_context_and_quick_sale_constraint'),
        ('pos', '0005_posdevice_active_cash_session'),
    ]

    operations = [
        migrations.AlterField(
            model_name='quicksalepayment',
            name='status',
            field=models.CharField(
                choices=[('applied', 'Aplicado'), ('reversed', 'Estorno')],
                default='applied',
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='quicksalepayment',
            name='source_type',
            field=models.CharField(
                choices=[('manual', 'Manual'), ('provider', 'Provedor')],
                default='manual',
                editable=False,
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='quicksalepayment',
            name='source_payment_attempt',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='quick_sale_payment',
                to='payment_integrations.paymentattempt',
            ),
        ),
    ]
