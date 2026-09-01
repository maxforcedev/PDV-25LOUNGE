from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.companies.models import Branch
from apps.products.models import InventoryBehavior, Product, ProductBranchConfig

from .materialization import materialize_stock


@receiver(post_save, sender=ProductBranchConfig)
def create_branch_product_stock(sender, instance, created, raw, **kwargs):
    if raw or not created or instance.product.inventory_behavior != InventoryBehavior.DIRECT:
        return
    materialize_stock(product=instance.product, branch=instance.branch)
