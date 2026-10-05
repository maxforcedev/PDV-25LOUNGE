#!/bin/sh
set -eu

STACK_FILE=${STACK_FILE:-docker-stack.yml}
STACK_NAME=${STACK_NAME:-corepdv}
BACKUP_FILE=${BACKUP_FILE:-}
RELEASE_WAIT_SECONDS=${RELEASE_WAIT_SECONDS:-180}

fail() {
    printf 'Release failed: %s\n' "$*" >&2
    exit 1
}

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
"$script_dir/production-preflight.sh"

[ "${#RELEASE_TAG:-}" -eq 40 ] && printf '%s' "$RELEASE_TAG" | grep -Eq '^[0-9a-f]{40}$' || \
    fail 'RELEASE_TAG must be a full 40-character lowercase commit SHA.'

printf 'Current images for %s:\n' "$STACK_NAME"
for service in backend frontend platform-admin; do
    docker service inspect "${STACK_NAME}_${service}" --format '  {{.Spec.Name}}: {{.Spec.TaskTemplate.ContainerSpec.Image}}' 2>/dev/null || \
        printf '  %s: not currently deployed\n' "$service"
done
printf 'Target release: %s\n' "$RELEASE_TAG"

docker stack config --compose-file "$STACK_FILE" >/dev/null || fail 'Docker stack configuration is invalid.'

if [ -n "$BACKUP_FILE" ]; then
    [ -s "$BACKUP_FILE" ] || fail "BACKUP_FILE is missing or empty: $BACKUP_FILE"
    printf 'Using existing backup: %s\n' "$BACKUP_FILE"
else
    "$script_dir/backup-postgres.sh"
fi

docker stack deploy --with-registry-auth --compose-file "$STACK_FILE" "$STACK_NAME" || \
    fail 'docker stack deploy returned an error.'

deadline=$(( $(date +%s) + RELEASE_WAIT_SECONDS ))
while :; do
    services=$(docker stack services --format '{{.Name}}' "$STACK_NAME")
    [ -n "$services" ] || fail "No services found for stack $STACK_NAME after deploy."
    all_running=true
    for service in $services; do
        state=$(docker service ps --filter desired-state=running --format '{{.CurrentState}}' "$service" | head -n 1)
        case "$state" in
            Running*) ;;
            *) all_running=false; printf 'Waiting for %s: %s\n' "$service" "${state:-no running task}" ;;
        esac
    done
    "$all_running" && break
    [ "$(date +%s)" -lt "$deadline" ] || fail 'Timed out waiting for running Swarm tasks.'
    sleep 5
done

docker stack services "$STACK_NAME"
"$script_dir/smoke-test.sh" || fail 'Smoke test failed after deployment.'
printf 'Release %s deployed successfully. Image rollback does not roll back PostgreSQL migrations.\n' "$RELEASE_TAG"
