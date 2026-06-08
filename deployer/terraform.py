import subprocess
from pathlib import Path

from rich.console import Console

console = Console()


def run_terraform_init(terraform_dir: Path) -> None:
    _stream("terraform init", ["terraform", "init", "-input=false"], terraform_dir)


def run_terraform_apply(terraform_dir: Path) -> None:
    _stream("terraform apply", ["terraform", "apply", "-auto-approve", "-input=false"], terraform_dir)


def run_terraform_destroy(terraform_dir: Path) -> None:
    _stream("terraform destroy", ["terraform", "destroy", "-auto-approve", "-input=false"], terraform_dir)


def get_output(terraform_dir: Path, key: str) -> str:
    result = subprocess.run(
        ["terraform", "output", "-raw", key],
        cwd=str(terraform_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"terraform output '{key}' failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _stream(label: str, cmd: list[str], cwd: Path) -> None:
    console.print(f"\n[dim]Running {label}...[/dim]\n")
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for line in process.stdout:
        console.print(line, end="", markup=False, highlight=False)
    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"{label} failed (exit {process.returncode})")
