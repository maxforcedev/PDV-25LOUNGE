from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [('saas', '0009_pos_capabilities')]

    operations = [
        migrations.AddField(
            model_name='globalsaassettings',
            name='public_signup_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='CommercialLead',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=150)),
                ('company_name', models.CharField(max_length=150)),
                ('whatsapp', models.CharField(max_length=24)),
                ('email', models.EmailField(max_length=254)),
                ('segment', models.CharField(max_length=100)),
                ('message', models.TextField(blank=True)),
                ('source_path', models.CharField(blank=True, max_length=500)),
                ('plan_interest', models.CharField(blank=True, max_length=100)),
                ('utm_source', models.CharField(blank=True, max_length=150)),
                ('utm_medium', models.CharField(blank=True, max_length=150)),
                ('utm_campaign', models.CharField(blank=True, max_length=150)),
                ('status', models.CharField(choices=[('NEW', 'Novo'), ('CONTACTED', 'Contatado'), ('QUALIFIED', 'Qualificado'), ('LOST', 'Perdido'), ('CONVERTED', 'Convertido')], default='NEW', max_length=12)),
            ],
            options={'ordering': ('-created_at', '-id')},
        ),
    ]
