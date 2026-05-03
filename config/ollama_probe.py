"""Container-side Ollama reachability + tool-capability probe.

Two checks: ``GET /api/tags`` for reachability (with diagnostics for
the localhost trap and the 127.0.0.1-binding case), and
``POST /api/show`` to require the model's ``capabilities`` includes
``tools`` — Decepticon agents always emit tool calls. Best-effort:
never blocks proxy boot, just logs ``[decepticon ollama]`` lines.

Lives next to ``litellm_startup.py`` rather than inside it so the
unit tests can load it via ``importlib`` without dragging in the
startup script's heavy import-time side effects.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

# Ollama's tools capability is reported under ``capabilities`` in
# /api/show responses on Ollama 0.3+ (released 2024-08). Models like
# qwen3-coder, llama3.3, mistral-small3 advertise it; smaller or
# legacy models often don't.
_TOOLS_CAPABILITY = "tools"

_OLLAMA_PROVIDER_PREFIXES = ("ollama_chat", "ollama")

_HttpOpener = Callable[[Any, float], Any]


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of one probe step. ``message=None`` means silent pass."""

    ok: bool
    message: str | None = None


def has_ollama_route(model_ids: Iterable[str]) -> bool:
    """True when at least one requested model uses an Ollama provider."""
    for model_id in model_ids:
        prefix = model_id.split("/", 1)[0].lower()
        if prefix in _OLLAMA_PROVIDER_PREFIXES:
            return True
    return False


def extract_ollama_models(model_ids: Iterable[str]) -> list[str]:
    """Strip the Ollama provider prefix; skip non-Ollama and bare-prefix entries."""
    out: list[str] = []
    for model_id in model_ids:
        prefix, _, tag = model_id.partition("/")
        if prefix.lower() in _OLLAMA_PROVIDER_PREFIXES and tag:
            out.append(tag)
    return out


def _default_opener(url_or_request: Any, timeout: float) -> Any:
    return urllib.request.urlopen(url_or_request, timeout=timeout)


def _classify_transport_error(base_url: str, err: BaseException) -> str:
    """Translate a transport error into a one-line operator hint."""
    text = str(err).lower()
    reason = str(getattr(err, "reason", err)).lower()
    combined = f"{text} {reason}"

    if "refused" in combined:
        return (
            f"Cannot reach {base_url}: connection refused. Ollama is most "
            "likely bound to 127.0.0.1 only — relaunch with "
            "OLLAMA_HOST=0.0.0.0:11434 ollama serve so the litellm "
            "container can reach it."
        )
    dns_signals = (
        "name or service not known",
        "name resolution",
        "nodename nor servname",
        "temporary failure in name resolution",
        "no address associated",
    )
    if any(signal in combined for signal in dns_signals):
        return (
            f"Cannot resolve host for {base_url}. The litellm service in "
            "docker-compose.yml needs "
            "extra_hosts: ['host.docker.internal:host-gateway'] for the "
            "default URL to resolve."
        )
    return f"Cannot reach {base_url}: {err}"


def reachability(
    base_url: str,
    *,
    timeout: float = 2.0,
    opener: _HttpOpener | None = None,
) -> ProbeResult:
    """Probe ``base_url/api/tags``. Pre-flight rejects loopback hosts —
    from inside a container they're never the host running Ollama."""
    if not base_url.strip():
        return ProbeResult(False, "OLLAMA_API_BASE is empty.")

    parts = urlsplit(base_url)
    host = (parts.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return ProbeResult(
            False,
            f"OLLAMA_API_BASE={base_url} points at the container's own "
            "loopback. From inside Docker localhost is the container, "
            "never the host. Use http://host.docker.internal:11434 — "
            "compose's extra_hosts mapping resolves that to the host.",
        )

    open_url = opener or _default_opener
    try:
        with open_url(f"{base_url.rstrip('/')}/api/tags", timeout) as resp:
            status = getattr(resp, "status", 200)
            if status >= 400:
                return ProbeResult(
                    False,
                    f"Ollama responded with HTTP {status} at {base_url}.",
                )
            return ProbeResult(True)
    except urllib.error.HTTPError as err:
        return ProbeResult(
            False,
            f"Ollama responded with HTTP {err.code} at {base_url}: {err.reason}",
        )
    except (urllib.error.URLError, OSError) as err:
        return ProbeResult(False, _classify_transport_error(base_url, err))


def tool_capability(
    base_url: str,
    model: str,
    *,
    timeout: float = 5.0,
    opener: _HttpOpener | None = None,
) -> ProbeResult:
    """Confirm ``model`` advertises ``tools`` via ``/api/show`` capabilities."""
    if not base_url.strip() or not model.strip():
        return ProbeResult(False, "Missing OLLAMA_API_BASE or model name for capability probe.")

    open_url = opener or _default_opener
    payload = json.dumps({"name": model}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/show",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with open_url(request, timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return ProbeResult(
                False,
                f"Ollama model {model!r} is not pulled on this host. Run: ollama pull {model}",
            )
        return ProbeResult(
            False,
            f"Ollama /api/show returned HTTP {err.code} for {model!r}: {err.reason}",
        )
    except (urllib.error.URLError, OSError) as err:
        return ProbeResult(False, _classify_transport_error(base_url, err))

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return ProbeResult(False, f"Ollama /api/show returned non-JSON body for {model!r}.")

    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        # Older Ollama versions (< 0.3) don't ship the capabilities
        # field. We can't determine tool support — emit a soft hint
        # and let the request path surface the real verdict.
        return ProbeResult(
            True,
            f"Ollama at {base_url} did not report capabilities for "
            f"{model!r} (Ollama < 0.3?). Tool calling may still work; "
            "if requests fail, upgrade Ollama and re-pull the model.",
        )

    if _TOOLS_CAPABILITY in capabilities:
        return ProbeResult(True)

    return ProbeResult(
        False,
        f"Model {model!r} does not advertise the 'tools' capability "
        f"(reported: {capabilities}). Decepticon agents always emit "
        "tool calls — pull a tool-capable model instead "
        "(e.g. qwen3-coder, llama3.3, mistral-small3) and set "
        "OLLAMA_MODEL accordingly.",
    )


def probe(
    base_url: str,
    models: Iterable[str],
    *,
    opener: _HttpOpener | None = None,
) -> list[str]:
    """Reachability + per-model tool-capability. Returns operator log
    lines; empty means clean. Reachability failure short-circuits."""
    lines: list[str] = []

    reach = reachability(base_url, opener=opener)
    if reach.message:
        lines.append(reach.message)
    if not reach.ok:
        return lines

    for model in models:
        cap = tool_capability(base_url, model, opener=opener)
        if cap.message:
            lines.append(cap.message)

    return lines


__all__ = [
    "ProbeResult",
    "extract_ollama_models",
    "has_ollama_route",
    "probe",
    "reachability",
    "tool_capability",
]
