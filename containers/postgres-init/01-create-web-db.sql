-- Create the decepticon_web database used by the Web dashboard.
--
-- Postgres auto-runs files in /docker-entrypoint-initdb.d/ on first startup
-- (only when data volume is empty). This ensures decepticon_web exists
-- alongside the litellm database created by POSTGRES_DB.
--
-- To apply to an existing deployment without data loss, create the DB
-- manually: `docker exec decepticon-postgres psql -U decepticon -c "CREATE DATABASE decepticon_web;"`

CREATE DATABASE decepticon_web;
GRANT ALL PRIVILEGES ON DATABASE decepticon_web TO decepticon;
