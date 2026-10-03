import django.db.models.deletion
import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('payment_integrations', '0004_cielo_smart_provider'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProviderReversalOperation',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('origin_type', models.CharField(choices=[('quick_sale', 'Venda rápida'), ('table', 'Mesa'), ('command', 'Comanda')], max_length=20)),
                ('origin_id', models.CharField(max_length=80)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('reason', models.TextField(blank=True, default='')),
                ('idempotency_key', models.UUIDField(editable=False)),
                ('request_fingerprint', models.CharField(editable=False, max_length=64)),
                ('status', models.CharField(choices=[('created', 'Criada'), ('processing', 'Processando'), ('approved', 'Aprovada'), ('cancelled', 'Cancelada'), ('error', 'Erro'), ('unknown', 'Desconhecida'), ('applied', 'Aplicada')], db_index=True, default='created', max_length=10)),
                ('provider_status', models.CharField(blank=True, default='', max_length=100)),
                ('provider_status_code', models.CharField(blank=True, default='', max_length=100)),
                ('provider_message', models.CharField(blank=True, default='', max_length=500)),
                ('response_metadata', models.JSONField(blank=True, default=dict)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('authorized_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='authorized_provider_reversals', to=settings.AUTH_USER_MODEL)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='provider_reversals', to='companies.branch')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='provider_reversals', to='companies.company')),
                ('operator', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='provider_reversals', to=settings.AUTH_USER_MODEL)),
                ('pos_device', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='provider_reversals', to='pos.posdevice')),
                ('provider_connection', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reversal_operations', to='payment_integrations.paymentproviderconnection')),
                ('source_attempt', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reversal_operations', to='payment_integrations.paymentattempt')),
                ('terminal', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reversal_operations', to='payment_integrations.paymentterminal')),
            ],
            options={'ordering': ('-created_at',)},
        ),
        migrations.AddConstraint(model_name='providerreversaloperation', constraint=models.CheckConstraint(condition=models.Q(('amount__gt', 0)), name='provider_reversal_amount_positive')),
        migrations.AddConstraint(model_name='providerreversaloperation', constraint=models.UniqueConstraint(fields=('company', 'idempotency_key'), name='provider_reversal_company_idempotency_unique')),
        migrations.AddConstraint(model_name='providerreversaloperation', constraint=models.UniqueConstraint(condition=models.Q(('status__in', ('created', 'processing', 'unknown', 'approved'))), fields=('source_attempt',), name='provider_reversal_source_blocking_unique')),
        migrations.AddIndex(model_name='providerreversaloperation', index=models.Index(fields=['branch', 'status', 'created_at'], name='prov_rev_branch_stat_idx')),
    ]
