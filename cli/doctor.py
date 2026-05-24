from rich.console import Console
from rich.table import Table

from prerequisites.checker import run_all_checks
from prerequisites.permissions import check_permissions, all_passed, failed_permissions
from cli.prompts import print_success, print_error, print_header, print_section

console = Console()


def run_doctor(check_perms: bool = True) -> bool:
    print_header("infragen doctor")

    console.print("Checking prerequisites...\n")
    checks = run_all_checks()

    all_checks_passed = True
    for check in checks:
        if check.passed:
            console.print(f"  [green]✓[/green]  {check.name:<20} {check.detail}")
        else:
            console.print(f"  [red]✗[/red]  {check.name:<20} {check.detail}")
            if check.fix:
                console.print(f"  [dim]   {' ' * 20} {check.fix}[/dim]")
            all_checks_passed = False

    if not all_checks_passed:
        console.print()
        failed = sum(1 for c in checks if not c.passed)
        console.print(f"[red]✗ {failed} check(s) failed. Fix the issues above and run infragen doctor again.[/red]")
        return False

    if not check_perms:
        console.print()
        print_success("All prerequisite checks passed.")
        return True

    console.print()
    console.print("Checking AWS permissions...\n")
    perm_results = check_permissions()

    for result in perm_results:
        if result.allowed:
            console.print(f"  [green]✓[/green]  {result.action}")
        else:
            console.print(f"  [red]✗[/red]  {result.action}")

    console.print()

    if not all_passed(perm_results):
        failed = failed_permissions(perm_results)
        console.print(f"[red]✗ {len(failed)} permission(s) missing.[/red]")
        console.print()
        console.print("[dim]Add these IAM permissions to your AWS user or role:[/dim]")
        for perm in failed:
            console.print(f"  [dim]- {perm}[/dim]")
        return False

    console.print()
    print_success("All checks passed. Run infragen deploy inside your project folder.")
    return True
