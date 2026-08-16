import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def classify_existing_withdrawals(apps, schema_editor):
    CashMovement = apps.get_model('cash', 'CashMovement')
    CashMovement.objects.filter(
        movement_type='withdrawal', withdrawal_category__isnull=True
    ).update(withdrawal_category='other')


class Migration(migrations.Migration):
    dependencies = [
        ('cash', '0001_initial'),
        ('companies', '0012_sprint_7_1_permissions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='cashmovement',
            name='withdrawal_category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('dj', 'DJ'),
                    ('artist', 'Pagode/Artista'),
                    ('advance', 'Vale/Adiantamento'),
                    ('promoter', 'Promoter'),
                    ('supplier', 'Fornecedor'),
                    ('other', 'Outros'),
                ],
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='cashmovement',
            name='beneficiary_user',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='beneficiary_cash_withdrawals',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(
            classify_existing_withdrawals, migrations.RunPython.noop
        ),
        migrations.AddConstraint(
            model_name='cashmovement',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        movement_type='manual_entry',
                        withdrawal_category__isnull=True,
                        beneficiary_user__isnull=True,
                    )
                    | models.Q(
                        movement_type='withdrawal',
                        withdrawal_category__isnull=False,
                    )
                ),
                name='cash_movement_withdrawal_classification_coherent',
            ),
        ),
        migrations.AddConstraint(
            model_name='cashmovement',
            constraint=models.CheckConstraint(
                condition=(
                    ~models.Q(
                        withdrawal_category__in=('dj', 'artist', 'advance', 'promoter')
                    )
                    | models.Q(beneficiary_user__isnull=False)
                ),
                name='cash_movement_required_beneficiary_coherent',
            ),
        ),
    ]
