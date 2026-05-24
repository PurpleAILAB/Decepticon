"""Inline templates for the ``decepticon-sdk plugin new`` scaffolder.

Each plugin ``kind`` maps to a ``ScaffoldTemplate`` that knows the
entry-point group, the stub module body, and the README copy. Inline
templates (no Jinja2) keep the SDK install lean — string ``.format()``
covers everything the scaffolder needs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScaffoldTemplate:
    """One plugin-kind scaffold spec."""

    kind: str
    entry_point_group: str
    module_body: str
    readme_body: str


_TOOL_BODY = '''"""Custom tool contributed to Decepticon."""

from __future__ import annotations

from decepticon_sdk import ToolProtocol


class HelloTool:
    """Minimal ToolProtocol-compliant tool."""

    name = "{plugin_name}"
    description = "Hello-world tool scaffolded by decepticon-sdk."

    def invoke(self, input: object, *, config: object | None = None) -> object:
        del config
        return f"hello from {{self.name}}: {{input}}"


def get_tools(role: str | None = None, **_: object) -> list[ToolProtocol]:
    """Plugin factory called by the framework's tool loader."""
    del role
    return [HelloTool()]
'''


_MIDDLEWARE_BODY = '''"""Custom middleware contributed to Decepticon."""

from __future__ import annotations

from decepticon_sdk import MiddlewareProtocol, MiddlewareSlot


class HelloMiddleware:
    """Minimal MiddlewareProtocol-compliant middleware."""

    name = "{plugin_name}"
    slot: MiddlewareSlot | str = MiddlewareSlot.SKILLS
    priority = 150

    def wrap_model_call(self, state: object, runtime: object, config: object) -> object:
        return state


def get_middleware(role: str | None = None, **_: object) -> list[MiddlewareProtocol]:
    """Plugin factory called by the framework's middleware loader."""
    del role
    return [HelloMiddleware()]
'''


_AGENT_BODY = '''"""Custom agent contributed to Decepticon."""

from __future__ import annotations


def get_agent() -> object:
    """Plugin factory returning a compiled agent (LangGraph CompiledGraph).

    Replace this stub with your real agent construction — see
    ``decepticon.agents.standard.recon.create_recon_agent`` for an
    example of the framework's factory pattern.
    """
    raise NotImplementedError(
        "{plugin_name}: replace get_agent() with your compiled-graph factory"
    )


# LangGraph platform discovers ``graph`` as the module-level attribute.
graph = None
'''


_CALLBACK_BODY = '''"""Custom callback handler contributed to Decepticon."""

from __future__ import annotations


class HelloCallback:
    """Minimal CallbackProtocol-compliant handler."""

    def on_llm_start(self, *args: object, **kwargs: object) -> None:
        return None

    def on_llm_end(self, *args: object, **kwargs: object) -> None:
        return None

    def on_tool_start(self, *args: object, **kwargs: object) -> None:
        return None

    def on_tool_end(self, *args: object, **kwargs: object) -> None:
        return None


def get_callbacks(role: str | None = None, **_: object) -> list[HelloCallback]:
    """Plugin factory called by the framework's callback loader."""
    del role
    return [HelloCallback()]
'''


_SKILL_BODY = '''"""Skill source paths contributed by this plugin.

The framework reads ``/skills/<bundle>/<role>/`` paths via the
``SkillsMiddleware``. Plugins ship skill markdown files as package data
and register the path prefix here.
"""

from __future__ import annotations


def get_skill_sources(role: str | None = None) -> list[str]:
    """Plugin factory called by the framework's skill loader."""
    del role
    return ["/skills/{plugin_name}/"]
'''


_PROMPT_BODY = '''"""Prompt fragments contributed to one or more roles."""

from __future__ import annotations

from decepticon_sdk import PromptContribution


def get_contribution() -> PromptContribution:
    """Plugin factory called by the framework's prompt loader."""
    return PromptContribution(
        fragments={{"recon": "<{plugin_name}>...</{plugin_name}>"}},
        mode="append",
        roles=("recon",),
    )
'''


_README_TEMPLATE = """# {plugin_name}

A Decepticon plugin ({kind}) scaffolded by ``decepticon-sdk plugin new``.

## Build + install

```bash
uv build
pip install dist/*.whl
```

After install, the framework's plugin loader discovers this contribution
via the ``{entry_point_group}`` entry-point group.

## Test

```bash
pip install decepticon-sdk[testing]
pytest
```

Use ``decepticon_sdk.testing.FakeBackend`` / ``FakeLLM`` / ``FakeSandbox``
to write hermetic tests that don't need a live framework.
"""


TEMPLATES: dict[str, ScaffoldTemplate] = {
    "tool": ScaffoldTemplate(
        kind="tool",
        entry_point_group="decepticon.tools",
        module_body=_TOOL_BODY,
        readme_body=_README_TEMPLATE,
    ),
    "middleware": ScaffoldTemplate(
        kind="middleware",
        entry_point_group="decepticon.middleware",
        module_body=_MIDDLEWARE_BODY,
        readme_body=_README_TEMPLATE,
    ),
    "agent": ScaffoldTemplate(
        kind="agent",
        entry_point_group="decepticon.agents",
        module_body=_AGENT_BODY,
        readme_body=_README_TEMPLATE,
    ),
    "callback": ScaffoldTemplate(
        kind="callback",
        entry_point_group="decepticon.callbacks",
        module_body=_CALLBACK_BODY,
        readme_body=_README_TEMPLATE,
    ),
    "skill": ScaffoldTemplate(
        kind="skill",
        entry_point_group="decepticon.skills",
        module_body=_SKILL_BODY,
        readme_body=_README_TEMPLATE,
    ),
    "prompt": ScaffoldTemplate(
        kind="prompt",
        entry_point_group="decepticon.prompts",
        module_body=_PROMPT_BODY,
        readme_body=_README_TEMPLATE,
    ),
}


def pyproject_for(*, plugin_name: str, module_name: str, group: str) -> str:
    """Return a buildable pyproject.toml for the scaffolded plugin."""
    return f"""[project]
name = "{plugin_name}"
version = "0.0.1"
description = "Decepticon plugin scaffolded by decepticon-sdk."
readme = "README.md"
license = {{ text = "Apache-2.0" }}
requires-python = ">=3.13"

dependencies = [
    "decepticon-sdk",
]

[project.entry-points."{group}"]
{module_name} = "{module_name}"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{module_name}"]
"""


__all__ = ["TEMPLATES", "ScaffoldTemplate", "pyproject_for"]
