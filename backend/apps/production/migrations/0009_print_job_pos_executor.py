from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('pos', '0005_posdevice_active_cash_session'),
        ('production', '0008_table_foundation_corrections'),
    ]

    operations = [
        migrations.AddField(
            model_name='printjob', name='batch_key',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='printjob', name='claimed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='claimed_print_jobs', to='pos.posdevice'),
        ),
        migrations.AddField(
            model_name='printjob', name='executor_metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='printjob', name='lease_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='printjob', name='status',
            field=models.CharField(choices=[
                ('pending', 'Pendente'), ('processing', 'Processando'),
                ('printed', 'Impresso'), ('failed', 'Falhou'),
                ('uncertain', 'Resultado incerto'), ('cancelled', 'Cancelado'),
            ], default='pending', max_length=12),
        ),
    ]
