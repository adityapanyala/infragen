import subprocess
import time
from pathlib import Path

import boto3
from rich.console import Console

console = Console()


def build_and_deploy(
    project_dir: Path,
    region: str,
    build_command: str,
    build_output_dir: str,
    bucket_name: str,
    distribution_id: str,
) -> None:
    _npm_build(project_dir, build_command)
    _s3_sync(project_dir, build_output_dir, bucket_name, region)
    _invalidate_cloudfront(region, distribution_id)


def _npm_build(project_dir: Path, build_command: str) -> None:
    console.print(f"\n[dim]Running {build_command}...[/dim]\n")
    process = subprocess.Popen(
        build_command.split(),
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
        raise RuntimeError(f"Build failed (exit {process.returncode})")


def _s3_sync(project_dir: Path, build_output_dir: str, bucket_name: str, region: str) -> None:
    build_dir = project_dir / build_output_dir
    console.print(f"\n[dim]Syncing {build_output_dir}/ to s3://{bucket_name}...[/dim]\n")
    process = subprocess.Popen(
        ["aws", "s3", "sync", str(build_dir), f"s3://{bucket_name}",
         "--delete", "--region", region],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for line in process.stdout:
        console.print(line, end="", markup=False, highlight=False)
    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"S3 sync failed (exit {process.returncode})")
    console.print(f"\n[green]✓[/green] Files uploaded to S3")


def _invalidate_cloudfront(region: str, distribution_id: str) -> None:
    console.print("\n[dim]Invalidating CloudFront cache...[/dim]")
    cf = boto3.client("cloudfront", region_name=region)
    cf.create_invalidation(
        DistributionId=distribution_id,
        InvalidationBatch={
            "Paths": {"Quantity": 1, "Items": ["/*"]},
            "CallerReference": str(time.time()),
        },
    )
    console.print("[green]✓[/green] CloudFront cache invalidated")
