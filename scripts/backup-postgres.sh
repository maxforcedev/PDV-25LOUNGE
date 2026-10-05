#!/bin/sh
set -eu

STACK_NAME=${STACK_NAME:-corepdv}
POSTGRES_DB=${POSTGRES_DB:-corepdv}
POSTGRES_USER=${POSTGRES_USER:-corepdv}
BACKUP_DIR=${BACKUP_DIR:-/var/backups/corepdv}

fail() {
    printf 'Backup failed: %s\n' "$*" >&2
    exit 1
}

command -v docker >/dev/null 2>&1 || fail 'Docker CLI is required.'
docker info >/dev/null 2>&1 || fail 'Docker daemon is unavailable.'

task_id=$(docker service ps --filter desired-state=running --format '{{.ID}}' "${STACK_NAME}_db" | head -n 1)
[ -n "$task_id" ] || fail "No running PostgreSQL task found for ${STACK_NAME}_db."
container_id=$(docker inspect --format '{{.Status.ContainerStatus.ContainerID}}' "$task_id" 2>/dev/null || true)
[ -n "$container_id" ] || fail "Could not resolve the active PostgreSQL container for task $task_id."

mkdir -p "$BACKUP_DIR"
timestamp=$(date -u '+%Y%m%dT%H%M%SZ')
backup_file="$BACKUP_DIR/${STACK_NAME}-${POSTGRES_DB}-${timestamp}.dump"
[ ! -e "$backup_file" ] || fail "Backup destination already exists: $backup_file"

printf 'Creating PostgreSQL backup: %s\n' "$backup_file"
if ! docker exec "$container_id" sh -ceu '
    export PGPASSWORD="$(cat /run/secrets/postgres_password)"
    exec pg_dump --username="$1" --dbname="$2" --format=custom
' sh "$POSTGRES_USER" "$POSTGRES_DB" >"$backup_file"; then
    fail 'pg_dump returned an error; the output file was not accepted as a backup.'
fi

[ -s "$backup_file" ] || fail "Backup file is empty: $backup_file"
chmod 600 "$backup_file"
printf 'PostgreSQL backup completed: %s\n' "$backup_file"
