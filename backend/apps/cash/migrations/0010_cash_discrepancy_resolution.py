from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('cash', '0009_remove_legacy_withdrawal_effect_constraint')]

    operations = [
        migrations.CreateModel(
            name='CashDiscrepancyResolution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('addressed_at', models.DateTimeField()),
                ('justification', models.TextField()),
                ('addressed_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='addressed_cash_discrepancies', to=settings.AUTH_USER_MODEL)),
                ('cash_session', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='cash_discrepancy_resolution', to='cash.cashsession')),
            ],
            options={'ordering': ('-addressed_at', '-pk')},
        ),
        migrations.AddIndex(
            model_name='cashsession',
            index=models.Index(fields=['branch', 'status', 'closed_at'], name='cash_session_attention_idx'),
        ),
    ]
