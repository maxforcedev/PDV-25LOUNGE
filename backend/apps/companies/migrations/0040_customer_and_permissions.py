import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


PERMISSIONS = [
    ('customers.view', 'customers', 'COMPANY', 'Visualizar clientes', 'Visualizar clientes da empresa.'),
    ('customers.add', 'customers', 'COMPANY', 'Cadastrar clientes', 'Cadastrar clientes na empresa.'),
    ('customers.change', 'customers', 'COMPANY', 'Editar clientes', 'Editar clientes da empresa.'),
    ('customers.deactivate', 'customers', 'COMPANY', 'Inativar clientes', 'Inativar clientes da empresa.'),
]


def add_permissions(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    permissions = []
    for code, module, scope, label, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={'module': module, 'scope': scope, 'label': label, 'description': description, 'status': 'active'},
        )
        permissions.append(permission)
    for profile in AccessProfile.objects.filter(name='Administrador', is_system=True):
        profile.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('companies', '0039_production_permissions')]

    operations = [
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=150)),
                ('phone', models.CharField(blank=True, max_length=20)),
                ('document', models.CharField(blank=True, max_length=20, null=True)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('birth_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('active', 'Ativo'), ('inactive', 'Inativo')], default='active', max_length=10)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='customers', to='companies.company')),
            ],
            options={'ordering': ('name', 'id')},
        ),
        migrations.AddConstraint(
            model_name='customer',
            constraint=models.UniqueConstraint(condition=Q(document__isnull=False), fields=('company', 'document'), name='companies_customer_company_document_unique'),
        ),
        migrations.RunPython(add_permissions, migrations.RunPython.noop),
    ]
