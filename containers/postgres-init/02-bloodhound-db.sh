#!/usr/bin/env bash
# Bootstrap the BHCE (BloodHound Community Edition) Postgres state.
#
# Why this exists
# ---------------
# The BHCE API container points at `postgres:5432` with
#   user=bloodhound password=$BHCE_POSTGRES_PASSWORD dbname=bloodhound
# and runs its own `goose` migrations on first boot.  The migrations
# include `CREATE EXTENSION IF NOT EXISTS pg_trgm;` (BHCE
# `cmd/api/src/database/migration/migrations/00000000000001_init.sql`,
# v9.2.2), which requires the connecting role to either own the
# extension or be a superuser.  We pre-create the role, the DB, and
# the extension here as the postgres superuser so BHCE's migration
# user can remain narrowly scoped.
#
# Postgres auto-runs files in /docker-entrypoint-initdb.d/ on first boot
# only, but Decepticon v1.1.7 also ships to users with an existing
# postgres_data volume.  Keep this script idempotent and run it both from
# initdb and from the compose `bhce-postgres-init` sidecar so upgrades gain
# the BloodHound role/database without deleting user data.
#
# ADR: docs/adr/0005-bloodhound-via-bhce-rest-client.md
set -euo pipefail

BHCE_DB_NAME="${BHCE_POSTGRES_DB:-bloodhound}"
BHCE_DB_USER="${BHCE_POSTGRES_USER:-bloodhound}"
BHCE_DB_PASSWORD="${BHCE_POSTGRES_PASSWORD:-bhce-decepticon-local}"

psql -v ON_ERROR_STOP=1 \
    --username "${POSTGRES_USER}" \
    --dbname "${POSTGRES_DB}" \
    -v bhce_db_name="${BHCE_DB_NAME}" \
    -v bhce_db_user="${BHCE_DB_USER}" \
    -v bhce_db_password="${BHCE_DB_PASSWORD}" <<-'EOSQL'
    SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'bhce_db_user', :'bhce_db_password')
    WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'bhce_db_user')
    \gexec

    SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'bhce_db_user', :'bhce_db_password')
    \gexec

    SELECT format('CREATE DATABASE %I OWNER %I', :'bhce_db_name', :'bhce_db_user')
    WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'bhce_db_name')
    \gexec

    SELECT format('ALTER DATABASE %I OWNER TO %I', :'bhce_db_name', :'bhce_db_user')
    \gexec

    SELECT format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', :'bhce_db_name', :'bhce_db_user')
    \gexec
EOSQL

psql -v ON_ERROR_STOP=1 \
    --username "${POSTGRES_USER}" \
    --dbname "${BHCE_DB_NAME}" \
    -v bhce_db_user="${BHCE_DB_USER}" <<-'EOSQL'
    CREATE EXTENSION IF NOT EXISTS pg_trgm;

    SELECT format('GRANT ALL ON SCHEMA public TO %I', :'bhce_db_user')
    \gexec

    SELECT format('GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO %I', :'bhce_db_user')
    \gexec

    SELECT format('GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO %I', :'bhce_db_user')
    \gexec
EOSQL
