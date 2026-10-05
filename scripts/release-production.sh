#!/bin/sh
set -eu

STACK_FILE=${STACK_FILE:-docker-stack.yml}
STACK_NAME=${STACK_NAME:-corepdv}
BACKUP_FILE=${BACKUP_FILE:-}
RELEASE_WAIT_SECONDS=${RELEASE_WAIT_SECONDS:-180}
SMTP_ENABLED=${SMTP_ENABLED:-False}
SMTP_STACK_FILE=${SMTP_STACK_FILE:-docker-stack.smtp.yml}

fail() {
    printf 'Release failed: %s\n' "$*" >&2
    exit 1
}

stack_config() {
    if [ "$SMTP_ENABLED" = 'True' ]; then
        docker stack config --compose-file "$STACK_FILE" --compose-file "$SMTP_STACK_FILE"
    else
        docker stack config --compose-file "$STACK_FILE"
    fi
}

deploy_stack() {
    if [ "$SMTP_ENABLED" = 'True' ]; then
        docker stack deploy --with-registry-auth --compose-file "$STACK_FILE" \
            --compose-file "$SMTP_STACK_FILE" "$STACK_NAME"
    else
        docker stack deploy --with-registry-auth --compose-file "$STACK_FILE" "$STACK_NAME"
    fi
}

matches_target_image() {
    case "$1" in
        "$2"|"$2"@sha256:*) return 0 ;;
        *) return 1 ;;
    esac
}

service_rollout_ready() {
    service=$1
    target_image=$2
    spec_image=$(docker service inspect "$service" --format '{{.Spec.TaskTemplate.ContainerSpec.Image}}') || \
        fail "Could not inspect service '$service'."
    matches_target_image "$spec_image" "$target_image" || \
        fail "$service is configured with '$spec_image', not target '$target_image'."

    update_state=$(docker service inspect "$service" --format '{{if .UpdateStatus}}{{.UpdateStatus.State}}{{end}}') || \
        fail "Could not inspect update state for '$service'."
    case "$update_state" in
        rollback_started|rollback_paused|rollback_completed|paused)
            fail "$service update state is '$update_state'."
            ;;
        ''|completed) ;;
        updating) return 1 ;;
        *) fail "$service reported unexpected update state '$update_state'." ;;
    esac

    tasks=$(docker service ps --filter desired-state=running --no-trunc \
        --format '{{.Image}}|{{.CurrentState}}' "$service") || \
        fail "Could not inspect running tasks for '$service'."
    task_count=0
    while IFS='|' read -r task_image task_state; do
        [ -n "$task_image" ] || continue
        case "$task_state" in
            Running*) ;;
            *) return 1 ;;
        esac
        matches_target_image "$task_image" "$target_image" || \
            fail "$service has a running task with '$task_image', not target '$target_image'."
        task_count=$((task_count + 1))
    done <<EOF
$tasks
EOF
    [ "$task_count" -gt 0 ] || return 1
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

stack_config >/dev/null || fail 'Docker stack configuration is invalid.'

if [ -n "$BACKUP_FILE" ]; then
    [ -s "$BACKUP_FILE" ] || fail "BACKUP_FILE is missing or empty: $BACKUP_FILE"
    printf 'Using existing backup: %s\n' "$BACKUP_FILE"
else
    "$script_dir/backup-postgres.sh"
fi

deploy_stack || \
    fail 'docker stack deploy returned an error.'

BACKEND_IMAGE=${BACKEND_IMAGE:-ghcr.io/maxforcedev/core-pdv-backend}
FRONTEND_IMAGE=${FRONTEND_IMAGE:-ghcr.io/maxforcedev/core-pdv-frontend}
PLATFORM_ADMIN_IMAGE=${PLATFORM_ADMIN_IMAGE:-ghcr.io/maxforcedev/core-pdv-platform-admin}
deadline=$(( $(date +%s) + RELEASE_WAIT_SECONDS ))
while :; do
    all_ready=true
    service_rollout_ready "${STACK_NAME}_backend" "$BACKEND_IMAGE:$RELEASE_TAG" || all_ready=false
    service_rollout_ready "${STACK_NAME}_frontend" "$FRONTEND_IMAGE:$RELEASE_TAG" || all_ready=false
    service_rollout_ready "${STACK_NAME}_platform-admin" "$PLATFORM_ADMIN_IMAGE:$RELEASE_TAG" || all_ready=false
    "$all_ready" && break
    printf 'Waiting for target images and completed Swarm updates.\n'
    [ "$(date +%s)" -lt "$deadline" ] || fail 'Timed out waiting for running Swarm tasks.'
    sleep 5
done

docker stack services "$STACK_NAME"
EXPECTED_RELEASE_TAG="$RELEASE_TAG" "$script_dir/smoke-test.sh" || fail 'Smoke test failed after deployment.'
printf 'Release %s deployed successfully. Image rollback does not roll back PostgreSQL migrations.\n' "$RELEASE_TAG"
