---
name: container-overview
description: "Container / Kubernetes attack category — pod escape, RBAC abuse, runtime CVE exploitation, socket-mount escape. Routing skill: identify the surface (pod-internal RCE vs API-level vs build-pipeline), then load the matching sub-skill."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "container kubernetes k8s docker podman containerd cri-o pod rbac runtime escape supply chain image registry helm"
  subdomain: cloud-native
  tags: kubernetes, container, cloud-native
  mitre_attack: T1611, T1078.004, T1190
---

# Container / Kubernetes Attack Category

This is a routing skill for cloud-native engagements. Identify the surface, then load the matching sub-skill.

## Sub-skills

| Sub-skill | Covers | When to load |
|---|---|---|
| **k8s-pod-escape** | Privileged container, hostPath escape, hostPID + SYS_PTRACE, runC CVE chains, cgroup release agent | RCE inside a pod, goal is node compromise | `load_skill("/skills/standard/cloud/container/k8s-pod-escape/SKILL.md")` |
| **k8s-rbac-abuse** | `auth can-i --list`, pods/exec on privileged pods, secrets get/list, escalate verb, bind verb, impersonate, nodes/proxy | You have a ServiceAccount token; goal is cluster-admin | `load_skill("/skills/standard/cloud/container/k8s-rbac-abuse/SKILL.md")` |
| **docker-socket-mount** | `/var/run/docker.sock` or containerd socket mounted in → instant host root | CI runners, ArgoCD/Flux, DinD, Jenkins agents | `load_skill("/skills/standard/cloud/container/docker-socket-mount/SKILL.md")` |
| **container-cve** | Catalog of high-impact runtime CVEs — Leaky Vessels, runC 2019-5736, BuildKit chain, CRI-O 2022-0811 | Container runtime version fingerprinted | `load_skill("/skills/standard/cloud/container/container-cve/SKILL.md")` |

## Quick routing

```
Container target identified?
├── You have RCE in a pod / container         → k8s-pod-escape
├── You have a Kubernetes SA token            → k8s-rbac-abuse
├── Socket mounted (`docker.sock`, etc.)      → docker-socket-mount
├── Runtime version is old / vulnerable       → container-cve
└── Unknown / all of above                     → start with k8s-pod-escape's Phase 1
```

## Tooling

| Tool | Use |
|---|---|
| `kubectl` | API-level enumeration and abuse |
| `kube-hunter` | Automated cluster vulnerability scan |
| `kdigger` | In-cluster recon (Quarkslab) |
| `peirates` | Kubernetes-specific privilege escalation |
| `botb` | Container break-out (Brad-Beam et al.) |
| `nsenter` | Cross-namespace process / mount entry |
| `crictl` / `ctr` / `nerdctl` | containerd / CRI direct access |
