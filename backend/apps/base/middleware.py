import logging
from time import perf_counter


logger = logging.getLogger('pos.performance')


class POSRequestTimingMiddleware:
    """Report full Django processing time for POS requests without request data."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith('/api/v1/pos/'):
            return self.get_response(request)

        started = perf_counter()
        logger.info('POS request_received method=%s', request.method)
        response = None
        try:
            response = self.get_response(request)
            return response
        finally:
            duration_ms = round((perf_counter() - started) * 1000)
            logger.info(
                'POS response_finished method=%s status=%s total_ms=%s',
                request.method,
                getattr(response, 'status_code', 'error'),
                duration_ms,
            )
