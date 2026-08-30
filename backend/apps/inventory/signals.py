from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.companies.models import Branch
from apps.products.models import InventoryBehavior, Product

from .materialization import materialize_branch_stocks, materialize_product_stocks


@receiver(post_save, sender=Product)
def create_product_stocks(sender, instance, created, raw, **kwargs):
    if raw or not created or instance.inventory_behavior != InventoryBehavior.DIRECT:
        return
    materialize_product_stocks(instance)


@receiver(post_save, sender=Branch)
def create_branch_stocks(sender, instance, created, raw, **kwargs):
    if raw or not created:
        return
    materialize_branch_stocks(instance)
