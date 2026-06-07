from pathlib import Path

from models import ScanResult
from scanner.detector import detect, DetectionError, UnsupportedFrameworkError
from scanner.ports import detect_port
from scanner.env_vars import scan_env_vars, MissingEnvExampleError
from scanner.dependencies import scan_dependencies
from scanner.dockfile import scan_dockerfile


def scan(project_dir: str | Path) -> ScanResult:
    project_dir = Path(project_dir)

    runtime, framework, service_type, version = detect(project_dir)

    port = detect_port(project_dir, framework, service_type)

    env_vars = scan_env_vars(project_dir)

    deps = scan_dependencies(project_dir, runtime)

    dockerfile = scan_dockerfile(
        project_dir=project_dir,
        framework=framework,
        port=port,
        runtime_version=version,
        django_project_name=_detect_django_project_name(project_dir, framework),
    )

    build_command, build_output_dir = _detect_build_info(framework,project_dir)
    start_command = _detect_start_command(framework, port, deps,project_dir)

    return ScanResult(
        runtime=runtime,
        framework=framework,
        service_type=service_type,
        runtime_version=version,
        port=port,
        has_dockerfile=dockerfile.exists,
        needs_rds=deps["needs_rds"],
        rds_engine=deps["rds_engine"],
        needs_elasticache=deps["needs_elasticache"],
        needs_s3=deps["needs_s3"],
        needs_ses=deps["needs_ses"],
        needs_sticky_sessions=deps["needs_sticky_sessions"],
        env_vars=env_vars,
        build_command=build_command,
        build_output_dir=build_output_dir,
        start_command=start_command,
        django_project_name=_detect_django_project_name(project_dir,framework),
        warnings=deps["warnings"],
        inferred_resources=deps["inferred_resources"],
    )


def _detect_django_project_name(project_dir: Path, framework) -> str | None:
    from models import Framework
    if framework != Framework.DJANGO:
        return None

    manage_py = project_dir / "manage.py"
    if not manage_py.exists():
        return None

    import re
    content = manage_py.read_text()
    match = re.search(r'["\'](\w+)\.settings["\']', content)
    if match:
        return match.group(1)

    return None


def _detect_build_info(framework, project_dir: Path) -> tuple[str | None, str | None]:
    from models import Framework

    if framework == Framework.REACT:
        pkg_path = project_dir / "package.json"
        if pkg_path.exists():
            import json
            pkg = json.loads(pkg_path.read_text())
            build_cmd = pkg.get("scripts", {}).get("build", "npm run build")
        else:
            build_cmd = "npm run build"

        if (project_dir / "vite.config.js").exists() or (project_dir /"vite.config.ts").exists():
            return build_cmd, "dist"
        return build_cmd, "build"

    if framework == Framework.NEXTJS:
        return "npm run build", ".next"

    return None, None


def _detect_start_command(framework, port: int | None, deps: dict, project_dir: Path) -> str | None:
    from models import Framework

    if framework == Framework.FASTAPI:
        return f"uvicorn main:app --host 0.0.0.0 --port {port or 8000}"

    if framework == Framework.FLASK:
        return f"gunicorn -w 4 -b 0.0.0.0:{port or 5000} app:app"

    if framework == Framework.DJANGO:
        return None

    if framework == Framework.EXPRESS:
        return None

    if framework == Framework.NEXTJS:
        return "npm start"

    return None