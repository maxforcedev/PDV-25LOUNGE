from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('cash', '0004_cash_movement_operation_reference')]
    operations = [
        migrations.AddField(model_name='cashsession', name='cancelled_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='cashsession', name='cancellation_reason', field=models.TextField(blank=True)),
        migrations.AddField(model_name='cashsession', name='cancelled_by', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='cancelled_cash_sessions', to=settings.AUTH_USER_MODEL)),
        migrations.AlterField(model_name='cashsession', name='status', field=models.CharField(choices=[('open', 'Aberto'), ('closed', 'Fechado'), ('cancelled', 'Anulado')], default='open', max_length=10)),
        migrations.RemoveConstraint(model_name='cashsession', name='cash_session_status_closing_coherent'),
        migrations.AddConstraint(model_name='cashsession', constraint=models.CheckConstraint(condition=(models.Q(('status', 'open'), ('closed_by__isnull', True), ('closed_at__isnull', True), ('closing_expected_amount__isnull', True), ('closing_amount_informed__isnull', True), ('closing_difference__isnull', True)) | models.Q(('status', 'closed'), ('closed_by__isnull', False), ('closed_at__isnull', False), ('closing_expected_amount__isnull', False), ('closing_amount_informed__isnull', False), ('closing_difference__isnull', False)) | models.Q(('status', 'cancelled'), ('closed_by__isnull', True), ('closed_at__isnull', True), ('closing_expected_amount__isnull', True), ('closing_amount_informed__isnull', True), ('closing_difference__isnull', True), ('cancelled_by__isnull', False), ('cancelled_at__isnull', False))), name='cash_session_status_closing_coherent')),
    ]
