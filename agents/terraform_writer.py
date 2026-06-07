from pathlib import Path
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from models import InfraSpec, ServiceType, DeployMode


TEMPLATE_BASE = Path(__file__).parent.parent / "terraform"


def run_terraform_writer(spec: InfraSpec) -> Path:
    template_dir = _select_template_dir(spec)
    output_dir = spec.terraform_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    context = _build_context(spec)

    for template_name in env.list_templates():
        template = env.get_template(template_name)
        rendered = template.render(**context)

        output_filename = template_name.replace(".jinja", "")
        output_path = output_dir / output_filename
        output_path.write_text(rendered)

    return output_dir


def _select_template_dir(spec: InfraSpec) -> Path:
    mode = "free" if spec.mode == DeployMode.FREE else "prod"

    if spec.scan.service_type == ServiceType.BACKEND_API:
        service = "backend"
    elif spec.scan.service_type == ServiceType.FRONTEND_SSR:
        service = "backend"
    else:
        service = "frontend"

    return TEMPLATE_BASE / mode / service


def _build_context(spec: InfraSpec) -> dict:
    scan = spec.scan

    secret_vars = {
        k: v for k, v in scan.env_vars.items() if v == "secret"
    }
    config_vars = {
        k: v for k, v in scan.env_vars.items() if v in ("config", "runtime_config", "unknown")
    }

    return {
        "project_name":       spec.project_name,
        "environment":        spec.environment,
        "region":             spec.region,
        "framework":          scan.framework.value,
        "runtime":            scan.runtime.value,
        "runtime_version":    scan.runtime_version,
        "port":               scan.port or 8000,
        "instance_type":      spec.instance_type,
        "rds_instance_class": spec.rds_instance_class,
        "rds_engine":         scan.rds_engine or "postgres",
        "needs_rds":          scan.needs_rds and spec.confirmed_rds,
        "needs_elasticache":  scan.needs_elasticache and spec.confirmed_elasticache,
        "needs_s3":           scan.needs_s3 and spec.confirmed_s3,
        "secret_vars":        list(secret_vars.keys()),
        "config_vars":        list(config_vars.keys()),
        "start_command":      scan.start_command or "",
        "build_output_dir":   scan.build_output_dir or "build",
        "mode":               spec.mode.value,
        "backend_api_url":    spec.backend_api_url or "",
    }
