from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0001_pos5_attendance'),
        ('sales', '0022_manual_discount_intents'),
    ]
    operations = [
        migrations.AddField(
            model_name='payment', name='source_attendance_payment',
            field=models.OneToOneField(blank=True, null=True, on_delete=models.deletion.PROTECT,
                                        related_name='final_payment', to='attendance.attendancepayment'),
        ),
    ]
