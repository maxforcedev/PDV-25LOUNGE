import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0014_table_order_and_customer_operations'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='attendanceoperation',
            name='operation_type',
            field=models.CharField(
                max_length=32,
                choices=[
                    ('open_table', 'Abrir mesa'), ('open_command', 'Abrir comanda'),
                    ('add_items', 'Adicionar itens'), ('transfer_command', 'Transferir comanda'),
                    ('transfer_items', 'Transferir itens'), ('cancel_item', 'Cancelar item'),
                    ('reverse_payment', 'Estornar pagamento'), ('group_tables', 'Agrupar mesas'),
                    ('separate_table', 'Separar mesa'), ('request_bill', 'Solicitar conta'),
                    ('clear_bill', 'Limpar solicitação de conta'), ('table_open', 'Abrir atendimento de mesa'),
                    ('table_order', 'Salvar pedido de mesa'), ('table_payment', 'Registrar pagamento de mesa'),
                    ('table_reverse_payment', 'Estornar pagamento de mesa'), ('table_cancel_item', 'Cancelar item de mesa'),
                    ('table_transfer_items', 'Transferir itens de mesa'), ('table_bill', 'Solicitar conta de mesa'),
                    ('table_close', 'Fechar atendimento de mesa'), ('table_cancel_order', 'Cancelar pedido de mesa'),
                    ('table_set_customer', 'Alterar cliente da mesa'),
                    ('table_checkout_context', 'Atualizar contexto financeiro da mesa'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='tableattendance',
            name='checkout_discount_approved_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='approved_table_checkout_discounts', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='tableattendance',
            name='checkout_service_fee_waived_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='approved_table_service_fee_waivers', to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
