SENSITIVE_KEYS = {
    'password',
    'credential',
    'token',
    'secret',
    'csrf',
    'authorization',
    'pin',
}

from contextvars import ContextVar


_request_metadata = ContextVar('audit_request_metadata', default={})


def redact(value):
    if isinstance(value, dict):
        return {
            key: ('***' if any(secret in key.lower() for secret in SENSITIVE_KEYS) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def model_snapshot(instance, fields):
    data = {}
    for field in fields:
        value = getattr(instance, field, None)
        if hasattr(value, 'pk'):
            value = value.pk
        data[field] = (
            value
            if value is None or isinstance(value, (str, int, float, bool, dict, list))
            else str(value)
        )
    return data


def audit_log(*, actor=None, action, obj=None, company=None, branch=None, before=None, after=None, metadata=None):
    from .models import AuditLog

    if obj is not None:
        object_type = f'{obj.__class__.__module__}.{obj.__class__.__name__}'
        object_id = str(getattr(obj, 'pk', '') or '')
        company = company or getattr(obj, 'company', None) or getattr(getattr(obj, 'branch', None), 'company', None)
        branch = branch or getattr(obj, 'branch', None)
    else:
        object_type = (metadata or {}).get('object_type', '')
        object_id = str((metadata or {}).get('object_id', '') or '')
    return AuditLog.objects.create(
        company=company,
        branch=branch,
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before=redact(before or {}),
        after=redact(after or {}),
        metadata=redact({**_request_metadata.get(), **(metadata or {})}),
    )


class AuditRequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip_address = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')
        token = _request_metadata.set({
            'ip_address': ip_address,
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
        })
        try:
            return self.get_response(request)
        finally:
            _request_metadata.reset(token)
