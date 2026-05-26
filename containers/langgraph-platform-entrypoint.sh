#!/bin/sh
# LangGraph Platform boot wrapper for the optional platform-mode image
# (see containers/langgraph.platform.Dockerfile). Synthesises
# LANGSERVE_GRAPHS from the OSS graph_registry, then execs the base
# image's entrypoint.
#
# LANGSERVE_GRAPHS is composed at boot so plugin-contributed agents
# (decepticon.agents entry-point group) appear automatically once their
# packages are pip-installed - no Dockerfile rebuild required.
#
# An explicit LANGSERVE_GRAPHS already in the environment (e.g. a Cloud
# Run revision narrowing the exposed graph set) wins; this wrapper only
# fills the gap when the env is empty.

set -e

# OSS graph_registry emits file-form graph paths like
# `./packages/decepticon/decepticon/agents/standard/decepticon.py:graph`
# that resolve relative to CWD. The packages are installed editable, so
# the source tree on disk is the resolution root - chdir there before
# booting.
cd /deps/decepticon

if [ -z "${LANGSERVE_GRAPHS-}" ]; then
  LANGSERVE_GRAPHS="$(python -m decepticon.graph_registry)"
  export LANGSERVE_GRAPHS
fi

exec /storage/entrypoint.sh "$@"
