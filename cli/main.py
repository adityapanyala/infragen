import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

from cli.doctor import run_doctor
from cli.prompts import (
    print_header, print_error, print_section, print_warning,
    print_success, print_info, confirm, ask, ask_secret,
    ask_deploy_description, ask_environment, ask_region,
    ask_backend_url, confirm_inferred_resource, confirm_dockerfile,
    collect_secrets, confirm_deploy,
)

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
    prod: bool = typer.Option(False, help="Deploy using production architecture."),
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
    project_name = project_dir.name.lower().replace(" ", "-").replace("_", "-")

    console.print(f"[dim]Scanning {project_dir}...[/dim]")
    console.print()

    try:
        from scanner import scan
        from scanner.detector import DetectionError, UnsupportedFrameworkError
        from scanner.env_vars import MissingEnvExampleError
        from scanner.dockfile import scan_dockerfile

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

    # ── DETECTED ─────────────────────────────────────────────
    print_section("DETECTED")
    console.print(f"  Runtime      {result.runtime.value} {result.runtime_version}")
    console.print(f"  Framework    {result.framework.value}")
    console.print(f"  Type         {result.service_type.value}")
    console.print(f"  Port         {result.port or 'none'}")
    console.print(f"  Dockerfile   {'found' if result.has_dockerfile else 'not found — will generate'}")

    # ── DOCKERFILE ───────────────────────────────────────────
    if not result.has_dockerfile:
        from scanner.dockfile import scan_dockerfile
        dockerfile_result = scan_dockerfile(
            project_dir=project_dir,
            framework=result.framework,
            port=result.port,
            runtime_version=result.runtime_version,
            django_project_name=result.django_project_name,
        )
        if dockerfile_result.generated_content:
            approved = confirm_dockerfile(dockerfile_result.generated_content)
            if not approved:
                console.print()
                console.print("[dim]Add your own Dockerfile and run infragen deploy again.[/dim]")
                raise typer.Exit(code=0)
            dockerfile_path = project_dir / "Dockerfile"
            dockerfile_path.write_text(dockerfile_result.generated_content)
            print_success("Dockerfile written to project root.")

    # ── INFERRED ─────────────────────────────────────────────
    confirmed_rds = False
    confirmed_elasticache = False
    confirmed_s3 = False

    if result.inferred_resources:
        print_section("INFERRED FROM CODEBASE")
        for resource in result.inferred_resources:
            console.print(f"  [dim]{resource}[/dim]")

        console.print()
        if result.needs_rds:
            confirmed_rds = confirm_inferred_resource(
                f"PostgreSQL database ({result.rds_engine})"
            )
        if result.needs_elasticache:
            confirmed_elasticache = confirm_inferred_resource("Redis (ElastiCache)")
        if result.needs_s3:
            confirmed_s3 = confirm_inferred_resource("S3 bucket (file storage)")

    if result.warnings:
        console.print()
        for warning in result.warnings:
            print_warning(warning)

    # ── USER INPUT ───────────────────────────────────────────
    console.print()
    user_description = ask_deploy_description()
    environment = ask_environment()
    region = _get_region()

    backend_api_url = None
    from models import ServiceType
    if result.service_type in (ServiceType.FRONTEND_STATIC, ServiceType.FRONTEND_SSR):
        backend_api_url = ask_backend_url()

    # ── BUILD INFRA SPEC ─────────────────────────────────────
    from models import InfraSpec, DeployMode

    mode = DeployMode.PROD if prod else DeployMode.FREE
    terraform_output_dir = Path.home() / ".infragen" / "output" / project_name / "terraform"

    spec = InfraSpec(
        scan=result,
        mode=mode,
        user_description=user_description,
        region=region,
        project_name=project_name,
        environment=environment,
        instance_type="t3.micro",
        rds_instance_class="db.t3.micro",
        confirmed_rds=confirmed_rds,
        confirmed_elasticache=confirmed_elasticache,
        confirmed_s3=confirmed_s3,
        backend_api_url=backend_api_url,
        terraform_output_dir=terraform_output_dir,
    )

    # ── RUN PIPELINE ─────────────────────────────────────────
    console.print()
    console.print("[dim]Generating infrastructure plan...[/dim]")

    from agents.orchestrator import run_pipeline
    from agents.cost_estimator import format_cost_table, get_total_cost

    pipeline_result = run_pipeline(spec)

    if pipeline_result.get("error"):
        print_error(pipeline_result["error"])
        raise typer.Exit(code=1)

    # ── APPROVAL GATE ────────────────────────────────────────
    console.print()
    console.rule("[bold]infragen — deployment plan[/bold]")
    console.print()

    mode_label = "[yellow]PRODUCTION[/yellow]" if prod else "[green]FREE TIER[/green]"
    console.print(f"Mode:  {mode_label}")

    print_section("DETECTED")
    console.print(f"  Runtime      {result.runtime.value} {result.runtime_version}")
    console.print(f"  Framework    {result.framework.value}")
    console.print(f"  Type         {result.service_type.value}")
    console.print(f"  Port         {result.port or 'none'}")
    console.print(f"  Dockerfile   {'found' if result.has_dockerfile else 'generated'}")

    print_section("INFERRED FROM CODEBASE")
    if result.inferred_resources:
        for resource in result.inferred_resources:
            console.print(f"  [green]✓[/green] {resource}")
    else:
        console.print("  none detected")

    print_section("INFRASTRUCTURE PLAN")
    _print_infra_plan(spec, result)

    print_section("SECURITY")
    findings = pipeline_result.get("security_findings") or []
    if not findings:
        console.print("  [green]✓[/green]  No issues found")
    else:
        for f in findings:
            if f.classification == "auto_fixed":
                console.print(f"  [green]✓ auto-fixed[/green]   {f.plain_english}")
            elif f.classification == "needs_input":
                console.print(f"  [red]! needs input[/red]   {f.plain_english}")
            else:
                console.print(f"  [dim]  informational[/dim]  {f.plain_english}")

    print_section("COST ESTIMATE")
    cost_items = pipeline_result.get("cost_items") or []
    if cost_items:
        table = format_cost_table(cost_items)
        console.print(table)
        if not prod:
            console.print()
            console.print("  [dim]⚠  Free tier applies to new AWS accounts for 12 months only[/dim]")
            total_after = sum(
                v for k, v in {
                    "aws_instance": 8.47,
                    "aws_db_instance": 25.55,
                }.items()
                if any(i.resource_type == k for i in cost_items)
            )
            if total_after > 0:
                console.print(f"  [dim]⚠  After free tier expires: ~${total_after:.2f}/month[/dim]")
    else:
        console.print("  Unable to estimate costs.")

    # ── SECRETS ──────────────────────────────────────────────
    secret_keys = [k for k, v in result.env_vars.items() if v == "secret"]
    secrets = collect_secrets(secret_keys)

    # ── DEPLOY CONFIRMATION ──────────────────────────────────
    should_deploy = confirm_deploy()

    if not should_deploy:
        console.print()
        console.print("[dim]Deployment cancelled. No resources created.[/dim]")
        raise typer.Exit(code=0)

    # ── DEPLOY ───────────────────────────────────────────────
    _run_deploy(
        project_dir=project_dir,
        spec=spec,
        result=result,
        secrets=secrets,
        terraform_output_dir=terraform_output_dir,
        project_name=project_name,
    )


