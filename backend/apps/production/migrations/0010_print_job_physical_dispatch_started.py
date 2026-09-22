from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('production', '0009_print_job_pos_executor'),
    ]

    operations = [
        migrations.AddField(
            model_name='printjob',
            name='physical_dispatch_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
