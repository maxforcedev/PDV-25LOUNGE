import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('companies', '0010_branch_access_profile_contract'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CashRegister',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('status', models.CharField(choices=[('active', 'Ativo'), ('inactive', 'Inativo')], default='active', max_length=10)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cash_registers', to='companies.branch')),
            ],
            options={
                'ordering': ('branch__company__trade_name', 'branch__name', 'name'),
                'constraints': [
                    models.UniqueConstraint(
                        models.F('branch'),
                        django.db.models.functions.text.Lower('name'),
                        name='cash_register_branch_name_ci_unique',
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name='CashSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('opened_at', models.DateTimeField()),
                ('opening_amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('status', models.CharField(choices=[('open', 'Aberto'), ('closed', 'Fechado')], default='open', max_length=10)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('closing_expected_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('closing_amount_informed', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('closing_difference', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cash_sessions', to='companies.branch')),
                ('cash_register', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='sessions', to='cash.cashregister')),
                ('closed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='closed_cash_sessions', to=settings.AUTH_USER_MODEL)),
                ('opened_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='opened_cash_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-opened_at', '-pk'),
                'constraints': [
                    models.CheckConstraint(condition=models.Q(('opening_amount__gte', 0)), name='cash_session_opening_nonnegative'),
                    models.CheckConstraint(condition=models.Q(('closing_amount_informed__isnull', True), ('closing_amount_informed__gte', 0), _connector='OR'), name='cash_session_closing_informed_nonnegative'),
                    models.UniqueConstraint(condition=models.Q(('status', 'open')), fields=('cash_register',), name='cash_session_one_open_per_register'),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(('status', 'open'), ('closed_by__isnull', True), ('closed_at__isnull', True), ('closing_expected_amount__isnull', True), ('closing_amount_informed__isnull', True), ('closing_difference__isnull', True)),
                            models.Q(('status', 'closed'), ('closed_by__isnull', False), ('closed_at__isnull', False), ('closing_expected_amount__isnull', False), ('closing_amount_informed__isnull', False), ('closing_difference__isnull', False)),
                            _connector='OR',
                        ),
                        name='cash_session_status_closing_coherent',
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name='CashMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('movement_type', models.CharField(choices=[('manual_entry', 'Entrada manual'), ('withdrawal', 'Sangria')], max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=14)),
                ('reason', models.TextField()),
                ('cash_session', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='movements', to='cash.cashsession')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cash_movements', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at', '-pk'),
                'constraints': [
                    models.CheckConstraint(condition=models.Q(('amount__gt', 0)), name='cash_movement_amount_positive'),
                    models.CheckConstraint(condition=models.Q(('reason', ''), _negated=True), name='cash_movement_reason_not_empty'),
                ],
            },
        ),
    ]
