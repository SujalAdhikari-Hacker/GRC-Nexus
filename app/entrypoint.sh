#!/bin/sh
set -e

echo "[entrypoint] Waiting for PostgreSQL to accept connections..."

until python - <<'PY'
import os
import sys
import psycopg2

user = os.environ.get("DB_APP_USER")
password = os.environ.get("DB_APP_PASSWORD")
if not user or not password:
    print("DB_APP_USER/DB_APP_PASSWORD are not set", file=sys.stderr)
    sys.exit(1)

try:
    psycopg2.connect(
        dbname=os.environ.get("POSTGRES_DB", "grc_db"),
        user=user,
        password=password,
        host=os.environ.get("POSTGRES_HOST", "db"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
    ).close()
except Exception:
    sys.exit(1)
sys.exit(0)
PY
do
    echo "[entrypoint]   database not ready yet - retrying in 2s"
    sleep 2
done

echo "[entrypoint] Database is ready. Applying migrations..."
python manage.py migrate --noinput

# Always rebuild STATIC_ROOT from scratch. collectstatic skips files whose
# mtime is not newer than the collected copy, which silently serves stale CSS/JS
# after a bind-mounted code change. STATIC_ROOT is a build artifact, so clearing
# it is safe and guarantees what is served matches the source tree.
echo "[entrypoint] Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "[entrypoint] Starting: $*"
exec "$@"
