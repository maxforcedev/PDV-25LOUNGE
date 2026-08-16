from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.companies.models import Branch
from apps.products.models import InventoryBehavior, Product

from .models import Stock


@receiver(post_save, sender=Product)
def create_product_stocks(sender, instance, raw, **kwargs):
    if raw or instance.inventory_behavior != InventoryBehavior.DIRECT:
        return
    Stock.objects.bulk_create(
        [
            Stock(product_id=instance.pk, branch_id=branch_id)
            for branch_id in Branch.objects.filter(
                company_id=instance.company_id
            ).values_list('id', flat=True)
        ],
        ignore_conflicts=True,
    )


@receiver(post_save, sender=Branch)
def create_branch_stocks(sender, instance, raw, **kwargs):
    if raw:
        return
    Stock.objects.bulk_create(
        [
            Stock(product_id=product_id, branch_id=instance.pk)
            for product_id in Product.objects.filter(
                company_id=instance.company_id,
                inventory_behavior=InventoryBehavior.DIRECT,
            ).values_list('id', flat=True)
        ],
        ignore_conflicts=True,
    )
