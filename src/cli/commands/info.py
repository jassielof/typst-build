import subprocess
import tempfile
from pathlib import Path

import typer

from cli.utils import parse_git_source, read_toml, typst_data_dir

app = typer.Typer()


@app.command()
def info(
    package_name: str = typer.Argument(
        ..., help="The name of the package (e.g., 'gh/user-repo')"
    ),
) -> None:
    """
    Show information from an installed or remote (git) Typst package/template.
    """

    def parse_typst_toml(toml_path):
        # Parse the typst.toml file and return the package information
        return read_toml(toml_path)

    def print_package_info(package_info, monorepo_path=None):
        # Print the relevant package information (be tolerant of missing fields)
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        pkg = package_info.get("package", {})
        name = pkg.get("name", "<unknown>")
        version = pkg.get("version", "<unknown>")
        description = pkg.get("description", "<none>")
        authors = ", ".join(pkg.get("authors", [])) if pkg.get("authors") else "<none>"
        license_ = pkg.get("license", "<unknown>")
        homepage = pkg.get("homepage")
        repository = pkg.get("repository")

        # Create a table for package information
        table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
        table.add_column("Field", style="cyan bold", width=15, no_wrap=True)
        table.add_column("Value", style="white")

        table.add_row("Package", f"[bold green]{name}[/bold green]")
        table.add_row("Version", version)
        if description != "<none>":
            table.add_row("Description", description)
        if authors != "<none>":
            table.add_row("Authors", authors)
        table.add_row("License", license_)
        if homepage:
            table.add_row("Homepage", homepage)
        if repository:
            table.add_row("Repository", repository)

        # If monorepo path is provided, show it in the panel title
        if monorepo_path:
            title = f"[bold cyan]Monorepo Path:[/bold cyan] {monorepo_path}"
            panel = Panel(table, title=title, title_align="left", expand=False)
            console.print(panel)
        else:
            console.print(table)

    # Check if the package is installed locally
    local_package_path = typst_data_dir() / "packages" / package_name
    if local_package_path.is_dir():
        # Load package information from local typst.toml
        toml_path = local_package_path / "typst.toml"
        if not toml_path.exists():
            typer.echo(
                f"No typst.toml found in the package directory: {local_package_path}"
            )
            raise typer.Exit(code=1)
        package_info = parse_typst_toml(toml_path)
        print_package_info(package_info)
        return

    # If not installed, clone the repository
    git_source = parse_git_source(package_name)
    repo_url = git_source.repo_url_for_clone
    with tempfile.TemporaryDirectory(prefix="typst-info-git-") as tmpdir:
        clone_dir = Path(tmpdir)
        typer.echo(f"Cloning {repo_url}...")
        cmd = ["git", "clone", "--depth", "1", repo_url, str(clone_dir)]
        res = subprocess.run(cmd)
        if res.returncode != 0:
            typer.echo("Failed to clone the repository.")
            raise typer.Exit(code=1)

        # Handle path in repo if it's a monorepo
        search_dir = (
            clone_dir / git_source.path_in_repo
            if git_source.path_in_repo != Path("")
            else clone_dir
        )

        # Collect candidate typst.toml files (supports monorepos) and print them all
        toml_candidates: list[Path] = []
        direct_toml = search_dir / "typst.toml"
        if direct_toml.exists():
            toml_candidates.append(direct_toml)
        else:
            toml_candidates = sorted(search_dir.rglob("typst.toml"))

        if not toml_candidates:
            typer.echo(f"No typst.toml found in the cloned repository: {search_dir}")
            raise typer.Exit(code=1)

        multiple = len(toml_candidates) > 1
        if multiple:
            typer.echo("\n[bold]Multiple packages found in this monorepo:[/bold]\n")

        for path in toml_candidates:
            try:
                rel_path = path.parent.relative_to(clone_dir)
            except ValueError:
                rel_path = path.parent

            package_info = parse_typst_toml(path)
            if multiple:
                print_package_info(package_info, monorepo_path=str(rel_path))
            else:
                print_package_info(package_info)

            if multiple:
                typer.echo("")
