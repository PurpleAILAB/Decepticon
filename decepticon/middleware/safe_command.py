"""SafeCommandMiddleware — blocks bash commands that destroy the sandbox session.

Commands like `pkill bash` or `killall tmux` kill the tmux server process inside
the Docker container, causing an unrecoverable "no server running" error.  This
middleware intercepts `bash` tool calls *before* execution and returns an error
ToolMessage with a safe alternative suggestion.

Implemented as an AgentMiddleware so it applies uniformly to every agent that
has it in its middleware stack — no per-tool-function patching needed.
"""

from __future__ import annotations

import shlex
from collections.abc import Iterator
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

# ─── Shell-aware dangerous-command detection ──────────────────────────────
#
# The previous implementation was a regex denylist applied to the raw
# command string. That ran into two classes of bug:
#
#   1. False positives inside quoted strings — ``echo 'pkill bash'`` was
#      blocked even though the echoing process never kills bash. This
#      broke scripted report generation and anything that needs to log or
#      print the literal string.
#   2. Trivial bypass — ``foo; pkill bash`` was matched, but so was
#      ``pkill${IFS}bash`` via the same regex if ``\b`` happened to fit.
#
# We now tokenize the command through ``shlex`` so quoted content is
# preserved as a single atom, then walk the token stream splitting on
# shell statement separators (``;``, ``|``, ``||``, ``&``, ``&&``,
# newline). Each sub-statement is checked as an argv-style list of
# tokens — ``argv[0]`` must actually be the dangerous binary name, not
# merely appear inside a quoted argument.
#
# This is still defense-in-depth, not a real sandbox. shell-substitution
# (``$(...)``, backticks) and env-indirection (``${CMD}``) are not
# expanded. The goal is ergonomics for benign commands, not cryptographic
# guarantees against a motivated attacker.


# Shell statement separators. When the lexer emits any of these as a
# standalone token we treat the preceding argv list as a complete command
# and start a new one.
_STATEMENT_SEPARATORS: frozenset[str] = frozenset({";", "&", "&&", "|", "||", "\n"})

# Binaries that kill the tmux session when targeted at bash/tmux.
_PKILL_LIKE: frozenset[str] = frozenset({"pkill", "killall"})

# docker subcommands that operate on the host daemon from inside the
# sandbox (blocked outright because the agent is already *in* the sandbox).
_DOCKER_BLOCKED_SUBCOMMANDS: frozenset[str] = frozenset({"exec", "run", "cp", "build", "compose"})


def _iter_commands(command: str) -> Iterator[list[str]]:
    """Yield argv-style token lists for each statement in ``command``.

    Quoted strings are preserved as a single token. Shell statement
    separators (``;``, ``|``, ``||``, ``&``, ``&&``, ``\\n``) terminate a
    statement. Unbalanced quotes or other lexer errors cause the
    function to fall back to best-effort whitespace splitting so a
    malformed command doesn't bypass the check by raising.
    """
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        argv: list[str] = []
        while True:
            tok = lex.get_token()
            if tok is None or tok == "":
                break
            if tok in _STATEMENT_SEPARATORS:
                if argv:
                    yield argv
                    argv = []
                continue
            argv.append(tok)
        if argv:
            yield argv
    except ValueError:
        # Unbalanced quotes → degrade to whitespace-split rather than
        # returning no commands (which would fail-open).
        naive = command.split()
        if naive:
            yield naive


def _strip_prefix(argv: list[str]) -> list[str]:
    """Skip ``sudo`` / ``env VAR=val`` prefixes so the real head is checked."""
    i = 0
    while i < len(argv):
        head = argv[i]
        if head == "sudo":
            i += 1
            continue
        if head == "env":
            i += 1
            while i < len(argv) and "=" in argv[i] and not argv[i].startswith("-"):
                i += 1
            continue
        break
    return argv[i:]


