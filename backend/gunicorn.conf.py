import os


def positive_int(name, default):
    try:
        value = int(os.environ.get(name, default))
    except ValueError as error:
        raise RuntimeError(f'{name} must be an integer.') from error
    if value < 1:
        raise RuntimeError(f'{name} must be greater than zero.')
    return value


bind = '0.0.0.0:8000'
workers = positive_int('GUNICORN_WORKERS', 2)
timeout = positive_int('GUNICORN_TIMEOUT', 60)
graceful_timeout = positive_int('GUNICORN_GRACEFUL_TIMEOUT', 30)
keepalive = positive_int('GUNICORN_KEEP_ALIVE', 5)
forwarded_allow_ips = os.environ.get('GUNICORN_FORWARDED_ALLOW_IPS', '127.0.0.1')
accesslog = '-'
errorlog = '-'
capture_output = True
control_socket_disable = True
