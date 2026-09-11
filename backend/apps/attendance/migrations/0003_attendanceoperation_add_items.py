from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('attendance', '0002_attendance_open_command_operation')]

    operations = [
        migrations.AlterField(
            model_name='attendanceoperation',
            name='operation_type',
            field=models.CharField(
                choices=[
                    ('open_table', 'Abrir mesa'),
                    ('open_command', 'Abrir comanda'),
                    ('add_items', 'Adicionar itens'),
                    ('transfer_command', 'Transferir comanda'),
                    ('transfer_items', 'Transferir itens'),
                    ('cancel_item', 'Cancelar item'),
                    ('reverse_payment', 'Estornar pagamento'),
                ],
                max_length=20,
            ),
        ),
    ]
