import subprocess
import tempfile
from pathlib import Path

import typer

from cli.utils import (
    copy_files,
    get_typst_version,
    matches_version_req,
    parse_git_source,
    read_toml,
    typst_data_dir,
)

app = typer.Typer()


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
