#!/bin/sh
set -eu

python - <<'PY'
import time
import os

import django
from django.db import OperationalError, connections

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

for attempt in range(1, 31):
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT 1')
            print('PostgreSQL is ready.')
            break
    except OperationalError:
        if attempt == 30:
            raise SystemExit('PostgreSQL did not become ready in time.')
        print(f'Waiting for PostgreSQL ({attempt}/30)...')
        time.sleep(2)
PY

case "$(printf '%s' "${MIGRATE_ON_START:-True}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on)
        python manage.py migrate --noinput
        ;;
    0|false|no|off)
        ;;
    *)
        echo 'MIGRATE_ON_START must be a boolean value.' >&2
        exit 1
        ;;
esac

exec "$@"
