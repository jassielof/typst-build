import subprocess
import tempfile
from pathlib import Path

import typer

from .utils import (
    compile_template,
    copy_files,
    generate_thumbnail,
    get_typst_version,
    matches_version_req,
    parse_git_source,
    read_toml,
    typst_cache_dir,
    typst_data_dir,
    validate_package_name,
)

app = typer.Typer(
    help="Build, install, and list Typst packages/templates.", no_args_is_help=True
)


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
    if toml_file.is_file():
        toml_path = toml_file.resolve()
    elif toml_file.is_dir():
        candidate = toml_file / "typst.toml"
        if not candidate.exists():
            typer.echo(f"No typst.toml found in directory: {toml_file}")
            raise typer.Exit(code=1)
        toml_path = candidate.resolve()
    else:
        typer.echo(f"Path is neither a file nor a directory: {toml_file}")
        raise typer.Exit(code=1)

    toml_dir = toml_path.parent
    cfg = read_toml(toml_path)

    pkg = cfg.get("package", {})
    template = cfg.get("template", {}) or {}

    package_name = pkg.get("name")
    package_version = pkg.get("version")
    package_exclude: list[str] = list(pkg.get("exclude", []) or [])
    package_entrypoint = pkg.get("entrypoint", "main.typ")
    compiler_req = pkg.get("compiler")

    if not package_name or not package_version:
        typer.echo("Error: 'package.name' and 'package.version' are required.")
        raise typer.Exit(code=1)

    # Check compiler version requirement
    if compiler_req:
        current = get_typst_version()
        if not matches_version_req(compiler_req, current):
            typer.echo(
                f"Package requires Typst version '{compiler_req}', but you have {current[0]}.{current[1]}.{current[2]}."
            )
            raise typer.Exit(code=1)
        typer.echo(
            f"Typst version check passed (required: {compiler_req}, current: {current[0]}.{current[1]}.{current[2]})."
        )

    validate_package_name(package_name, toml_dir)

    template_path = template.get("path") or ""
    template_entrypoint = template.get("entrypoint") or ""
    thumbnail_path = template.get("thumbnail") or ""

    if template_path and template_entrypoint:
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


