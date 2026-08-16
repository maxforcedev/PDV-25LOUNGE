import django.db.models.deletion
import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('companies', '0004_company_companies_company_trade_name_ci_unique_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='FunctionalPermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(max_length=100, unique=True)),
                ('module', models.CharField(max_length=50)),
                ('label', models.CharField(max_length=150)),
                ('description', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('active', 'Ativo'), ('inactive', 'Inativo')], default='active', max_length=10)),
            ],
            options={'ordering': ('module', 'code')},
        ),
        migrations.CreateModel(
            name='AccessProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('is_system', models.BooleanField(default=False)),
                ('status', models.CharField(choices=[('active', 'Ativo'), ('inactive', 'Inativo')], default='active', max_length=10)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='access_profiles', to='companies.company')),
                ('permissions', models.ManyToManyField(blank=True, related_name='access_profiles', to='companies.functionalpermission')),
            ],
            options={
                'ordering': ('company__trade_name', 'name'),
                'constraints': [
                    models.UniqueConstraint(
                        models.F('company'),
                        django.db.models.functions.text.Lower('name'),
                        name='companies_access_profile_company_name_ci_unique',
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name='usercompanyaccess',
            name='access_profile',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='user_accesses',
                to='companies.accessprofile',
            ),
        ),
    ]
