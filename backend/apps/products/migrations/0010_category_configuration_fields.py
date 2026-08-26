from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0009_v2_7_modifiers'),
    ]

    operations = [
        migrations.AddField(
            model_name='category',
            name='available_command',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='category',
            name='available_counter',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='category',
            name='available_table',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='category',
            name='participates_in_commission',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='category',
            name='participates_in_service_fee',
            field=models.BooleanField(default=True),
        ),
    ]
