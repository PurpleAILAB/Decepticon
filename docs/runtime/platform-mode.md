# Optional: LangGraph Platform mode

Decepticon ships with two runtime images for the orchestrator:

| Image | Backed by | Default? | Use when |
|---|---|---|---|
| `containers/langgraph.Dockerfile` | `langgraph dev` (in-memory CLI) | **Yes** | Individual contributors, CTF / benchmark runs, air-gapped labs, anyone who has not opted in to a LangGraph commercial tier |
| `containers/langgraph.platform.Dockerfile` | `langchain/langgraph-api` | No | Production-style deployments that want durable thread state, multi-worker scheduling, and the platform server's queue / pubsub |

The default `docker-compose.yml` uses the first. **This document explains
when and how to opt in to the second.** Both surfaces register the same
`LANGSERVE_GRAPHS` set, run the same agents, and accept the same plugin
contributions — the difference is the host runtime.

## Why you might want this

`langgraph dev` is great for development. The trade-offs become visible
in production:

- **Thread state is in-memory.** `docker compose restart langgraph`
  wipes every active engagement's chat history. The agent recovers
  because it re-reads `/workspace/` on resume (Ralph-loop pattern), but
  the conversation feels reset.
- **One worker.** The dev server is single-process; horizontal scaling
  is not possible.
- **No queue.** Long-running graph executions block the request that
  triggered them. SSE clients survive disconnect, but a fresh client
  cannot resume mid-run.

The LangGraph Platform server addresses all three:

- **PostgresSaver checkpointer.** Threads survive container restart,
  postgres restart, host reboot. Verified by LangChain: a thread
  created via `POST /threads`, then `docker compose restart langgraph`,
  then `GET /threads/<id>` returns the same thread with status
  preserved.
- **Multi-worker.** Replace `langgraph` with N replicas behind a
  shared Postgres / Redis pair.
- **Redis-backed queue.** Disconnects, retries, fan-out all become
  durable instead of best-effort.

The cost is the LangGraph Platform license model — see "License gate"
below.

## License gate

`langchain/langgraph-api` performs a **load-bearing license check at
boot**:

| Env set | Tier | Limit | Phone-home | Cost |
|---|---|---|---|---|
| `LANGSMITH_API_KEY` | Self-Hosted Lite | **1,000,000 node executions / year** | `beacon.langchain.com` on startup | Free with LangSmith account |
| `LANGGRAPH_CLOUD_LICENSE_KEY` | Self-Hosted Enterprise | Unlimited; air-gap configurable | Configurable | [Contact LangChain sales](https://www.langchain.com/pricing) |
| Neither | — | — | — | Container exits at boot with `ValueError: License verification failed` |

**Decepticon engagements consume thousands of node executions each**
(deep chain: recon → exploit → postexploit → analyst). On the Lite tier,
100 engagements can exceed the entire annual budget. Monitor usage at
`https://smith.langchain.com/o/<your-org>/settings/usage` and plan the
upgrade to Enterprise if you intend to run continuously.

## How to opt in

1. **Get a LangSmith API key.** Sign up at
   [smith.langchain.com](https://smith.langchain.com), navigate to
   Settings → API keys, create one. (Or buy an Enterprise license and
   get `LANGGRAPH_CLOUD_LICENSE_KEY` from your account team.)

2. **Set the env var.** Add to `.env`:

   ```bash
   LANGSMITH_API_KEY=lsv2_pt_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx_xxxxxxxxxx
   ```

3. **Bring up the overlay.** From the repo root:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.platform.yml up --build
   ```

   First boot creates the `langgraph_cp` Postgres database from
   `containers/postgres-init/02-create-langgraph-cp.sql`. **If you have
   an existing `postgres_data` volume**, that init script does not run
   (Postgres only runs initdb scripts on empty volumes); create the
   database manually:

   ```bash
   docker compose exec postgres \
       psql -U decepticon -c 'CREATE DATABASE langgraph_cp;'
   ```

4. **Verify.** Threads should now survive a restart:

   ```bash
   # Start an engagement, then:
   docker compose -f docker-compose.yml -f docker-compose.platform.yml restart langgraph
   # Reopen the engagement in the web dashboard - chat history is intact.
   ```

## How to opt back out

```bash
docker compose -f docker-compose.yml -f docker-compose.platform.yml down
docker compose up    # default langgraph dev runtime
```

The default runtime ignores the `langgraph_cp` database and the
`langgraph-redis` service. They sit idle until the next overlay run.
Delete them with `docker volume rm postgres_data` (destructive: wipes
all Postgres data) or with `docker compose exec postgres psql -U
decepticon -c 'DROP DATABASE langgraph_cp;'` (surgical) if you want to
reclaim the space.

## What this overlay does NOT do

- **Run agents in production.** The platform runtime improves durability
  and scheduling. It does not change the agent code, the safety gate,
  or the engagement model. Production deployment also wants a hardened
  reverse proxy, TLS termination, observability, etc. — out of scope
  here.
- **Replace the OSS image as the default.** `langgraph dev` remains
  the canonical OSS path. We are not opinionated about which runtime
  you choose; we just make both available.
- **Enable multi-tenant gating.** A single Decepticon stack is still
  single-tenant by design. Multi-tenant SaaS isolation is a layer on
  top — see PurpleAILAB's hosted Decepticon Cloud for the productised
  version.

## Reference

- [LangGraph Platform deployment options](https://github.com/langchain-ai/langgraph/blob/main/docs/docs/how-tos/deploy-self-hosted.md)
- [LangSmith pricing](https://www.langchain.com/pricing)
- `containers/langgraph.platform.Dockerfile` — the platform-mode image build.
- `docker-compose.platform.yml` — the overlay itself.
