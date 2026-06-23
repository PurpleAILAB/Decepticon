"""Heuristic prompt-injection detector for tool output.

Catches the obvious LLM-jailbreak payload classes that ride on
attacker-controlled bytes (HTTP responses, banner grabs, file contents,
DNS records) before they reach the model. The detector is deliberately
conservative: false positives downgrade trust on a tool output (the
model still sees it inside the ``<UNTRUSTED_TOOL_OUTPUT risk="high">``
envelope, and the operator can override). False negatives let an
adversarial payload through, so the regex set errs heavy.

Patterns drawn from:
  * Public prompt-injection PoC corpora (Anthropic 2024 indirect-injection
    research, OWASP LLM Top 10 LLM01 examples, MITRE ATLAS T0051).
  * The repo's own offensive skill at
    ``packages/decepticon/decepticon/skills/standard/analyst/prompt-injection/SKILL.md``
    - same payloads that work *against* third-party LLMs work *against*
    Decepticon's own agents reading sandboxed output.

This is NOT a perfect classifier. It is a defence-in-depth tripwire
that pairs with the structural quarantine done by
``UntrustedOutputMiddleware``. The structural marker is what the model
actually relies on; the detector annotates risk so the orchestrator and
the operator can prioritise review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class InjectionCategory(StrEnum):
    """Coarse category of a matched injection signal."""

    INSTRUCTION_OVERRIDE = "instruction-override"
    ROLE_HIJACK = "role-hijack"
    TOOL_CALL_HIJACK = "tool-call-hijack"
    EXFIL_MARKDOWN = "exfil-markdown"
    SYSTEM_PROMPT_LEAK = "system-prompt-leak"
    CYPHER_INJECTION = "cypher-injection"
    SHELL_INJECTION_HINT = "shell-injection-hint"
    INVISIBLE_TEXT = "invisible-text"


@dataclass(frozen=True, slots=True)
class InjectionMatch:
    """One matched injection pattern."""

    category: InjectionCategory
    pattern_name: str
    offset: int
    length: int
    excerpt: str


@dataclass(frozen=True, slots=True)
class InjectionVerdict:
    """Aggregated result of a scan."""

    matches: tuple[InjectionMatch, ...] = field(default_factory=tuple)

    @property
    def risk(self) -> str:
        if not self.matches:
            return "low"
        categories = {m.category for m in self.matches}
        if (
            InjectionCategory.TOOL_CALL_HIJACK in categories
            or InjectionCategory.CYPHER_INJECTION in categories
            or InjectionCategory.EXFIL_MARKDOWN in categories
        ):
            return "high"
        if (
            InjectionCategory.INSTRUCTION_OVERRIDE in categories
            or InjectionCategory.ROLE_HIJACK in categories
        ):
            return "high" if len(self.matches) >= 2 else "medium"
        return "medium"

    @property
    def categories(self) -> frozenset[InjectionCategory]:
        return frozenset(m.category for m in self.matches)

    def summary(self) -> str:
        if not self.matches:
            return "no injection patterns detected"
        cats = sorted(c.value for c in self.categories)
        return f"{len(self.matches)} match(es) across {cats}"


_FLAGS = re.IGNORECASE | re.MULTILINE


_PATTERNS: tuple[tuple[InjectionCategory, str, re.Pattern[str]], ...] = (
    (
        InjectionCategory.INSTRUCTION_OVERRIDE,
        "ignore-previous",
        re.compile(
            r"\bignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|preceding|above)\s+"
            r"(?:instructions?|messages?|prompts?|rules?|directives?|context)",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.INSTRUCTION_OVERRIDE,
        "disregard",
        re.compile(
            r"\b(?:disregard|forget|override|set\s+aside|cancel)\s+"
            r"(?:all\s+)?(?:previous|prior|earlier|above|system|safety|alignment)",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.INSTRUCTION_OVERRIDE,
        "new-instructions",
        re.compile(
            r"\b(?:new|updated|revised|corrected|important|critical|urgent)\s+"
            r"(?:instructions?|directives?|orders?|rules?)\s*[:\-]",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.INSTRUCTION_OVERRIDE,
        "system-override-marker",
        re.compile(
            r"\[\s*(?:system|SYSTEM)\s+(?:override|prompt|message|notice)\s*\]",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.ROLE_HIJACK,
        "you-are-now",
        re.compile(
            r"\byou\s+are\s+(?:now|actually|really|in\s+fact)\s+"
            r"(?:a|an|the)\s+\w+",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.ROLE_HIJACK,
        "act-as",
        re.compile(
            r"\b(?:act|behave|roleplay|pretend\s+to\s+be)\s+as\s+"
            r"(?:a|an|the)?\s*[\w\- ]{3,40}\b",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.ROLE_HIJACK,
        "im-start-chatml",
        re.compile(r"<\|im_start\|>\s*(?:system|user|assistant|developer)", _FLAGS),
    ),
    (
        InjectionCategory.ROLE_HIJACK,
        "inst-tags",
        re.compile(r"\[(?:INST|/INST|SYSTEM|/SYSTEM)\]", _FLAGS),
    ),
    (
        InjectionCategory.ROLE_HIJACK,
        "anthropic-tags",
        re.compile(
            r"(?:</?)?(?:human|assistant)(?:></?)?\s*[:\-]|" r"\\n\\nHuman:|\\n\\nAssistant:",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.TOOL_CALL_HIJACK,
        "call-tool",
        re.compile(
            r"\b(?:call|invoke|use|run|execute)\s+"
            r"(?:the\s+)?(?:tool|function|api|endpoint)\s+(?:named\s+)?"
            r"['\"`]?[\w_]+['\"`]?",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.TOOL_CALL_HIJACK,
        "function-call-json",
        re.compile(
            r"\{\s*\"(?:function|tool|name|tool_call)\"\s*:\s*\"",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.TOOL_CALL_HIJACK,
        "send-email-with-secrets",
        re.compile(
            r"\bsend_(?:email|mail|message|webhook|sms)\b",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.EXFIL_MARKDOWN,
        "image-exfil",
        re.compile(
            r"!\[[^\]]*\]\(\s*https?://[^)\s]+\?[^)\s]*"
            r"(?:secret|token|key|password|cred|session|auth|cookie|exfil|q=)",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.EXFIL_MARKDOWN,
        "link-exfil",
        re.compile(
            r"\[[^\]]*\]\(\s*https?://[^)\s]+\?[^)\s]*"
            r"(?:secret|token|key|password|cred|session|auth|cookie|exfil|q=)",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.SYSTEM_PROMPT_LEAK,
        "leak-prompt",
        re.compile(
            r"\b(?:print|output|reveal|repeat|show|display|recite|recall|emit)\s+"
            r"(?:your|the)\s+(?:full\s+)?(?:system|initial|original|previous)\s+"
            r"(?:prompt|instructions?|message)",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.SYSTEM_PROMPT_LEAK,
        "ssh-key-dump",
        re.compile(
            r"-----BEGIN\s+(?:OPENSSH|RSA|DSA|EC)\s+PRIVATE\s+KEY-----",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.CYPHER_INJECTION,
        "apoc-runfile",
        re.compile(r"\bapoc\.(?:cypher\.runFile|load\.|import\.|export\.)", _FLAGS),
    ),
    (
        InjectionCategory.CYPHER_INJECTION,
        "call-apoc",
        re.compile(
            r"\bCALL\s+apoc\.(?:cypher|load|import|export|systemdb|trigger|dbms)",
            _FLAGS,
        ),
    ),
    (
        InjectionCategory.SHELL_INJECTION_HINT,
        "exec-with-curl",
        re.compile(
            r"\b(?:execute|run|invoke|launch)\b.{0,80}?"
            r"(?:curl\s|wget\s|nc\s|bash\s|sh\s|python\s|powershell|cmd\.exe|"
            r"chmod\s|chown\s|/bin/|/sbin/|rm\s+-rf)",
            _FLAGS | re.DOTALL,
        ),
    ),
    (
        InjectionCategory.INVISIBLE_TEXT,
        "zero-width-cluster",
        re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]{3,}"),
    ),
    (
        InjectionCategory.INVISIBLE_TEXT,
        "tag-language-marker",
        re.compile(r"[\U000e0020-\U000e007f]{4,}"),
    ),
)


_EXCERPT_WINDOW = 80


# ── special-token literal neutralization (GHSA-g5f9-3xfg-p9mf) ────────────────
#
# Detection (above) annotates risk; it does NOT change the bytes. That is not
# enough for chat-template special tokens. Under BYOK with a self-hosted /
# OpenAI-compatible backend (vLLM, SGLang, TGI, Ollama, LM Studio, …) whose
# tokenizer preserves special-token IDs, a literal like ``<|im_start|>`` planted
# in attacker-controlled tool output is parsed into a *structural* role-delimiter
# token, forging an operator/system turn the model treats as authoritative and
# bypassing the quarantine envelope. Hosted vendors (OpenAI/Anthropic) strip
# these server-side, but that is vendor-side luck, not an architectural control.
#
# The durable fix is application-layer: defang the literal before it is composed
# into an LLM message. We insert a zero-width space (U+200B) immediately after
# the opening bracket so the exact-match special-token vocab entry can no longer
# fire, while the text stays visually identical for the model and the operator
# audit trail. This mirrors the envelope-marker neutralization already done by
# the two quarantine middlewares.
_ZWSP = "\u200b"

# Token families to cover (advisory §Remediation):
#   ChatML / Qwen / DeepSeek : <|im_start|> <|im_end|> <|endoftext|>
#   Llama-3.x                : <|begin_of_text|> <|end_of_text|>
#                              <|start_header_id|> <|end_header_id|> <|eot_id|>
#   Gemma 2/3                : <start_of_turn> <end_of_turn>
#   Mistral / Mixtral        : [INST] [/INST] <<SYS>> <</SYS>>
#   Unicode bypass           : <｜…｜> (U+FF5C fullwidth vertical bar, DeepSeek)
# The vertical-bar arm accepts BOTH ASCII ``|`` and fullwidth ``｜`` on each end,
# independently, so half/full-width mixing cannot slip past.
_SPECIAL_TOKEN_RE = re.compile(
    r"""
      (?P<vbar> < [|\uff5c] [A-Za-z0-9_]{1,48} [|\uff5c] > )   # <|im_start|>, <|eot_id|>, <｜…｜>
    | (?P<gemma> < /? (?:start|end)_of_turn > )                # <start_of_turn>, <end_of_turn>
    | (?P<inst> \[ /? INST \] )                                # [INST], [/INST]
    | (?P<sys> << /? SYS >> )                                  # <<SYS>>, <</SYS>>
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _defang(match: re.Match[str]) -> str:
    tok = match.group(0)
    # ZWSP right after the leading bracket char breaks the contiguous special-
    # token literal without removing any visible character.
    return f"{tok[0]}{_ZWSP}{tok[1:]}"


