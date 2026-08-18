from django.db import models
from django.conf import settings


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError('Logs de auditoria sao append-only.')

    def delete(self):
        raise ValueError('Logs de auditoria nao podem ser excluidos.')


class AuditLog(models.Model):
    objects = AuditLogQuerySet.as_manager()

    company = models.ForeignKey(
        'companies.Company', on_delete=models.PROTECT, related_name='audit_logs',
        blank=True, null=True,
    )
    branch = models.ForeignKey(
        'companies.Branch', on_delete=models.PROTECT, related_name='audit_logs',
        blank=True, null=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='audit_logs',
        blank=True, null=True,
    )
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=120)
    object_id = models.CharField(max_length=80, blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at', '-id')

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError('Logs de auditoria sao append-only.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Logs de auditoria nao podem ser excluidos.')
