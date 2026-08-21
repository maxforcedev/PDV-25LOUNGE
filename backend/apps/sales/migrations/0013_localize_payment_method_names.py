from django.db import migrations


PAYMENT_METHOD_NAMES = {
    'cash': 'Dinheiro',
    'pix': 'PIX',
    'credit_card': 'Cartão de crédito',
    'debit_card': 'Cartão de débito',
}


def localize_payment_method_names(apps, schema_editor):
    PaymentMethod = apps.get_model('sales', 'PaymentMethod')
    Payment = apps.get_model('sales', 'Payment')
    for code, name in PAYMENT_METHOD_NAMES.items():
        PaymentMethod.objects.filter(code=code, is_system=True).update(name=name)
        Payment.objects.filter(payment_method_code=code).update(
            payment_method_name=name
        )


class Migration(migrations.Migration):
    dependencies = [('sales', '0012_alter_promotionschedule_weekday_and_more')]
    operations = [
        migrations.RunPython(
            localize_payment_method_names,
            migrations.RunPython.noop,
        )
    ]
