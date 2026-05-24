import typer
from rich.console import Console
from rich.prompt import Prompt, Confirm


console = Console()


def ask(question: str, default: str = "") -> str:
    return Prompt.ask(f"[cyan]{question}[/cyan]", default=default)


def ask_secret(question: str) -> str:
    return Prompt.ask(f"[cyan]{question}[/cyan]", password=True)


def confirm(question: str, default: bool = False) -> bool:
    return Confirm.ask(f"[cyan]{question}[/cyan]", default=default)


def print_success(message: str) -> None:
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str) -> None:
    console.print(f"  {message}")


def print_header(title: str) -> None:
    console.print()
    console.rule(f"[bold]{title}[/bold]")
    console.print()


def print_section(title: str) -> None:
    console.print(f"\n[bold white]{title}[/bold white]")


def print_divider() -> None:
    console.rule()


def ask_deploy_description() -> str:
    console.print()
    console.print("[dim]Describe your deployment in plain English.[/dim]")
    console.print("[dim]Example: 'A REST API with PostgreSQL, needs Redis for caching'[/dim]")
    console.print()
    return ask("Description")


def ask_backend_url() -> str | None:
    has_backend = confirm("Does this frontend call a backend API?", default=False)
    if not has_backend:
        return None
    return ask("Backend API URL:")


def ask_environment() -> str:
    console.print()
    choice = Prompt.ask(
        "[cyan]Environment[/cyan]",
        choices=["dev", "staging", "production"],
        default="dev",
    )
    return choice


def ask_region() -> str:
    return ask("AWS region", default="us-east-1")


def collect_secrets(secret_keys: list[str]) -> dict[str, str]:
    if not secret_keys:
        return {}

    console.print()
    print_section("SECRETS")
    console.print("[dim]Enter values — sent directly to AWS SSM, never written to disk[/dim]")
    console.print()

    secrets = {}
    for key in secret_keys:
        secrets[key] = ask_secret(f"{key}")

    return secrets


def confirm_deploy() -> bool:
    console.print()
    console.rule()
    return confirm("Deploy?", default=False)


def confirm_dockerfile(content: str) -> bool:
    console.print()
    print_section("GENERATED DOCKERFILE")
    console.print(content)
    console.print()
    console.print("[dim]No Dockerfile found. Generated one for your app.[/dim]")
    console.print("[dim]Review it above. Add your own Dockerfile and re-run, or use this one.[/dim]")
    console.print()
    return confirm("Use this Dockerfile?", default=True)


def confirm_inferred_resource(description: str) -> bool:
    return confirm(f"Include {description}?", default=True)
