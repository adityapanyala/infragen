import subprocess
from dataclasses import dataclass

@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    fix: str | None = None

def check_aws_cli() -> CheckResult:
    try:
        result = subprocess.run(["aws", "--version"],capture_output=True, text=True)
        version = result.stdout.strip() or result.stderr.strip()
        return CheckResult(
            name="AWS CLI",
            passed=True,
            detail=version,
        )
    except FileNotFoundError:
        return CheckResult(
            name="AWS CLI",
            passed=False,
            detail="not found",
            fix="Install AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html",
        )


def check_aws_credentials() -> CheckResult:
    try:
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return CheckResult(
                name="AWS credentials",
                passed=True,
                detail="configured",
            )
        return CheckResult(
            name="AWS credentials",
            passed=False,
            detail="not configured",
            fix="Run: aws configure",
        )
    except FileNotFoundError:
        return CheckResult(
            name="AWS credentials",
            passed=False,
            detail="AWS CLI not installed",
            fix="Install AWS CLI first",
        )


def check_aws_identity() -> CheckResult:
    try:
        import json
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            identity = json.loads(result.stdout)
            arn = identity.get("Arn", "unknown")
            return CheckResult(
                name="AWS identity",
                passed=True,
                detail=arn,
            )
        return CheckResult(
            name="AWS identity",
            passed=False,
            detail="could not retrieve identity",
            fix="Run: aws configure",
        )
    except Exception:
        return CheckResult(
            name="AWS identity",
            passed=False,
            detail="error retrieving identity",
            fix="Run: aws configure",
        )


def check_aws_region() -> CheckResult:
    import os
    try:
        region = None

        env_region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION")
        if env_region:
            region = env_region
        else:
            result = subprocess.run(
                ["aws", "configure", "get", "region"],
                capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout.strip():
                region = result.stdout.strip()

        if region:
            return CheckResult(
                name="AWS region",
                passed=True,
                detail=region,
            )

        return CheckResult(
            name="AWS region",
            passed=False,
            detail="not set",
            fix="Run: aws configure  (set your preferred region)",
        )
    except Exception:
        return CheckResult(
            name="AWS region",
            passed=False,
            detail="could not determine region",
            fix="Run: aws configure",
        )


def check_terraform() -> CheckResult:
    try:
        result = subprocess.run(
            ["terraform", "--version"],
            capture_output=True, text=True
        )
        first_line = result.stdout.strip().splitlines()[0]
        return CheckResult(
            name="Terraform",
            passed=True,
            detail=first_line,
        )
    except FileNotFoundError:
        return CheckResult(
            name="Terraform",
            passed=False,
            detail="not found",
            fix="Install Terraform: https://developer.hashicorp.com/terraform/install",
        )


def check_docker() -> CheckResult:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return CheckResult(
                name="Docker",
                passed=True,
                detail="running",
            )
        return CheckResult(
            name="Docker",
            passed=False,
            detail="daemon not running",
            fix="Start Docker Desktop and try again.\n"
                "     (Not required for React static deployments)",
        )
    except FileNotFoundError:
        return CheckResult(
            name="Docker",
            passed=False,
            detail="not installed",
            fix="Install Docker Desktop: https://www.docker.com/products/docker-desktop",
        )


def run_all_checks() -> list[CheckResult]:
    return [
        check_aws_cli(),
        check_aws_credentials(),
        check_aws_identity(),
        check_aws_region(),
        check_terraform(),
        check_docker(),
    ]
