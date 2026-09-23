from django.db import migrations


PERMISSIONS = (
    ('print_routes.manage', 'Configurar rotas de impressão', 'Configurar políticas de documentos e overrides por POS da filial.'),
    ('print_documents.view', 'Visualizar documentos de impressão', 'Consultar snapshots e histórico de documentos impressos.'),
    ('print_documents.print', 'Imprimir documentos', 'Gerar a primeira impressão de documentos comerciais.'),
    ('print_documents.reprint', 'Reimprimir documentos', 'Solicitar cópia explícita e auditada de documento comercial.'),
)


def add_document_printing_permissions(apps, schema_editor):
    Permission = apps.get_model('companies', 'FunctionalPermission')
    AccessProfile = apps.get_model('companies', 'AccessProfile')
    created = {}
    for code, label, description in PERMISSIONS:
        created[code], _ = Permission.objects.update_or_create(
            code=code,
            defaults={'module': 'production', 'scope': 'BRANCH', 'label': label, 'description': description, 'status': 'active'},
        )
    assignments = {
        'Administrador': set(created),
        'Gerente': {'print_documents.view', 'print_documents.print', 'print_documents.reprint'},
        'Operador de Caixa': {'print_documents.view', 'print_documents.print'},
    }
    for profile_name, codes in assignments.items():
        for profile in AccessProfile.objects.filter(name=profile_name, is_system=True):
            profile.permissions.add(*(created[code] for code in codes))


class Migration(migrations.Migration):
    dependencies = [('companies', '0055_grant_table_operations_to_system_profiles')]
    operations = [migrations.RunPython(add_document_printing_permissions, migrations.RunPython.noop)]
