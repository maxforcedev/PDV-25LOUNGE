from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0003_attendanceoperation_add_items'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancecommand', name='bill_requested_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='attendancecommand', name='bill_requested_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT,
                                    related_name='requested_attendance_bills', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='AttendanceTableGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('separated_at', models.DateTimeField(blank=True, null=True)),
                ('branch', models.ForeignKey(on_delete=models.PROTECT, related_name='attendance_table_groups', to='companies.branch')),
                ('company', models.ForeignKey(on_delete=models.PROTECT, related_name='attendance_table_groups', to='companies.company')),
                ('created_by', models.ForeignKey(on_delete=models.PROTECT, related_name='created_attendance_table_groups', to=settings.AUTH_USER_MODEL)),
                ('separated_by', models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT, related_name='separated_attendance_table_groups', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='AttendanceTableGroupMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('left_at', models.DateTimeField(blank=True, null=True)),
                ('group', models.ForeignKey(on_delete=models.PROTECT, related_name='memberships', to='attendance.attendancetablegroup')),
                ('joined_by', models.ForeignKey(on_delete=models.PROTECT, related_name='joined_attendance_table_groups', to=settings.AUTH_USER_MODEL)),
                ('left_by', models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT, related_name='left_attendance_table_groups', to=settings.AUTH_USER_MODEL)),
                ('table', models.ForeignKey(on_delete=models.PROTECT, related_name='attendance_group_memberships', to='commands.table')),
            ],
        ),
        migrations.AddConstraint(
            model_name='attendancetablegroupmembership',
            constraint=models.UniqueConstraint(condition=Q(left_at__isnull=True), fields=('table',), name='attendance_one_active_group_per_table'),
        ),
        migrations.AlterField(
            model_name='attendanceoperation', name='operation_type',
            field=models.CharField(choices=[
                ('open_table', 'Abrir mesa'), ('open_command', 'Abrir comanda'), ('add_items', 'Adicionar itens'),
                ('transfer_command', 'Transferir comanda'), ('transfer_items', 'Transferir itens'),
                ('cancel_item', 'Cancelar item'), ('reverse_payment', 'Estornar pagamento'),
                ('group_tables', 'Agrupar mesas'), ('separate_table', 'Separar mesa'),
                ('request_bill', 'Solicitar conta'), ('clear_bill', 'Limpar solicitação de conta'),
            ], max_length=20),
        ),
    ]
