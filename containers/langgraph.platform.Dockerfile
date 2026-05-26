# Optional production runtime: LangGraph Platform (Self-Hosted Lite or
# Self-Hosted Enterprise) layered with the Decepticon framework.
#
# This image is NOT used by the default `docker-compose.yml`. It is the
# build target for the optional `docker-compose.platform.yml` overlay
# (see `docs/runtime/platform-mode.md` for when and why to opt in).
#
# Layered on `langchain/langgraph-api` so the LangGraph Platform server
# (PostgresSaver checkpointer, Redis queue, multi-worker scheduler)
# handles durability and the OSS Decepticon package contributes the
# graphs / agents / skills.
#
# License gate at runtime:
#   - `LANGSMITH_API_KEY`            → Self-Hosted Lite (1M nodes/yr,
#                                       phones home to LangSmith Beacon)
#   - `LANGGRAPH_CLOUD_LICENSE_KEY`  → Self-Hosted Enterprise (paid,
#                                       optional air-gap)
# Neither set → container exits at boot with
# `ValueError: License verification failed` from the base image.
#
# The default OSS `containers/langgraph.Dockerfile` remains the canonical
# image. It runs `langgraph dev` (free, in-memory, no phone-home) and
# stays the supported path for individual contributors, CTF / benchmark
# runs, air-gapped labs, and anyone who hasn't opted in to a LangGraph
# commercial tier.

ARG LANGGRAPH_API_VERSION=3.13
FROM langchain/langgraph-api:${LANGGRAPH_API_VERSION}

WORKDIR /deps/decepticon

# uv for fast, reproducible installs against the base image's
# constraints file (locks transitive versions to what the langgraph-api
# server was tested with — prevents a pip upgrade from sliding
# langgraph-core out from under the server).
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv

# Workspace files. Same shape as the OSS dev image so the source-relative
# graph paths in `langgraph.json` resolve identically.
COPY pyproject.toml langgraph.json README.md uv.lock ./
COPY packages/ packages/

# Stamp the package version from the git tag at build time. Local builds
# use the 0.0.0 sentinel from pyproject; release CI overrides via
# --build-arg VERSION=<tag>.
ARG VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_DECEPTICON=${VERSION} \
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_DECEPTICON_CORE=${VERSION} \
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_DECEPTICON_SDK=${VERSION}

# Install Decepticon (core + framework + sdk) against the base image's
# constraints file. -e installs the three workspace packages editable so
# the on-disk source remains the source of truth — matches the dev-mode
# image's behaviour and keeps `--reload` workflows usable.
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install \
        --system --no-cache-dir \
        -c /api/constraints.txt \
        -e ./packages/decepticon-core \
        -e ./packages/decepticon-sdk \
        -e ./packages/decepticon

# Postgres + Redis checkpointer adapters. The base image ships the
# runtime hooks but expects these packages installed for the production
# checkpointer to bind. Redis adapter is needed for the queue / pubsub
# layer, not for checkpoints.
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install \
        --system --no-cache-dir \
        -c /api/constraints.txt \
        langgraph-checkpoint-postgres

# Process-level plugin bundle baseline. OSS resolves enabled bundles
# from a 4-tier hierarchy (env > .decepticon.toml > pyproject.toml >
# hardcoded ["standard"]); we set the env explicitly so activation
# isn't dependent on whatever CWD the container starts from.
ENV DECEPTICON_PLUGINS=standard

# Mirror the OSS langgraph.json multitask strategy on the platform
# runtime. Override at runtime if a deployment needs different
# semantics.
ENV LANGGRAPH_HTTP='{"multitask_strategy": "interrupt"}'

# LANGSERVE_GRAPHS is composed at boot (see entrypoint below) rather
# than baked into the image so plugin-contributed agents
# (`decepticon.agents` entry-point group) appear automatically once
# their packages are pip-installed — no Dockerfile rebuild required.

# Boot wrapper. Synthesises LANGSERVE_GRAPHS from the OSS graph_registry
# then execs the base image's entrypoint.
COPY containers/langgraph-platform-entrypoint.sh /usr/local/bin/langgraph-platform-entrypoint.sh
RUN chmod +x /usr/local/bin/langgraph-platform-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/langgraph-platform-entrypoint.sh"]
