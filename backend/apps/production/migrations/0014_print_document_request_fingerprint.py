from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('production', '0013_print_document_request')]

    operations = [
        migrations.AddField(
            model_name='printdocumentrequest',
            name='request_fingerprint',
            field=models.CharField(default='', max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='printdocumentrequest',
            name='generated_jobs',
            field=models.ManyToManyField(blank=True, related_name='document_requests', to='production.printjob'),
        ),
    ]
