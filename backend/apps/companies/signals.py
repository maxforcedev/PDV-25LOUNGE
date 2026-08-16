from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Company
from .services import ensure_default_access_profiles


@receiver(post_save, sender=Company)
def create_company_access_profiles(sender, instance, created, **kwargs):
    if created and not kwargs.get('raw'):
        ensure_default_access_profiles(instance)
        from apps.sales.services import ensure_default_payment_methods

        ensure_default_payment_methods(instance)
