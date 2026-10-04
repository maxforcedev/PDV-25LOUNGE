from django.db import migrations, models
from django.db.models import Q


def copy_transaction_ids_to_operation_keys(apps, schema_editor):
    PaymentAttempt = apps.get_model('payment_integrations', 'PaymentAttempt')
    PaymentAttempt._base_manager.filter(provider_operation_key='').exclude(
        provider_transaction_id='',
    ).update(provider_operation_key=models.F('provider_transaction_id'))


class Migration(migrations.Migration):
    dependencies = [('payment_integrations', '0005_provider_reversal_operation')]

    operations = [
        migrations.AddField(
            model_name='paymentattempt',
            name='provider_operation_key',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.RunPython(copy_transaction_ids_to_operation_keys, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='paymentattempt',
            name='payment_attempt_connection_transaction_unique',
        ),
        migrations.AddConstraint(
            model_name='paymentattempt',
            constraint=models.UniqueConstraint(
                condition=~Q(provider_operation_key=''),
                fields=('provider_connection', 'provider_operation_key'),
                name='payment_attempt_connection_operation_key_unique',
            ),
        ),
    ]
