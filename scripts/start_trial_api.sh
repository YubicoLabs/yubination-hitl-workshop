#!/bin/sh
set -eu

max_attempts="${PRELOOP_TRIAL_DB_INIT_ATTEMPTS:-30}"
attempt=1

while [ "$attempt" -le "$max_attempts" ]; do
    if python scripts/init_db.py --force; then
        exec python -m preloop.server
    fi

    echo "Database initialization failed; retrying (${attempt}/${max_attempts})..."
    attempt=$((attempt + 1))
    sleep 3
done

echo "Database initialization did not complete after ${max_attempts} attempts."
exit 1