def neutralize_special_tokens(text: str) -> str:
    """Defang chat-template special-token literals in untrusted content.

    Returns ``text`` with every recognized role-delimiter special token
    (``<|im_start|>``, ``<|eot_id|>``, ``<start_of_turn>``, ``[INST]``,
    ``<<SYS>>``, and their fullwidth-vertical-bar variants) rendered inert by a
    zero-width-space insertion, so a self-hosted tokenizer can no longer parse
    them into structural role boundaries. No-op for content with no candidate
    bracket. See GHSA-g5f9-3xfg-p9mf.
    """
    if not text or ("<" not in text and "[" not in text):
        return text
    return _SPECIAL_TOKEN_RE.sub(_defang, text)


def detect_injection(text: str) -> InjectionVerdict:
    """Scan ``text`` for prompt-injection signals.

    Returns an ``InjectionVerdict`` carrying every matched pattern and a
    derived risk level. Empty / short text returns ``InjectionVerdict()``
    (risk = "low") without running the regexes.
    """
    if not text or len(text) < 8:
        return InjectionVerdict()
    matches: list[InjectionMatch] = []
    for category, name, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            start = max(0, m.start() - _EXCERPT_WINDOW // 2)
            end = min(len(text), m.end() + _EXCERPT_WINDOW // 2)
            matches.append(
                InjectionMatch(
                    category=category,
                    pattern_name=name,
                    offset=m.start(),
                    length=m.end() - m.start(),
                    excerpt=text[start:end],
                )
            )
    return InjectionVerdict(matches=tuple(matches))
