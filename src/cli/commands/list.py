from pathlib import Path

import typer

from cli.utils import typst_cache_dir, typst_data_dir

app = typer.Typer()


# FIXME: Preview should be renamed to Universe installed packages, as they are called preview given that Typst Universe is in the Preview stage, they'll rename the namespace later to something else, but they packages directory probably won't, a good name should be probably "universe".
# FIXME: Local should (probably) also be renamed, as it only fetchs for local named namespaces, but locally installed packages can have any namespace, local is fine, but it needs to handle any namespace.
# TODO: For each installed package, it would be nice to show little additional information, specially the description from the typst.toml file.
# FIXME: The list can end up listing the same package version multiple times, if it detects the same package installed and with multiple versions, it should list the package once and then its versions below it. Otherwise it can get very noisy. For packages installed and that only have a single version, print it in the same line. In these cases, for the description, since there will be many versions (for cases with multiple versions), it can just print the description of the latest version installed.
@app.command("list", help="List all installed Typst packages")
def list_packages(
    preview: bool = typer.Option(
        False,
        "--preview",
        help="List only preview (cache) packages installed from Typst Universe",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        help="List only local (data) packages that were manually installed",
    ),
):
    typer.echo("Installed Typst packages:")

    def list_packages_in_root(packages_root_dir: Path, root_type: str) -> int:
        count = 0
        if not packages_root_dir.is_dir():
            typer.echo(
                f"  No packages found in {root_type} directory ({packages_root_dir} does not exist)."
            )
            return 0

        for ns_dir in sorted([p for p in packages_root_dir.iterdir() if p.is_dir()]):
            ns = ns_dir.name
            for pkg_dir in sorted([p for p in ns_dir.iterdir() if p.is_dir()]):
                pkg = pkg_dir.name
                for ver_dir in sorted([p for p in pkg_dir.iterdir() if p.is_dir()]):
                    ver = ver_dir.name
                    typer.echo(f"  @{ns}/{pkg}:{ver}")
                    count += 1
        return count

    want_local = local
    want_preview = preview
    list_all = not want_local and not want_preview

    total = 0
    if want_local or list_all:
        typer.echo("\nLocal packages (data directory):")
        total += list_packages_in_root(typst_data_dir() / "packages", "data")
    if want_preview or list_all:
        typer.echo("\nPreview packages (cache directory):")
        total += list_packages_in_root(typst_cache_dir() / "packages", "cache")

    if total == 0:
        if want_local and not want_preview:
            typer.echo("  No local packages found.")
        elif want_preview and not want_local:
            typer.echo("  No preview packages found.")
        else:
            typer.echo(
                "  No packages found in standard Typst data or cache directories."
            )
