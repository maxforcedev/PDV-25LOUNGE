from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ('products', '0017_modifier_group_quantity_limits'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='category', name='deleted_at',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='category', name='deleted_by',
            field=models.ForeignKey(
                blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='deleted_product_categories', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='productbranchconfig', name='participates_in_service_fee',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='productbranchconfig', name='participates_in_commission',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.RemoveConstraint(
            model_name='category', name='products_category_branch_name_ci_unique',
        ),
        migrations.AddConstraint(
            model_name='category',
            constraint=models.UniqueConstraint(
                'branch', Lower('name'), condition=Q(deleted_at__isnull=True),
                name='products_category_active_branch_name_ci_unique',
            ),
        ),
    ]
