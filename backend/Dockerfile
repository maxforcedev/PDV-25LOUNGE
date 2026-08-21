FROM python:3.13-slim@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --system corepdv \
    && useradd --system --gid corepdv --home-dir /app --no-create-home corepdv

COPY --chown=corepdv:corepdv . .
RUN chmod +x /app/entrypoint.sh \
    && DEBUG=False \
       SECRET_KEY=build-only-not-a-runtime-secret \
       DATABASE_URL=sqlite:////tmp/corepdv-build.sqlite3 \
       EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend \
       python manage.py collectstatic --noinput

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]


FROM base AS development

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM base AS production

USER corepdv

HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=5 \
    CMD ["python", "-c", "import urllib.request; request = urllib.request.Request('http://127.0.0.1:8000/health/', headers={'X-Forwarded-Proto': 'https'}); urllib.request.urlopen(request, timeout=3)"]

CMD ["gunicorn", "core.wsgi:application", "--config", "/app/gunicorn.conf.py"]
