#!/bin/sh
set -eu

STACK_FILE=${STACK_FILE:-docker-stack.yml}
STACK_NAME=${STACK_NAME:-corepdv}
TRAEFIK_NETWORK=${TRAEFIK_NETWORK:-traefik_public}
SMTP_STACK_FILE=${SMTP_STACK_FILE:-docker-stack.smtp.yml}
SMTP_ENABLED=${SMTP_ENABLED:-False}

fail() {
    printf 'Preflight failed: %s\n' "$*" >&2
    exit 1
}

require_value() {
    name=$1
    value=$(printenv "$name" || true)
    [ -n "$value" ] || fail "$name must be set."
}

require_secret() {
    secret_name=$1
    docker secret inspect "$secret_name" >/dev/null 2>&1 || \
        fail "Docker secret '$secret_name' does not exist."
    printf 'Secret available: %s\n' "$secret_name"
}

require_image() {
    image=$1
    docker manifest inspect "$image" >/dev/null 2>&1 || \
        fail "Image '$image' is not available to this Docker client."
    printf 'Image available: %s\n' "$image"
}

stack_config() {
    if [ "$SMTP_ENABLED" = 'True' ]; then
        [ -f "$SMTP_STACK_FILE" ] || fail "SMTP stack file '$SMTP_STACK_FILE' was not found."
        docker stack config --compose-file "$STACK_FILE" --compose-file "$SMTP_STACK_FILE"
    else
        docker stack config --compose-file "$STACK_FILE"
    fi
}

command -v docker >/dev/null 2>&1 || fail 'Docker CLI is required.'
docker info >/dev/null 2>&1 || fail 'Docker daemon is unavailable.'
[ "$(docker info --format '{{.Swarm.LocalNodeState}}')" = 'active' ] || \
    fail 'Docker Swarm must be active on this host.'
[ -f "$STACK_FILE" ] || fail "Stack file '$STACK_FILE' was not found."

require_value RELEASE_TAG
[ "${#RELEASE_TAG}" -eq 40 ] && printf '%s' "$RELEASE_TAG" | grep -Eq '^[0-9a-f]{40}$' || \
    fail 'RELEASE_TAG must be a full 40-character lowercase commit SHA.'

for variable in API_DOMAIN FRONTEND_DOMAIN FRONTEND_URL PLATFORM_ADMIN_DOMAIN ALLOWED_HOSTS \
    CSRF_TRUSTED_ORIGINS CORS_ALLOWED_ORIGINS POSTGRES_DB POSTGRES_USER; do
    require_value "$variable"
done

docker network inspect "$TRAEFIK_NETWORK" >/dev/null 2>&1 || \
    fail "External Traefik network '$TRAEFIK_NETWORK' does not exist."
printf 'Network available: %s\n' "$TRAEFIK_NETWORK"
docker service inspect "${STACK_NAME}_db" >/dev/null 2>&1 || \
    fail "Existing PostgreSQL service '${STACK_NAME}_db' does not exist."
docker service ps --filter desired-state=running --format '{{.ID}}' "${STACK_NAME}_db" | grep -q . || \
    fail "Existing PostgreSQL service '${STACK_NAME}_db' has no running task."
printf 'PostgreSQL service available: %s\n' "${STACK_NAME}_db"

DJANGO_SECRET_NAME=${DJANGO_SECRET_NAME:-corepdv_django_secret_key}
POSTGRES_PASSWORD_SECRET_NAME=${POSTGRES_PASSWORD_SECRET_NAME:-corepdv_postgres_password}
CIELO_SMART_CLIENT_ID_SECRET_NAME=${CIELO_SMART_CLIENT_ID_SECRET_NAME:-corepdv_cielo_smart_client_id}
CIELO_SMART_ACCESS_TOKEN_SECRET_NAME=${CIELO_SMART_ACCESS_TOKEN_SECRET_NAME:-corepdv_cielo_smart_access_token}
SMTP_PASSWORD_SECRET_NAME=${SMTP_PASSWORD_SECRET_NAME:-corepdv_smtp_password}

require_secret "$DJANGO_SECRET_NAME"
require_secret "$POSTGRES_PASSWORD_SECRET_NAME"
require_secret "$CIELO_SMART_CLIENT_ID_SECRET_NAME"
require_secret "$CIELO_SMART_ACCESS_TOKEN_SECRET_NAME"

case "$SMTP_ENABLED" in
    True) ;;
    False) ;;
    *) fail 'SMTP_ENABLED must be True or False.' ;;
esac

if [ "$SMTP_ENABLED" = 'True' ]; then
    for variable in EMAIL_HOST EMAIL_PORT EMAIL_HOST_USER DEFAULT_FROM_EMAIL SALES_LEAD_EMAIL; do
        require_value "$variable"
    done
    [ "${EMAIL_USE_TLS:-True}" != 'True' ] || [ "${EMAIL_USE_SSL:-False}" != 'True' ] || \
        fail 'EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be True.'
    require_secret "$SMTP_PASSWORD_SECRET_NAME"
fi

BACKEND_IMAGE=${BACKEND_IMAGE:-ghcr.io/maxforcedev/core-pdv-backend}
FRONTEND_IMAGE=${FRONTEND_IMAGE:-ghcr.io/maxforcedev/core-pdv-frontend}
PLATFORM_ADMIN_IMAGE=${PLATFORM_ADMIN_IMAGE:-ghcr.io/maxforcedev/core-pdv-platform-admin}
for image in "$BACKEND_IMAGE:$RELEASE_TAG" "$FRONTEND_IMAGE:$RELEASE_TAG" "$PLATFORM_ADMIN_IMAGE:$RELEASE_TAG"; do
    require_image "$image"
done

stack_config >/dev/null || fail 'Docker stack configuration is invalid.'
printf 'Production preflight passed for stack %s and release %s.\n' "$STACK_NAME" "$RELEASE_TAG"
