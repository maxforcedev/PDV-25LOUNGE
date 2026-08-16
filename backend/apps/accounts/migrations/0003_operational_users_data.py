from django.db import migrations
from django.db.models.functions import Lower
from django.db.models import Count


def preserve_existing_users(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    duplicates = list(
        User.objects.exclude(email__isnull=True)
        .exclude(email='')
        .annotate(normalized_email=Lower('email'))
        .values('normalized_email')
        .annotate(total=Count('id'))
        .filter(total__gt=1)
        .values_list('normalized_email', flat=True)
    )
    if duplicates:
        raise RuntimeError(
            'E-mails duplicados ignorando maiusculas/minusculas impedem a migration: '
            + ', '.join(duplicates)
        )
    User.objects.all().update(can_login=True, user_type='employee')
    User.objects.filter(email='').update(email=None)


class Migration(migrations.Migration):
    dependencies = [('accounts', '0002_operational_users_expand')]

    operations = [migrations.RunPython(preserve_existing_users, migrations.RunPython.noop)]
