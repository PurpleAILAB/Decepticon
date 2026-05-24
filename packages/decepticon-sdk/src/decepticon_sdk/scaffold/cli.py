"""``decepticon-sdk plugin new`` — typer-based scaffold CLI.

Generates a buildable plugin package for one of the six supported
plugin kinds. The output directory contains ``pyproject.toml``,
``README.md``, and ``src/<module>/__init__.py`` wired to the matching
``decepticon.<group>`` entry-point group.

Sample run::

    decepticon-sdk plugin new --kind=middleware --name=my-plugin --path=./my-plugin
    cd my-plugin
    uv build
    pip install dist/*.whl
"""

from __future__ import annotations

from pathlib import Path

import typer

from decepticon_sdk.scaffold.templates import TEMPLATES, pyproject_for

app = typer.Typer(
    name="decepticon-sdk",
    help="Decepticon plugin author SDK — scaffold + utilities.",
    no_args_is_help=True,
)

plugin_app = typer.Typer(name="plugin", help="Plugin scaffolding subcommands.")
app.add_typer(plugin_app)


def _normalize_module_name(plugin_name: str) -> str:
    """Convert ``my-plugin`` (PyPI-style) into ``my_plugin`` (module-style)."""
    return plugin_name.replace("-", "_")


@plugin_app.command("new")
def plugin_new(
    kind: str = typer.Option(
        ...,
        "--kind",
        help=f"Plugin kind. One of: {', '.join(sorted(TEMPLATES))}",
    ),
    name: str = typer.Option(
        ...,
        "--name",
        help="Plugin name (PyPI-style, e.g. 'my-decepticon-plugin').",
    ),
    path: Path = typer.Option(
        ...,
        "--path",
        help="Target directory. Created if absent.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing files in --path.",
    ),
) -> None:
    """Scaffold a new Decepticon plugin package."""
    if kind not in TEMPLATES:
        raise typer.BadParameter(f"unknown --kind={kind!r}; expected one of {sorted(TEMPLATES)}")
    template = TEMPLATES[kind]
    module_name = _normalize_module_name(name)

    target = path.resolve()
    src_dir = target / "src" / module_name
    pyproject_path = target / "pyproject.toml"
    readme_path = target / "README.md"
    init_path = src_dir / "__init__.py"

    if not force and pyproject_path.exists():
        raise typer.BadParameter(f"{pyproject_path} already exists; pass --force to overwrite")

    src_dir.mkdir(parents=True, exist_ok=True)

    pyproject_path.write_text(
        pyproject_for(
            plugin_name=name,
            module_name=module_name,
            group=template.entry_point_group,
        ),
        encoding="utf-8",
    )
    readme_path.write_text(
        template.readme_body.format(
            plugin_name=name,
            kind=kind,
            entry_point_group=template.entry_point_group,
        ),
        encoding="utf-8",
    )
    init_path.write_text(
        template.module_body.format(plugin_name=module_name),
        encoding="utf-8",
    )

    typer.echo(f"created decepticon plugin '{name}' (kind={kind}) at {target}")
    typer.echo(f"  pyproject:    {pyproject_path.relative_to(target.parent)}")
    typer.echo(f"  module:       {init_path.relative_to(target.parent)}")
    typer.echo(f"  entry-point:  {template.entry_point_group}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo(
        f"  cd {target.relative_to(Path.cwd()) if target.is_relative_to(Path.cwd()) else target}"
    )
    typer.echo("  uv build")
    typer.echo("  pip install dist/*.whl")


if __name__ == "__main__":
    app()