def _run_deploy(project_dir, spec, result, secrets, terraform_output_dir, project_name):
    import json
    from models import ServiceType
    from deployer.terraform import run_terraform_init, run_terraform_apply, get_output
    from deployer.docker import build_and_push
    from deployer.static import build_and_deploy

    state_dir = Path.home() / ".infragen" / "state" / project_name
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text(json.dumps({
        "terraform_dir": str(terraform_output_dir),
        "project_name": project_name,
        "mode": spec.mode.value,
        "region": spec.region,
        "service_type": result.service_type.value,
    }, indent=2))

    console.print()
    console.rule("[bold]Deploying[/bold]")

    try:
        run_terraform_init(terraform_output_dir)

        if result.service_type in (ServiceType.BACKEND_API, ServiceType.FRONTEND_SSR):
            run_terraform_apply(terraform_output_dir)
            ecr_url = get_output(terraform_output_dir, "ecr_repository_url")

            build_and_push(project_dir, spec.region, ecr_url)

            _push_secrets(secrets, project_name, spec.region)

            public_ip = get_output(terraform_output_dir, "app_public_ip")
            console.print()
            console.rule("[bold green]Deployment Complete[/bold green]")
            console.print()
            console.print(f"  [bold]Endpoint:[/bold]  http://{public_ip}:{result.port}")
            console.print(f"  [dim]The app may take 2-3 minutes to start while EC2 initializes.[/dim]")
            console.print()
            console.print(f"  [dim]To destroy:  infragen destroy[/dim]")

        else:
            # Static frontend
            run_terraform_apply(terraform_output_dir)

            _push_secrets(secrets, project_name, spec.region)

            bucket_name = get_output(terraform_output_dir, "s3_bucket_name")
            distribution_id = get_output(terraform_output_dir, "cloudfront_distribution_id")
            cloudfront_url = get_output(terraform_output_dir, "cloudfront_url")

            build_and_deploy(
                project_dir=project_dir,
                region=spec.region,
                build_command=result.build_command or "npm run build",
                build_output_dir=result.build_output_dir or "build",
                bucket_name=bucket_name,
                distribution_id=distribution_id,
            )

            console.print()
            console.rule("[bold green]Deployment Complete[/bold green]")
            console.print()
            console.print(f"  [bold]URL:[/bold]  https://{cloudfront_url}")
            console.print()
            console.print(f"  [dim]To destroy:  infragen destroy[/dim]")

    except RuntimeError as e:
        print_error(str(e))
        console.print()
        console.print("[dim]Cleaning up partial resources...[/dim]")
        try:
            from deployer.terraform import run_terraform_destroy
            run_terraform_destroy(terraform_output_dir)
            console.print("[dim]Partial resources removed. No charges incurred.[/dim]")
        except Exception:
            console.print("[dim]Could not auto-cleanup. Run: infragen destroy[/dim]")
        raise typer.Exit(code=1)


