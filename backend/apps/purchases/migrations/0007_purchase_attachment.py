from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import apps.purchases.storage


def copy_legacy_attachments(apps, schema_editor):
    PurchaseOrder = apps.get_model('purchases', 'PurchaseOrder')
    PurchaseAttachment = apps.get_model('purchases', 'PurchaseAttachment')
    for order in PurchaseOrder.objects.exclude(attachment=''):
        PurchaseAttachment.objects.get_or_create(
            purchase_order_id=order.pk,
            attachment=order.attachment,
            defaults={'company_id': order.company_id, 'uploaded_by_id': order.created_by_id},
        )


class Migration(migrations.Migration):
    dependencies = [('purchases', '0006_block_4_payable_payment_and_due_date')]

    operations = [
        migrations.CreateModel(
            name='PurchaseAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('attachment', models.FileField(max_length=500, storage=apps.purchases.storage.PrivatePurchaseStorage(), upload_to=apps.purchases.storage.purchase_attachment_path, validators=[apps.purchases.storage.validate_purchase_attachment])),
                ('status', models.CharField(choices=[('active', 'Ativo'), ('inactive', 'Removido')], default='active', max_length=10)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='purchase_attachments', to='companies.company')),
                ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='attachments', to='purchases.purchaseorder')),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='uploaded_purchase_attachments', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('created_at', 'id')},
        ),
        migrations.RunPython(copy_legacy_attachments, migrations.RunPython.noop),
    ]
