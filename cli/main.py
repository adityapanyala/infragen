import sys
from pathlib import Path

import typer
from rich.console import Console

from cli.doctor import run_doctor
from cli.prompts import print_header, print_error, print_section, print_warning

app = typer.Typer(
    name="infragen",
    help="Deploy web apps to AWS from a single command.",
    add_completion=False,
)

console = Console()


@app.command()
def doctor():
    """Check all prerequisites and AWS permissions."""
    passed = run_doctor(check_perms=True)
    if not passed:
        raise typer.Exit(code=1)


@app.command()
def deploy(
    prod: bool = typer.Option(False, "--prod", help="Deploy using production architecture."),
):
    """Scan your project and deploy it to AWS."""
    console.print()

    passed = run_doctor(check_perms=False)
    if not passed:
        raise typer.Exit(code=1)

    console.print()
    console.rule()
    console.print()

    project_dir = Path.cwd()

    console.print(f"[dim]Scanning {project_dir}...[/dim]")
    console.print()

    try:
        from scanner import scan
        from scanner.detector import DetectionError, UnsupportedFrameworkError
        from scanner.env_vars import MissingEnvExampleError

        result = scan(project_dir)

    except DetectionError as e:
        print_error(str(e))
        raise typer.Exit(code=1)
    except UnsupportedFrameworkError as e:
        print_error(str(e))
        raise typer.Exit(code=1)
    except MissingEnvExampleError as e:
        print_error(str(e))
        raise typer.Exit(code=1)

    print_section("DETECTED")
    console.print(f"  Runtime      {result.runtime.value} {result.runtime_version}")
    console.print(f"  Framework    {result.framework.value}")
    console.print(f"  Type         {result.service_type.value}")
    console.print(f"  Port         {result.port or 'none'}")
    console.print(f"  Dockerfile   {'found' if result.has_dockerfile else 'not found — will generate'}")

    if result.inferred_resources:
        print_section("INFERRED FROM CODEBASE")
        for resource in result.inferred_resources:
            console.print(f"  [green]✓[/green] {resource}")

    if result.warnings:
        console.print()
        for warning in result.warnings:
            print_warning(warning)

    console.print()
    console.rule()
    console.print()
    console.print("[dim]Deployment coming soon. Scanner complete.[/dim]")


if __name__ == "__main__":
    app()
