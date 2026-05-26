-- LangGraph Platform checkpoint database.
--
-- Created only when the optional docker-compose.platform.yml overlay is
-- active (it mounts this script into /docker-entrypoint-initdb.d/). Runs
-- after 01-create-decepticon-web.sql on first volume init only - existing
-- deployments must create the database manually if they switch in:
--     docker compose exec postgres \
--         psql -U decepticon -c 'CREATE DATABASE langgraph_cp;'
--
-- The LangGraph Platform server (langchain/langgraph-api) creates its
-- own schema (checkpoints, checkpoint_blobs, checkpoint_writes, ...) on
-- first boot, so we only need the empty database here.

SELECT 'CREATE DATABASE langgraph_cp'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langgraph_cp')\gexec
