import logging
import re
import uuid
from contextvars import ContextVar

from django.conf import settings


SENSITIVE_KEYS = {
    'password',
    'credential',
    'token',
    'secret',
    'csrf',
    'authorization',
    'pin',
}

_request_metadata = ContextVar('audit_request_metadata', default={})
_request_event_count = ContextVar('audit_request_event_count', default=0)
logger = logging.getLogger(__name__)
MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
SAFE_REQUEST_ID = re.compile(r'^[A-Za-z0-9._:-]{1,100}$')


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
    log = AuditLog.objects.create(
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
    _request_event_count.set(_request_event_count.get() + 1)
    return log


def require_audit_fallback(request):
    """Require one request-level fallback in addition to any rich side-effect events."""
    request.audit_fallback_required = True


class AuditRequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        forwarded = (
            request.META.get('HTTP_X_FORWARDED_FOR', '')
            if settings.TRUST_PROXY_HEADERS
            else ''
        )
        ip_address = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')
        supplied_request_id = request.META.get('HTTP_X_REQUEST_ID', '')
        request_id = supplied_request_id if SAFE_REQUEST_ID.fullmatch(supplied_request_id) else str(uuid.uuid4())
        supplied_correlation_id = request.META.get('HTTP_X_CORRELATION_ID', '')
        correlation_id = supplied_correlation_id if SAFE_REQUEST_ID.fullmatch(supplied_correlation_id) else request_id
        request.request_id = request_id
        request.correlation_id = correlation_id
        token = _request_metadata.set({
            'ip_address': ip_address,
            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
            'request_id': request_id,
            'correlation_id': correlation_id,
        })
        count_token = _request_event_count.set(0)
        actor = request.user if getattr(request.user, 'is_authenticated', False) else None
        try:
            response = self.get_response(request)
            response['X-Request-ID'] = request_id
            response['X-Correlation-ID'] = correlation_id
            if (
                request.method in MUTATING_METHODS
                and request.path.startswith('/api/v1/')
                and 200 <= response.status_code < 400
                and (
                    _request_event_count.get() == 0
                    or getattr(request, 'audit_fallback_required', False)
                )
                and not getattr(request, 'audit_fallback_suppressed', False)
            ):
                self._fallback(request, response, actor)
            return response
        finally:
            _request_event_count.reset(count_token)
            _request_metadata.reset(token)

    @staticmethod
    def _fallback(request, response, actor):
        try:
            match = getattr(request, 'resolver_match', None)
            view_class = getattr(getattr(match, 'func', None), 'cls', None)
            view_name = view_class.__name__ if view_class else (match.view_name if match else 'api')
            action = getattr(getattr(match, 'func', None), 'actions', {}).get(
                request.method.lower(), request.method.lower()
            )
            branch = getattr(request, 'branch_context', None)
            company = getattr(branch, 'company', None)
            audit_log(
                actor=(request.user if getattr(request.user, 'is_authenticated', False) else actor),
                action=f'api.{action}',
                company=company,
                branch=branch,
                metadata={
                    'object_type': view_name,
                    'object_id': (match.kwargs.get('pk', '') if match else ''),
                    'fallback': True,
                    'method': request.method,
                    'path': request.path,
                    'status_code': response.status_code,
                },
            )
        except Exception:
            logger.exception('Failed to persist mutation audit fallback for %s %s', request.method, request.path)
