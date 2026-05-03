FROM ghcr.io/berriai/litellm:main-v1.82.3-stable.patch.2

# xxhash is required for CCH (Claude Code Hash) request signing
RUN pip install --no-cache-dir xxhash

COPY config/claude_code_handler.py /app/claude_code_handler.py
COPY config/codex_handler.py /app/codex_handler.py
COPY config/gemini_handler.py /app/gemini_handler.py
COPY config/copilot_handler.py /app/copilot_handler.py
COPY config/grok_handler.py /app/grok_handler.py
COPY config/perplexity_handler.py /app/perplexity_handler.py
COPY config/litellm_dynamic_config.py /app/litellm_dynamic_config.py
COPY config/ollama_probe.py /app/ollama_probe.py
COPY config/litellm_startup.py /app/litellm_startup.py
