#!/usr/bin/env bash
set -euo pipefail

# Deploy the investment dashboard on y540.
# Run from the checkout on y540 after CI has passed.

REPO_DIR="${INVEST_REPO_DIR:-$HOME/repos/invest-engine}"
cd "$REPO_DIR"

before=$(git rev-parse HEAD)
git pull --ff-only origin main
after=$(git rev-parse HEAD)

if [[ -n "${EXPECTED_DEPLOY_SHA:-}" && "$after" != "$EXPECTED_DEPLOY_SHA" ]]; then
    echo "Remote checkout is $after, expected $EXPECTED_DEPLOY_SHA" >&2
    exit 1
fi

echo "Deploying invest from $before to $after"

# Keep the remote environment aligned with the lockfile before restarting the
# long-running user service.
uv sync --frozen
uv run python scripts/dashboard.py
systemctl --user restart invest-dashboard.service

for _ in $(seq 1 15); do
    if curl --fail --silent http://127.0.0.1:8050/api/health >/dev/null; then
        echo "Invest dashboard is healthy at commit $after"
        exit 0
    fi
    sleep 2
done

echo "Dashboard health check failed at commit $after" >&2
systemctl --user status invest-dashboard.service --no-pager >&2 || true
exit 1