# TODO: support installing directly from local paths
@app.command()
def install(
    git_source: str = typer.Argument(
        ..., help="Git URL or alias (e.g., gh/user/repo[/path])"
    ),
) -> None:
    typer.echo(f"Attempting to install from: {git_source}")
    desc = parse_git_source(git_source)

    with tempfile.TemporaryDirectory(prefix="typst-build-git-") as tmpdir:
        clone_dir = Path(tmpdir)
        typer.echo(f"Cloning {desc.repo_url_for_clone} into {clone_dir}...")
        cmd = ["git", "clone", "--depth", "1"]
        if desc.git_ref:
            cmd += ["--branch", desc.git_ref]
        cmd += [desc.repo_url_for_clone, str(clone_dir)]
        res = subprocess.run(cmd)
        if res.returncode != 0:
            raise typer.Exit(code=1)
        typer.echo("Clone successful.")

        package_src = clone_dir / desc.path_in_repo
        toml_path = package_src / "typst.toml"
        if not toml_path.exists():
            typer.echo(
                f"typst.toml not found at {toml_path}. Searching recursively in {package_src}..."
            )
            found = [p for p in package_src.rglob("typst.toml")]
            if not found:
                typer.echo(f"No typst.toml found under {package_src}")
                raise typer.Exit(code=1)
            if len(found) == 1:
                toml_path = found[0]
                package_src = toml_path.parent
                typer.echo(f"Found typst.toml at: {toml_path}")
            else:
                # List and prompt
                typer.echo(
                    "\nMultiple typst.toml files found. Please choose one to install:"
                )
                for i, p in enumerate(found, 1):
                    disp = p.relative_to(clone_dir)
                    typer.echo(f"  {i}: {disp}")
                choice = typer.prompt(f"Enter number (1-{len(found)})", type=int)
                if choice < 1 or choice > len(found):
                    typer.echo("Invalid choice.")
                    raise typer.Exit(code=1)
                toml_path = found[choice - 1]
                package_src = toml_path.parent
                typer.echo(f"Selected: {toml_path}")

        cfg = read_toml(toml_path)
        pkg = cfg.get("package", {})
        name = pkg.get("name")
        version = pkg.get("version")
        exclude: list[str] = list(pkg.get("exclude", []) or [])
        entrypoint = pkg.get("entrypoint", "main.typ")
        compiler_req = pkg.get("compiler")

        if not name or not version:
            typer.echo(
                "Invalid typst.toml: package.name and package.version are required."
            )
            raise typer.Exit(code=1)

        if compiler_req:
            current = get_typst_version()
            if not matches_version_req(compiler_req, current):
                typer.echo(
                    f"Package requires Typst version '{compiler_req}', but you have {current[0]}.{current[1]}.{current[2]}."
                )
                raise typer.Exit(code=1)
            typer.echo(
                f"Typst version check passed (required: {compiler_req}, current: {current[0]}.{current[1]}.{current[2]})."
            )

        data_dir = typst_data_dir()
        provider_abbr = {
            "github.com": "gh",
            "gitlab.com": "gl",
            "bitbucket.org": "bb",
        }.get(desc.provider_host, desc.provider_host.split(".")[0])
        namespace = f"{provider_abbr}-{desc.user_or_org}"
        final_install_dir = data_dir / "packages" / namespace / name / version
        final_install_dir.mkdir(parents=True, exist_ok=True)

        typer.echo(f"Installing to: {final_install_dir}")
        copy_files(
            package_src,
            final_install_dir,
            exclude,
            f"{namespace}/{name}",
            version,
            entrypoint,
        )

        typer.echo(f"\nPackage '{name}' v{version} installed successfully.")
        typer.echo(
            f'You can now import it using: #import "@{namespace}/{name}:{version}": ...'
        )


@app.command("list", help="List all installed Typst packages")
def list_packages(
    preview: bool = typer.Option(
        False, "--preview", help="List only preview (cache) packages"
    ),
    local: bool = typer.Option(
        False, "--local", help="List only local (data) packages"
    ),
) -> None:
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


# TODO: implement remove command
@app.command()
def remove():
    """
    Remove an installed Typst package
    """
    pass


# TODO: implement update command
@app.command()
def update(check: bool = typer.Option()):
    """
    Update or check for updates on installed Typst packages.
    Only applies to local packages
    """
    pass


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

    def print_package_info(package_info):
        # Print the relevant package information (be tolerant of missing fields)
        pkg = package_info.get("package", {})
        name = pkg.get("name", "<unknown>")
        version = pkg.get("version", "<unknown>")
        description = pkg.get("description", "<none>")
        authors = ", ".join(pkg.get("authors", [])) if pkg.get("authors") else "<none>"
        license_ = pkg.get("license", "<unknown>")
        homepage = pkg.get("homepage")
        repository = pkg.get("repository")

        typer.echo(f"Name: {name}")
        typer.echo(f"Version: {version}")
        typer.echo(f"Description: {description}")
        typer.echo(f"Authors: {authors}")
        typer.echo(f"License: {license_}")
        if homepage:
            typer.echo(f"Homepage: {homepage}")
        if repository:
            typer.echo(f"Repository: {repository}")

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
            typer.echo("Multiple packages found in this monorepo:")

        for path in toml_candidates:
            try:
                rel_path = path.parent.relative_to(clone_dir)
            except ValueError:
                rel_path = path.parent

            if multiple:
                typer.echo(f"- {rel_path}")

            package_info = parse_typst_toml(path)
            print_package_info(package_info)
            if multiple:
                typer.echo("")

        # Clean up by removing the cloned directory
        # subprocess.run(['rm', '-rf', clone_dir])  # Not needed, tmpdir will be removed automatically
