from pathlib import Path

import typer

from cli.utils import typst_cache_dir, typst_data_dir

app = typer.Typer()


@app.command("list", help="List all installed Typst packages")
def list_packages(
    universe: bool = typer.Option(
        False,
        "--universe",
        help="List only Universe (cache) packages installed from Typst Universe",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        help="List only packages from data directory (manually installed, any namespace)",
    ),
):
    from rich.console import Console
    from rich.table import Table

    from cli.utils import read_toml

    console = Console()

    def get_package_description(ver_dir: Path) -> str:
        """Extract description from typst.toml in a package version directory."""
        toml_path = ver_dir / "typst.toml"
        if toml_path.exists():
            try:
                config = read_toml(toml_path)
                return config.get("package", {}).get("description", "")
            except Exception:
                return ""
        return ""

    def parse_version(ver: str) -> tuple:
        """Parse version string into tuple for sorting (handles semantic versioning)."""
        try:
            parts = ver.split(".")
            return tuple(int(p) if p.isdigit() else p for p in parts)
        except Exception:
            return (ver,)

    def list_packages_in_root(packages_root_dir: Path, root_type: str) -> int:
        count = 0
        if not packages_root_dir.is_dir():
            typer.echo(
                f"  No packages found in {root_type} directory ({packages_root_dir} does not exist)."
            )
            return 0

        # First, collect all packages with their versions
        packages: dict[
            tuple[str, str], list[tuple[str, str]]
        ] = {}  # (ns, pkg) -> [(ver, desc), ...]

        for ns_dir in sorted([p for p in packages_root_dir.iterdir() if p.is_dir()]):
            ns = ns_dir.name
            for pkg_dir in sorted([p for p in ns_dir.iterdir() if p.is_dir()]):
                pkg = pkg_dir.name
                versions = []
                for ver_dir in sorted(
                    [p for p in pkg_dir.iterdir() if p.is_dir()],
                    key=lambda p: parse_version(p.name),
                    reverse=True,
                ):
                    ver = ver_dir.name
                    desc = get_package_description(ver_dir)
                    versions.append((ver, desc))
                    count += 1
                if versions:
                    packages[(ns, pkg)] = versions

        if not packages:
            return 0

        # Create Rich table
        table = Table(title=f"{root_type.title()} Packages", show_header=True)
        table.add_column("Package", style="cyan", no_wrap=False)
        table.add_column("Version(s)", style="green", no_wrap=False)
        table.add_column("Description", style="white", no_wrap=False)

        # Add rows for each package
        for (ns, pkg), versions in sorted(packages.items()):
            pkg_name = f"@{ns}/{pkg}"

            if len(versions) == 1:
                # Single version
                ver, desc = versions[0]
                table.add_row(pkg_name, ver, desc or "")
            else:
                # Multiple versions - show them as a comma-separated list or newline-separated
                version_list = "\n".join(ver for ver, _ in versions)
                # Use description from the latest (first) version
                latest_desc = versions[0][1]
                table.add_row(pkg_name, version_list, latest_desc or "")

        console.print(table)
        return count

    want_local = local
    want_universe = universe
    list_all = not want_local and not want_universe

    total = 0
    if want_local or list_all:
        typer.echo("")
        total += list_packages_in_root(typst_data_dir() / "packages", "data")
    if want_universe or list_all:
        typer.echo("")
        total += list_packages_in_root(typst_cache_dir() / "packages", "cache")

    if total == 0:
        if want_local and not want_universe:
            typer.echo("No local packages found.")
        elif want_universe and not want_local:
            typer.echo("No Universe packages found.")
        else:
            typer.echo("No packages found in standard Typst data or cache directories.")
