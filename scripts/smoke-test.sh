#!/bin/sh
set -eu

API_BASE_URL=${API_BASE_URL:-https://api.corepdv.com}
FRONTEND_BASE_URL=${FRONTEND_BASE_URL:-https://corepdv.com}
PLATFORM_ADMIN_BASE_URL=${PLATFORM_ADMIN_BASE_URL:-https://admin.corepdv.com}
EXPECTED_RELEASE_TAG=${EXPECTED_RELEASE_TAG:-}

check_url() {
    label=$1
    url=$2
    printf 'Checking %s: %s\n' "$label" "$url"
    status=$(curl --silent --show-error --location --max-time 15 \
        --output /dev/null --write-out '%{http_code}' "$url")
    if [ "$status" != '200' ]; then
        printf '%s returned HTTP %s, expected 200.\n' "$label" "$status" >&2
        return 1
    fi
}

command -v curl >/dev/null 2>&1 || {
    echo 'curl is required to run the smoke test.' >&2
    exit 1
}

check_url 'backend health' "${API_BASE_URL%/}/health/"

if [ -n "$EXPECTED_RELEASE_TAG" ]; then
    health=$(curl --fail --silent --show-error --location --max-time 15 "${API_BASE_URL%/}/health/") || {
        echo 'Could not read backend health metadata.' >&2
        exit 1
    }
    printf '%s' "$health" | grep -Eq "\"commit\"[[:space:]]*:[[:space:]]*\"$EXPECTED_RELEASE_TAG\"" || {
        printf 'Backend health metadata does not report expected release %s.\n' "$EXPECTED_RELEASE_TAG" >&2
        exit 1
    }
fi

check_url 'frontend root' "${FRONTEND_BASE_URL%/}/"
check_url 'frontend login' "${FRONTEND_BASE_URL%/}/login"
check_url 'platform admin login' "${PLATFORM_ADMIN_BASE_URL%/}/login"

echo 'CORE PDV smoke test passed.'
