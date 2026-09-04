import secrets

from django.db import migrations, models


def assign_licensing_codes(apps, schema_editor):
    Branch = apps.get_model('companies', 'Branch')
    for branch in Branch.objects.filter(licensing_code='').iterator():
        while True:
            code = f'CORE-{secrets.token_urlsafe(12).upper()}'
            if not Branch.objects.filter(licensing_code=code).exists():
                branch.licensing_code = code
                branch.save(update_fields=['licensing_code'])
                break


class Migration(migrations.Migration):
    dependencies = [('companies', '0045_repair_audited_archived_memberships')]

    operations = [
        migrations.AddField(model_name='branch', name='licensing_code', field=models.CharField(blank=True, default='', max_length=32)),
        migrations.RunPython(assign_licensing_codes, migrations.RunPython.noop),
        migrations.AlterField(model_name='branch', name='licensing_code', field=models.CharField(db_index=True, editable=False, max_length=32, unique=True)),
    ]
