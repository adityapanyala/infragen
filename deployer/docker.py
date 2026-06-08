import base64
import subprocess
from pathlib import Path

import boto3
from rich.console import Console

console = Console()


def build_and_push(project_dir: Path, region: str, ecr_url: str) -> str:
    """Build Docker image and push to ECR. Returns the full image URI."""
    image_tag = f"{ecr_url}:latest"
    _ecr_login(region, ecr_url)
    _docker_build(project_dir, image_tag)
    _docker_push(image_tag)
    return image_tag


def _ecr_login(region: str, ecr_url: str) -> None:
    console.print("\n[dim]Logging in to ECR...[/dim]")
    ecr = boto3.client("ecr", region_name=region)
    token = ecr.get_authorization_token()
    auth_data = token["authorizationData"][0]
    username, password = (
        base64.b64decode(auth_data["authorizationToken"]).decode().split(":", 1)
    )
    registry = ecr_url.split("/")[0]

    result = subprocess.run(
        ["docker", "login", "--username", username, "--password-stdin", registry],
        input=password,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ECR login failed: {result.stderr.strip()}")
    console.print("[green]✓[/green] Logged in to ECR\n")


def _docker_build(project_dir: Path, image_tag: str) -> None:
    console.print("[dim]Building Docker image...[/dim]\n")
    process = subprocess.Popen(
        ["docker", "build", "-t", image_tag, "."],
        cwd=str(project_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for line in process.stdout:
        console.print(line, end="", markup=False, highlight=False)
    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"docker build failed (exit {process.returncode})")


def _docker_push(image_tag: str) -> None:
    console.print("\n[dim]Pushing image to ECR...[/dim]\n")
    process = subprocess.Popen(
        ["docker", "push", image_tag],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for line in process.stdout:
        console.print(line, end="", markup=False, highlight=False)
    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"docker push failed (exit {process.returncode})")
