from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0001_pos5_attendance'),
        ('production', '0005_ticket_redemptions'),
    ]
    operations = [
        migrations.AddField(
            model_name='productionjob', name='attendance_order_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.PROTECT,
                                    related_name='production_jobs', to='attendance.attendanceorderitem'),
        ),
        migrations.AddField(
            model_name='ticket', name='source_attendance_order_item',
            field=models.OneToOneField(blank=True, null=True, on_delete=models.deletion.PROTECT,
                                        related_name='order_ticket', to='attendance.attendanceorderitem'),
        ),
        migrations.RemoveConstraint(model_name='productionjob', name='production_job_exactly_one_source'),
        migrations.RemoveConstraint(model_name='ticket', name='production_ticket_exactly_one_source'),
        migrations.AddConstraint(
            model_name='productionjob',
            constraint=models.CheckConstraint(
                condition=(
                    Q(order_item__isnull=False, sale_item__isnull=True, attendance_order_item__isnull=True)
                    | Q(order_item__isnull=True, sale_item__isnull=False, attendance_order_item__isnull=True)
                    | Q(order_item__isnull=True, sale_item__isnull=True, attendance_order_item__isnull=False)
                ), name='production_job_exactly_one_source',
            ),
        ),
        migrations.AddConstraint(
            model_name='productionjob',
            constraint=models.UniqueConstraint(
                fields=('attendance_order_item', 'destination', 'event'),
                condition=Q(attendance_order_item__isnull=False),
                name='production_job_attendance_order_destination_event_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='ticket',
            constraint=models.CheckConstraint(
                condition=(
                    Q(source_sale_item__isnull=False, source_order_item__isnull=True, source_attendance_order_item__isnull=True)
                    | Q(source_sale_item__isnull=True, source_order_item__isnull=False, source_attendance_order_item__isnull=True)
                    | Q(source_sale_item__isnull=True, source_order_item__isnull=True, source_attendance_order_item__isnull=False)
                ), name='production_ticket_exactly_one_source',
            ),
        ),
    ]
