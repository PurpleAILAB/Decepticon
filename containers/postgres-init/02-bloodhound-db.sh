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
# Postgres auto-runs files in /docker-entrypoint-initdb.d/ on first
# boot only (when the data volume is empty).  To apply to an existing
# deployment without data loss, run the equivalent commands manually
# inside the postgres container.
#
# ADR: docs/adr/0005-bloodhound-via-bhce-rest-client.md
set -euo pipefail

BHCE_DB_NAME="${BHCE_POSTGRES_DB:-bloodhound}"
BHCE_DB_USER="${BHCE_POSTGRES_USER:-bloodhound}"
BHCE_DB_PASSWORD="${BHCE_POSTGRES_PASSWORD:-bhce-decepticon-local}"

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<-EOSQL
    CREATE ROLE "${BHCE_DB_USER}" WITH LOGIN PASSWORD '${BHCE_DB_PASSWORD}';
    CREATE DATABASE "${BHCE_DB_NAME}" OWNER "${BHCE_DB_USER}";
    GRANT ALL PRIVILEGES ON DATABASE "${BHCE_DB_NAME}" TO "${BHCE_DB_USER}";
EOSQL

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${BHCE_DB_NAME}" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    GRANT ALL ON SCHEMA public TO "${BHCE_DB_USER}";
EOSQL
