"""Language / locale registry and operator-language policy.

Holds the country-code → ISO 639-1 alias map, the ISO 639-1 → language-name
map, and :func:`build_language_policy`, which renders the ``<LANGUAGE_POLICY>``
block injected into every agent prompt. Kept separate from the prompt-assembly
engine (:mod:`decepticon.agents.prompts.builder`) so the assembly engine can
depend on this data without the reverse — one-directional, no cycle.
"""

from __future__ import annotations

# Country-code aliases → ISO 639-1 language codes. Users naturally type
# "dk" (Denmark), "se" (Sweden), "jp" (Japan), "cn" (China) instead of
# the ISO 639-1 "da", "sv", "ja", "zh". Shared between the env-based
# prompt-time path (CLI) and the runtime config path (multi-tenant web).
_COUNTRY_TO_LANG = {
    "dk": "da",
    "se": "sv",
    "jp": "ja",
    "cn": "zh",
    "br": "pt-br",
    "tw": "zh-tw",
}

_LANG_NAMES = {
    # East Asian
    "ko": "Korean",
    "ja": "Japanese",
    "zh": "Chinese",
    "zh-cn": "Simplified Chinese",
    "zh-tw": "Traditional Chinese",
    # Nordic / Scandinavian
    "no": "Norwegian",
    "nb": "Norwegian Bokmål",
    "nn": "Norwegian Nynorsk",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "is": "Icelandic",
    # Western European
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "pt": "Portuguese",
    "pt-br": "Brazilian Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "ca": "Catalan",
    # Eastern European / Slavic
    "ru": "Russian",
    "pl": "Polish",
    "cs": "Czech",
    "sk": "Slovak",
    "uk": "Ukrainian",
    "bg": "Bulgarian",
    "hr": "Croatian",
    "sr": "Serbian",
    "sl": "Slovenian",
    "ro": "Romanian",
    # South / Southeast Asian
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "ms": "Malay",
    "tl": "Filipino",
    # Middle Eastern
    "ar": "Arabic",
    "fa": "Persian",
    "he": "Hebrew",
    "tr": "Turkish",
    # Other
    "el": "Greek",
    "hu": "Hungarian",
    "et": "Estonian",
    "lv": "Latvian",
    "lt": "Lithuanian",
    "sw": "Swahili",
    "af": "Afrikaans",
}


def build_language_policy(language: str) -> str | None:
    """Build the LANGUAGE_POLICY block for a given ISO 639-1 code.

    Returns the policy text, or None when the code is empty / English (no
    override needed — the prompt's default language.md fragment applies).
    Shared between the prompt builder (env-based) and the
    EngagementContextMiddleware runtime path (config-based).
    """
    lang = (language or "").strip()
    if not lang or lang.lower() == "en":
        return None

    resolved = _COUNTRY_TO_LANG.get(lang.lower(), lang.lower())

    if resolved == "wenyan":
        return (
            "<LANGUAGE_POLICY>\n"
            "You MUST respond in 文言文 (wenyan-full) — Classical Chinese literary\n"
            "prose with English technical terms preserved verbatim.\n"
            "\n"
            "Rules:\n"
            "- Maximum classical terseness. 80-90% character reduction vs normal prose.\n"
            "- Classical sentence patterns: verbs precede objects, subjects often omitted,\n"
            "  use classical particles (之/乃/為/其/則/而/以/故).\n"
            "- ALL technical terms stay in English exactly as-is: function names, API names,\n"
            "  code symbols, error strings, file paths, command flags, tool names, config\n"
            "  keys, variable names. NEVER transliterate these into Chinese.\n"
            "- Code blocks, tool calls, JSON, structured payloads: completely unchanged.\n"
            "- Mix freely: Classical Chinese for explanation, English for technical nouns.\n"
            "\n"
            "Examples:\n"
            "- '物出新參照，致重繪。useMemo Wrap之。'\n"
            "- '池reuse open connection。不每req新開。skip handshake overhead。'\n"
            "- 'Bug在auth middleware。Token expiry check用 `<` 非 `<=`。Fix:'\n"
            "\n"
            "Drop caveman for: security warnings, irreversible action confirmations,\n"
            "cases where compression creates technical ambiguity. Resume after.\n"
            "</LANGUAGE_POLICY>"
        )

    lang_name = _LANG_NAMES.get(resolved, lang)
    return (
        "<LANGUAGE_POLICY>\n"
        f"You MUST respond in {lang_name} for all operator-facing prose.\n"
        f"\n"
        f"- All operator-facing prose (interview questions, menu options, explanations,\n"
        f"  summaries, status updates, error messages) MUST be in {lang_name}.\n"
        f"- Tool calls, tool arguments, and structured payloads (JSON fields, code\n"
        f"  blocks, file paths, command output) stay in their original technical\n"
        f"  form — do not translate identifiers, file names, command flags, or\n"
        f"  schema field names.\n"
        f"</LANGUAGE_POLICY>"
    )