def _check_argv(argv: list[str]) -> str | None:
    """Return a block reason for ``argv`` if it is dangerous, else None."""
    argv = _strip_prefix(argv)
    if not argv:
        return None
    head = argv[0]
    rest = argv[1:]

    # ── pkill/killall bash or tmux ────────────────────────────────────
    if head in _PKILL_LIKE:
        targets = {t for t in rest if not t.startswith("-")}
        if "bash" in targets:
            return (
                f"{head} bash kills the tmux session itself. "
                "Use `kill <specific-pid>` or `pkill -f '<your-script-name>'` instead."
            )
        if "tmux" in targets:
            return (
                f"{head} tmux destroys the sandbox session. "
                "Use `tmux kill-session -t <name>` for a specific session."
            )
        return None

    # ── kill -9 -1 / kill -9 0 (mass-signal the session) ─────────────
    if head == "kill":
        if "-9" in rest and any(t in ("-1", "0") for t in rest):
            return (
                "kill -9 -1/0 sends SIGKILL to all processes, destroying "
                "the session. Use `kill <specific-pid>` instead."
            )
        return None

    # ── docker CLI from inside the sandbox ───────────────────────────
    if head == "docker":
        if rest and rest[0] in _DOCKER_BLOCKED_SUBCOMMANDS:
            return (
                "Docker CLI commands are blocked — you are INSIDE the "
                "sandbox container. All commands execute directly in the "
                "Kali Linux environment."
            )
        return None

    # ── cat /proc/1/{environ,cmdline,maps} ───────────────────────────
    if head == "cat":
        for tok in rest:
            if tok in (
                "/proc/1/environ",
                "/proc/1/cmdline",
                "/proc/1/maps",
            ):
                return (
                    "Reading /proc/1/ exposes host process information. "
                    "Use /proc/self/ for current process info instead."
                )
        return None

    # ── nsenter (namespace escape) ───────────────────────────────────
    if head == "nsenter":
        return "nsenter can escape container namespaces. This is blocked for sandbox safety."

    # ── mount proc / sys / sysfs ─────────────────────────────────────
    if head == "mount":
        # ``mount -t {proc,sys,sysfs} ...``
        if "-t" in rest:
            try:
                t_value = rest[rest.index("-t") + 1]
            except IndexError:
                t_value = ""
            if t_value in ("proc", "sys", "sysfs"):
                return "Mounting /proc or /sys filesystems is blocked for sandbox safety."
        # Catch-all: any mount with proc/sys/sysfs as a positional token.
        if any(t in ("proc", "sys", "sysfs") for t in rest):
            return "Mounting /proc or /sys filesystems is blocked for sandbox safety."
        return None

    # ── eval / bash -c / interpreter -c (bypass vectors) ────────────
    if head == "eval":
        return (
            "eval is blocked — it can execute arbitrary commands that "
            "bypass safety checks. Run the command directly instead."
        )
    if head in ("bash", "sh", "zsh", "dash") and "-c" in rest:
        return (
            f"{head} -c is blocked — the inner command bypasses safety "
            "checks. Run the command directly instead."
        )
    if head in ("python", "python3", "perl", "ruby", "node") and "-c" in rest:
        return f"{head} -c is blocked — interpreter execution may bypass command safety checks."

    # ── firewall modification (iptables family) ──────────────────────
    if head in ("iptables", "ip6tables", "nft", "nftables"):
        return (
            "Firewall rule modification is blocked — may violate Rules "
            "of Engagement. Document the finding and request RoE "
            "amendment if needed."
        )

    # ── routing table modification ───────────────────────────────────
    if head == "ip" and rest and rest[0] in ("route", "rule"):
        if any(op in rest for op in ("add", "del", "flush")):
            return (
                "Routing table modification is blocked — may violate "
                "Rules of Engagement. Use the network as-is or document "
                "the limitation."
            )

    return None


def _first_dangerous(command: str) -> str | None:
    """Return the first block reason across every statement in ``command``."""
    for argv in _iter_commands(command):
        reason = _check_argv(argv)
        if reason is not None:
            return reason
    return None


class SafeCommandMiddleware(AgentMiddleware):
    """Block bash tool calls that would destroy the sandbox tmux session.

    Sits in the middleware stack and intercepts ``bash`` tool calls before
    they reach the actual tool.  If the command matches a dangerous pattern
    (e.g. ``pkill bash``), returns a ``ToolMessage(status="error")`` with a
    safe alternative — the tool is never executed.

    Usage::

        middleware = [
            SafeCommandMiddleware(),   # ← early in the stack
            SkillsMiddleware(...),
            FilesystemMiddleware(...),
            ...
        ]
    """

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """Intercept bash calls and block session-destroying commands."""
        tool_name = request.tool_call["name"]

        if tool_name == "bash":
            args = request.tool_call.get("args", {})
            command = args.get("command", "")
            is_input = args.get("is_input", False)

            # Only check new commands, not interactive input to a running process
            if command and not is_input:
                reason = _first_dangerous(command)
                if reason is not None:
                    return ToolMessage(
                        content=f"[BLOCKED] {reason}",
                        tool_call_id=request.tool_call["id"],
                        name=tool_name,
                        status="error",
                    )

        return await handler(request)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        """Synchronous fallback for non-async agent runtimes."""
        tool_name = request.tool_call["name"]

        if tool_name == "bash":
            args = request.tool_call.get("args", {})
            command = args.get("command", "")
            is_input = args.get("is_input", False)

            if command and not is_input:
                reason = _first_dangerous(command)
                if reason is not None:
                    return ToolMessage(
                        content=f"[BLOCKED] {reason}",
                        tool_call_id=request.tool_call["id"],
                        name=tool_name,
                        status="error",
                    )

        return handler(request)
