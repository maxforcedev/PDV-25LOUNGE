from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [('production', '0014_print_document_request_fingerprint')]

    operations = [
        migrations.AddConstraint(
            model_name='printjob',
            constraint=models.UniqueConstraint(
                condition=Q(print_document__isnull=False),
                fields=('print_document', 'printer_device', 'idempotency_key'),
                name='document_print_job_idempotency_unique',
            ),
        ),
    ]
