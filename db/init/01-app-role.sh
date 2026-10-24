#!/bin/sh
# Runs only when the PostgreSQL data directory is first initialised.
#
# POSTGRES_USER is the bootstrap/break-glass superuser. The application must
# not use it: superusers bypass row-level security even with FORCE. Create a
# dedicated non-superuser role and make it the database/schema owner so the
# FORCE policies in core.0011 apply to normal application traffic.
set -eu

: "${DB_APP_USER:?DB_APP_USER must be set in .env}"
: "${DB_APP_PASSWORD:?DB_APP_PASSWORD must be set in .env}"

psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    -v app_user="$DB_APP_USER" \
    -v app_password="$DB_APP_PASSWORD" \
    -v db_name="$POSTGRES_DB" <<'EOSQL'
CREATE ROLE :"app_user" LOGIN CREATEDB PASSWORD :'app_password';
GRANT ALL PRIVILEGES ON DATABASE :"db_name" TO :"app_user";
ALTER DATABASE :"db_name" OWNER TO :"app_user";
ALTER SCHEMA public OWNER TO :"app_user";
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";
EOSQL
