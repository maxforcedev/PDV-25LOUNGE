#!/bin/sh
set -eu

python - <<'PY'
import os
import time

import psycopg

database_url = os.environ['DATABASE_URL']
for attempt in range(1, 31):
    try:
        with psycopg.connect(database_url, connect_timeout=3):
            print('PostgreSQL is ready.')
            break
    except psycopg.OperationalError:
        if attempt == 30:
            raise SystemExit('PostgreSQL did not become ready in time.')
        print(f'Waiting for PostgreSQL ({attempt}/30)...')
        time.sleep(2)
PY

python manage.py migrate --noinput

exec "$@"
