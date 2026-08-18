from rest_framework import serializers

from apps.sales.serializers import readable_user_name

from .models import AuditLog
from .labels import audit_labels


class AuditLogSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.trade_name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    actor_name = serializers.SerializerMethodField()
    action_label = serializers.SerializerMethodField()
    module_label = serializers.SerializerMethodField()
    object_label = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            'id', 'company', 'company_name', 'branch', 'branch_name', 'actor',
            'actor_name', 'action', 'action_label', 'module_label', 'object_label',
            'object_type', 'object_id', 'before', 'after',
            'metadata', 'created_at',
        )

    def get_actor_name(self, log):
        return readable_user_name(log.actor) if log.actor_id else None

    def get_action_label(self, log):
        return audit_labels(log)['action_label']

    def get_module_label(self, log):
        return audit_labels(log)['module_label']

    def get_object_label(self, log):
        return audit_labels(log)['object_label']
