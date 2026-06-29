# Decepticon Helm Chart

Kubernetes deployment for the Decepticon offensive security platform.

## Components

| Service | Description | Default Port |
|---------|-------------|--------------|
| LiteLLM | LLM API gateway & model router | 4000 |
| LangGraph | Agent orchestration API | 2024 |
| Sandbox | Isolated red-team tool runner | 9999 |
| Neo4j | Attack-chain knowledge graph | 7687 (bolt) |

## Prerequisites

- Kubernetes 1.27+
- Helm 3.12+
- External PostgreSQL instance (or deploy one separately)
- Container images pushed to your registry

## Install

```bash
helm install decepticon ./deploy/helm/decepticon \
  --namespace decepticon --create-namespace \
  --set postgres.host=my-postgres.example.com \
  --set postgres.password=changeme \
  --set neo4j.auth.password=changeme
```

## Configuration

See `values.yaml` for the full parameter reference. Key overrides:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.imageRegistry` | Container registry | `ghcr.io/purpleailab` |
| `global.imageTag` | Image tag for all services | `stable` |
| `litellm.replicaCount` | LiteLLM replicas | `1` |
| `langgraph.replicaCount` | LangGraph replicas | `1` |
| `neo4j.enabled` | Deploy Neo4j StatefulSet | `true` |
| `neo4j.persistence.size` | Neo4j PVC size | `10Gi` |
| `networkPolicy.enabled` | Enforce network policies | `true` |

## Network Policies

When enabled, the chart enforces sandbox isolation:

- Sandbox pods accept ingress **only** from LangGraph.
- Sandbox egress is limited to Neo4j (bolt) and DNS.
- LiteLLM accepts ingress **only** from LangGraph.

## Uninstall

```bash
helm uninstall decepticon -n decepticon
```
