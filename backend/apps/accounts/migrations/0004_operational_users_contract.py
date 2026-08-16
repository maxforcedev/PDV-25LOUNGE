from django.db import migrations, models
from django.db.models import Q
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [('accounts', '0003_operational_users_data')]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='can_login',
            field=models.BooleanField(db_default=True, default=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='user_type',
            field=models.CharField(
                choices=[
                    ('employee', 'Funcionario'),
                    ('promoter', 'Promoter'),
                    ('dj', 'DJ'),
                    ('artist', 'Artista'),
                    ('other', 'Outro'),
                ],
                default='employee',
                db_default='employee',
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.UniqueConstraint(
                Lower('email'),
                condition=Q(email__isnull=False),
                name='accounts_user_email_ci_unique_not_null',
            ),
        ),
    ]
