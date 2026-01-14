from pathlib import Path

import typer

from .commands.info import app as info_app
from .commands.install import app as install_app
from .commands.list import app as list_app
from .commands.remove import app as remove_app
from .commands.update import app as update_app
from .utils import (
    compile_template,
    generate_thumbnail,
    get_typst_version,
    matches_version_req,
)

app = typer.Typer(
    help="Build, install, and list Typst packages/templates.", no_args_is_help=True
)


def _resolve_toml_path(toml_file: Path) -> Path:
    """Resolve the path to typst.toml file."""
    if toml_file.is_file():
        return toml_file.resolve()

    if toml_file.is_dir():
        candidate = toml_file / "typst.toml"
        if not candidate.exists():
            typer.echo(f"No typst.toml found in directory: {toml_file}")
            raise typer.Exit(code=1)
        return candidate.resolve()

    typer.echo(f"Path is neither a file nor a directory: {toml_file}")
    raise typer.Exit(code=1)


def _validate_package_config(
    package_name: str | None, package_version: str | None
) -> None:
    """Validate required package configuration fields."""
    if not package_name or not package_version:
        typer.echo("Error: 'package.name' and 'package.version' are required.")
        raise typer.Exit(code=1)


def _check_compiler_version(compiler_req: str | None) -> None:
    """Check if compiler version meets requirements."""
    if not compiler_req:
        return

    current = get_typst_version()
    if not matches_version_req(compiler_req, current):
        typer.echo(
            f"Package requires Typst version '{compiler_req}', but you have {current[0]}.{current[1]}.{current[2]}."
        )
        raise typer.Exit(code=1)

    typer.echo(
        f"Typst version check passed (required: {compiler_req}, current: {current[0]}.{current[1]}.{current[2]})."
    )


def _build_template(toml_dir: Path, package_name: str, template: dict) -> None:
    """Build template and thumbnail if configured."""
    template_path = template.get("path") or ""
    template_entrypoint = template.get("entrypoint") or ""
    thumbnail_path = template.get("thumbnail") or ""

    if not (template_path and template_entrypoint):
        return

    typer.echo(f"Compiling template: {template_path}/{template_entrypoint}")
    compile_template(toml_dir, package_name, template_path, template_entrypoint)

    if thumbnail_path:
        typer.echo(f"Generating thumbnail: {thumbnail_path}")
        generate_thumbnail(
            toml_dir,
            package_name,
            template_path,
            template_entrypoint,
            thumbnail_path,
        )


app.add_typer(info_app)
app.add_typer(remove_app)
app.add_typer(update_app)
app.add_typer(install_app)
app.add_typer(list_app)
