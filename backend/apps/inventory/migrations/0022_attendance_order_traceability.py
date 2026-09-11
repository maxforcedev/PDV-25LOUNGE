from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0001_pos5_attendance'),
        ('inventory', '0021_operational_text_optional'),
    ]
    operations = [
        migrations.AddField(
            model_name='stockmovement', name='attendance_order_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.PROTECT,
                                    related_name='stock_movements', to='attendance.attendanceorderitem'),
        ),
        migrations.RemoveConstraint(model_name='stockmovement', name='inventory_movement_sales_links_coherent'),
        migrations.AddConstraint(
            model_name='stockmovement',
            constraint=models.CheckConstraint(
                condition=(
                    Q(movement_type__in=('entry', 'exit', 'adjustment'), sale__isnull=True, original_movement__isnull=True)
                    | Q(movement_type__in=('sale', 'consumption'), sale__isnull=False, original_movement__isnull=True)
                    | Q(movement_type='sale', sale__isnull=True, order_item__isnull=False, original_movement__isnull=True, domain_origin='ORDER')
                    | Q(movement_type='sale', sale__isnull=True, attendance_order_item__isnull=False, original_movement__isnull=True, domain_origin='ATTENDANCE_ORDER')
                    | Q(movement_type__in=('sale_cancellation', 'consumption_cancellation'), sale__isnull=False, original_movement__isnull=False)
                    | Q(movement_type='sale_cancellation', sale__isnull=True, order_item__isnull=False, original_movement__isnull=False, domain_origin='ORDER_CANCELLATION')
                    | Q(movement_type='sale_cancellation', sale__isnull=True, attendance_order_item__isnull=False, original_movement__isnull=False, domain_origin='ATTENDANCE_ORDER_CANCELLATION')
                ), name='inventory_movement_sales_links_coherent',
            ),
        ),
        migrations.AddConstraint(
            model_name='stockmovement',
            constraint=models.UniqueConstraint(
                fields=('attendance_order_item', 'stock'),
                condition=Q(attendance_order_item__isnull=False, movement_type='sale', domain_origin='ATTENDANCE_ORDER', original_movement__isnull=True),
                name='inventory_attendance_order_item_stock_original_unique',
            ),
        ),
    ]
