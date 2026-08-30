from unittest.mock import patch

from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.base.release import log_release_metadata


RELEASE_SETTINGS = {
    'APP_VERSION': '0.9.0',
    'GIT_SHA': 'a82ef91full',
    'BUILD_DATE': '2026-08-29T12:00:00Z',
    'ENVIRONMENT': 'test',
}


class SessionPolicyTests(SimpleTestCase):
    def test_session_uses_eight_hour_sliding_expiration(self):
        self.assertEqual(settings.SESSION_COOKIE_AGE, 28800)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)
        self.assertFalse(settings.SESSION_EXPIRE_AT_BROWSER_CLOSE)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax')

    @override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies')
    def test_active_session_cookie_is_renewed(self):
        def start_session(request):
            request.session['authenticated'] = True
            return HttpResponse()

        middleware = SessionMiddleware(start_session)
        first_response = middleware(RequestFactory().get('/'))
        session_cookie = first_response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(session_cookie['max-age'], 28800)

        def read_session(request):
            self.assertTrue(request.session['authenticated'])
            return HttpResponse()

        middleware = SessionMiddleware(read_session)
        next_request = RequestFactory().get(
            '/',
            HTTP_COOKIE=f'{settings.SESSION_COOKIE_NAME}={session_cookie.value}',
        )
        next_response = middleware(next_request)
        self.assertIn(settings.SESSION_COOKIE_NAME, next_response.cookies)


@override_settings(**RELEASE_SETTINGS)
class ReleaseMetadataTests(SimpleTestCase):
    def test_api_root_exposes_release_metadata(self):
        response = self.client.get('/api/v1/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'name': 'CORE PDV API',
            'version': 'v1',
            'release': {
                'version': '0.9.0',
                'commit': 'a82ef91full',
                'environment': 'test',
                'build_date': '2026-08-29T12:00:00Z',
            },
        })

    def test_health_exposes_same_release_metadata(self):
        with patch('apps.base.views.connection') as database_connection:
            response = self.client.get('/health/')

        self.assertEqual(response.status_code, 200)
        execute = database_connection.cursor.return_value.__enter__.return_value.execute
        execute.assert_called_once_with('SELECT 1')
        self.assertEqual(response.json()['release']['commit'], 'a82ef91full')

    def test_startup_log_identifies_release(self):
        with self.assertLogs('django', level='INFO') as captured:
            log_release_metadata()

        self.assertIn(
            'version=0.9.0 environment=test commit=a82ef91full',
            captured.output[0],
        )
