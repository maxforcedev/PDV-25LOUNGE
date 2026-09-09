import uuid

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


def backfill_validation_codes(apps, schema_editor):
    Ticket = apps.get_model('production', 'Ticket')
    for ticket in Ticket.objects.filter(validation_code__isnull=True).iterator():
        ticket.validation_code = uuid.uuid4()
        ticket.save(update_fields=('validation_code',))


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pos', '0002_pos_performance_and_catalog_settings'),
        ('production', '0004_printer_operational_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='validation_code',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_validation_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='ticket',
            name='validation_code',
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='status',
            field=models.CharField(choices=[('issued', 'Emitido'), ('partially_used', 'Parcialmente utilizado'), ('used', 'Utilizado'), ('cancelled', 'Cancelado')], default='issued', max_length=14),
        ),
        migrations.CreateModel(
            name='TicketRedemption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('redeemed_at', models.DateTimeField()),
                ('idempotency_key', models.UUIDField()),
                ('request_fingerprint', models.CharField(max_length=64)),
                ('input_method', models.CharField(choices=[('scan', 'Scanner'), ('manual', 'Manual')], max_length=10)),
                ('device', models.ForeignKey(on_delete=models.deletion.PROTECT, related_name='ticket_redemptions', to='pos.posdevice')),
                ('operator', models.ForeignKey(on_delete=models.deletion.PROTECT, related_name='ticket_redemptions', to=settings.AUTH_USER_MODEL)),
                ('ticket', models.ForeignKey(on_delete=models.deletion.PROTECT, related_name='redemptions', to='production.ticket')),
            ],
            options={'ordering': ('redeemed_at', 'id')},
        ),
        migrations.AddConstraint(model_name='ticketredemption', constraint=models.CheckConstraint(condition=Q(('quantity__gt', 0)), name='production_ticket_redemption_quantity_positive')),
        migrations.AddConstraint(model_name='ticketredemption', constraint=models.UniqueConstraint(fields=('ticket', 'idempotency_key'), name='production_ticket_redemption_idempotency_unique')),
    ]
