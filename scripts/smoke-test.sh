#!/bin/sh
set -eu

API_BASE_URL=${API_BASE_URL:-https://api.corepdv.com}
FRONTEND_BASE_URL=${FRONTEND_BASE_URL:-https://corepdv.com}

check_url() {
    label=$1
    url=$2
    printf 'Checking %s: %s\n' "$label" "$url"
    curl --fail --silent --show-error --location --max-time 15 \
        --output /dev/null "$url"
}

command -v curl >/dev/null 2>&1 || {
    echo 'curl is required to run the smoke test.' >&2
    exit 1
}

check_url 'backend health' "${API_BASE_URL%/}/health/"
check_url 'frontend root' "${FRONTEND_BASE_URL%/}/"
check_url 'frontend login' "${FRONTEND_BASE_URL%/}/login"

echo 'CORE PDV smoke test passed.'
