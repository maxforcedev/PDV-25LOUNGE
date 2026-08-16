from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except DatabaseError:
        return JsonResponse({'status': 'unavailable'}, status=503)

    return JsonResponse({'status': 'ok'})


@api_view(['GET'])
@permission_classes([AllowAny])
def api_root(request):
    return Response({'name': 'CORE PDV API', 'version': 'v1'})
