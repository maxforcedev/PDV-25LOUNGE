from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('production', '0012_printer_connection_type_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrintDocumentRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('action', models.CharField(choices=[('issue', 'Emissão'), ('reprint', 'Reimpressão')], max_length=12)),
                ('idempotency_key', models.UUIDField()),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='print_document_requests', to='companies.branch')),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='requests', to='production.printdocument')),
            ],
        ),
        migrations.AddConstraint(
            model_name='printdocumentrequest',
            constraint=models.UniqueConstraint(fields=('branch', 'action', 'idempotency_key'), name='print_document_request_idempotency_unique'),
        ),
    ]