def _push_secrets(secrets: dict, project_name: str, region: str) -> None:
    if not secrets:
        return
    import boto3
    ssm = boto3.client("ssm", region_name=region)
    console.print("\n[dim]Pushing secrets to AWS SSM...[/dim]")
    pushed = 0
    for key, value in secrets.items():
        if not value:
            continue
        ssm.put_parameter(
            Name=f"/infragen/{project_name}/{key}",
            Value=value,
            Type="SecureString",
            Overwrite=True,
        )
        pushed += 1
    console.print(f"[green]✓[/green] {pushed} secret(s) stored in SSM")


@app.command()
def destroy():
    """Tear down all infrastructure for the current project."""
    import json
    from rich.prompt import Prompt

    project_name = Path.cwd().name.lower().replace(" ", "-").replace("_", "-")
    state_file = Path.home() / ".infragen" / "state" / project_name / "state.json"

    if not state_file.exists():
        print_error(f"No deployed state found for '{project_name}'.")
        print_error("Run this command from the same project directory you deployed from.")
        raise typer.Exit(code=1)

    state = json.loads(state_file.read_text())
    terraform_dir = Path(state["terraform_dir"])

    console.print()
    console.print(f"[bold red]This will destroy all infrastructure for '{project_name}'.[/bold red]")
    console.print(f"[dim]Region: {state['region']}  Mode: {state['mode']}[/dim]")
    console.print()

    confirmed = Prompt.ask("Type the project name to confirm")
    if confirmed != project_name:
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(code=0)

    from deployer.terraform import run_terraform_destroy
    try:
        run_terraform_destroy(terraform_dir)
        state_file.unlink(missing_ok=True)
        console.print()
        print_success("All infrastructure destroyed.")
    except RuntimeError as e:
        print_error(str(e))
        raise typer.Exit(code=1)


def _get_region() -> str:
    try:
        result = subprocess.run(
            ["aws", "configure", "get", "region"],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return ask_region()


def _print_infra_plan(spec, scan_result) -> None:
    from models import ServiceType, DeployMode

    if scan_result.service_type in (ServiceType.BACKEND_API, ServiceType.FRONTEND_SSR):
        if spec.mode == DeployMode.FREE:
            console.print(f"  EC2 {spec.instance_type:<12} 1 instance (free tier)")
            if spec.confirmed_rds:
                console.print(f"  RDS {spec.rds_instance_class:<12} {scan_result.rds_engine}, public subnet, SG-restricted")
            console.print(f"  Security Groups  app port {scan_result.port} open, RDS from EC2 only")
            console.print(f"  Elastic IP       1 static public IP")
            console.print(f"  ECR              1 repository")
            console.print(f"  SSM Parameters   {len(scan_result.env_vars)} parameters")
            console.print(f"  Key Pair         infragen-{spec.project_name}")
            if spec.confirmed_rds:
                console.print()
                console.print("  [yellow]⚠[/yellow]  RDS is in a public subnet (free tier limitation)")
                console.print("     It is only accessible from your EC2 instance via security group.")
                console.print("     Use --prod for private subnet deployment.")
        else:
            console.print(f"  ECS Fargate      0.5 vCPU / 1GB")
            if spec.confirmed_rds:
                console.print(f"  RDS {spec.rds_instance_class:<12} {scan_result.rds_engine}, private subnet")
            if spec.confirmed_elasticache:
                console.print(f"  ElastiCache      Redis cache.t3.micro")
            console.print(f"  ALB              Application Load Balancer")
            console.print(f"  VPC              dedicated VPC with public/private subnets")
            console.print(f"  NAT Gateway      private subnet outbound access")
            console.print(f"  ECR              1 repository")
            console.print(f"  SSM Parameters   {len(scan_result.env_vars)} parameters")
    else:
        console.print(f"  S3 bucket        static file hosting")
        console.print(f"  CloudFront       CDN distribution (always free)")
        console.print(f"  OAC              S3 access via CloudFront only")


if __name__ == "__main__":
    app()
