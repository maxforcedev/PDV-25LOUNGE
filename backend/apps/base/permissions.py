from rest_framework.permissions import DjangoModelPermissions


class StrictDjangoModelPermissions(DjangoModelPermissions):
    perms_map = {
        'GET': ['%(app_label)s.view_%(model_name)s'],
        'OPTIONS': ['%(app_label)s.view_%(model_name)s'],
        'HEAD': ['%(app_label)s.view_%(model_name)s'],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }

    def has_permission(self, request, view):
        if not request.user.is_authenticated or not request.user.can_login or not request.user.is_active:
            return False
        if getattr(view, 'action', None) in {'activate', 'deactivate'}:
            queryset = self._queryset(view)
            model = queryset.model
            permission = f'{model._meta.app_label}.change_{model._meta.model_name}'
            return request.user.is_authenticated and request.user.has_perm(permission)
        return super().has_permission(request, view)
