import typer

app = typer.Typer()


# TODO: implement update command
@app.command()
def update(check: bool = typer.Option()):
    """
    Update or check for updates on installed Typst packages.
    Only applies to local packages
    """
    pass

    # Clean up by removing the cloned directory
    # subprocess.run(['rm', '-rf', clone_dir])  # Not needed, tmpdir will be removed automatically
