from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('attendance', '0006_table_foundation_corrections')]

    operations = [
        migrations.AlterField(
            model_name='attendanceoperation',
            name='operation_type',
            field=models.CharField(
                max_length=20,
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
                    ('table_close', 'Fechar atendimento de mesa'),
                ],
            ),
        ),
    ]
