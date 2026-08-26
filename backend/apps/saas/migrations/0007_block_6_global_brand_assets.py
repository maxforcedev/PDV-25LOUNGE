from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('saas', '0003_v2_10_feature_capabilities')]
    operations = [
        migrations.AddField(model_name='globalsaassettings', name='logo_light_url', field=models.URLField(blank=True)),
        migrations.AddField(model_name='globalsaassettings', name='logo_dark_url', field=models.URLField(blank=True)),
        migrations.AddField(model_name='globalsaassettings', name='compact_logo_light_url', field=models.URLField(blank=True)),
        migrations.AddField(model_name='globalsaassettings', name='compact_logo_dark_url', field=models.URLField(blank=True)),
    ]
