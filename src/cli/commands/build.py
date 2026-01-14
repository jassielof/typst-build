from pathlib import Path

import typer

from cli import (
    _build_template,
    _check_compiler_version,
    _resolve_toml_path,
    _validate_package_config,
)
from cli.utils import copy_files, read_toml, validate_package_name

app = typer.Typer()


@app.command()
def build(
    toml_file: Path = typer.Argument(
        ..., help="Path to the typst.toml file or its directory"
    ),
    output_dir: str = typer.Option(
        "out",
        "--output-dir",
        help="The output directory where the built package will be placed.",
    ),
    namespace: str = typer.Option(
        "preview",
        "--namespace",
        "-n",
        help="Namespace for the package (e.g., 'preview' for official, 'local' for self-hosted, or any custom namespace)",
    ),
) -> None:
    """
    Build a Typst package/template from a typst.toml file to be published or installed.
    """
    # Resolve toml file
    toml_path = _resolve_toml_path(toml_file)
    toml_dir = toml_path.parent
    cfg = read_toml(toml_path)

    pkg = cfg.get("package", {})
    template = cfg.get("template", {}) or {}

    package_name = pkg.get("name")
    package_version = pkg.get("version")
    package_exclude: list[str] = list(pkg.get("exclude", []) or [])
    package_entrypoint = pkg.get("entrypoint", "main.typ")
    compiler_req = pkg.get("compiler")

    _validate_package_config(package_name, package_version)
    _check_compiler_version(compiler_req)
    validate_package_name(package_name, toml_dir)

    _build_template(toml_dir, package_name, template)

    output_base = Path(output_dir)
    final_output_dir = output_base / package_name / package_version

    # Exclude the output directory name to avoid recursive copy
    out_name = output_base.name
    if out_name not in package_exclude:
        package_exclude.append(out_name)

    typer.echo(f"Copying files to: {final_output_dir}")
    copy_files(
        toml_dir,
        final_output_dir,
        package_exclude,
        f"{namespace}/{package_name}",
        package_version,
        package_entrypoint,
    )
    typer.echo(
        f"Package '{package_name}' v{package_version} built successfully to {final_output_dir}"
    )
