import json
import re
from pathlib import Path
from models import Runtime, Framework, ServiceType, ScanResult

class DetectionError(Exception):
    pass

class UnsupportedFrameworkError(Exception):
    pass

def detect(project_dir : Path) -> tuple[Runtime, Framework, ServiceType, str]:
    project_dir = Path(project_dir)
    
    has_package_json = (project_dir / "package.json").exists()
    has_requirements = (
        (project_dir / "requirements.txt").exists()
        or (project_dir / "pyproject.toml").exists()
        or (project_dir / "Pipfile").exists()
    )
    if not has_package_json and not has_requirements:
        raise DetectionError(
            "No package.json or requirements.txt found.\n"
            "Make sure you are running infragen from your project root"
        )
    
    runtime = _detect_runtime(project_dir, has_package_json, has_requirements)
    framework = _detect_framework(project_dir, runtime)
    service_type = _detect_service_type(framework, project_dir)
    version = _detect_version(runtime)

    return runtime, framework, service_type, version

def _detect_runtime(project_dir: Path, has_package_json: bool, has_requirements: bool) -> Runtime:

    if has_package_json and has_requirements:
        pkg = json.loads((project_dir/"package.json").read_text())
        all_deps = {
            **pkg.get("dependencies", {}),
            **pkg.get("devDependencies", {}),
        }
        if any(k in all_deps for k in ("next", "react", "express")):
            return Runtime.NODEJS
        return Runtime.PYTHON

    if has_package_json:
        return Runtime.NODEJS

    return Runtime.PYTHON

def _detect_framework(project_dir: Path, runtime: Runtime) -> Framework:
    if runtime == Runtime.NODEJS:
        pkg = json.loads((project_dir / "package.json").read_text())
        deps = {
            **pkg.get("dependencies", {}),
            **pkg.get("devDependencies", {}),
        }
        if "next" in deps:
            return Framework.NEXTJS
        if "react" in deps:
            return Framework.REACT
        if "express" in deps:
            return Framework.EXPRESS
        raise UnsupportedFrameworkError(
            f"No supported Node.js framework found in package.json.\n"
            f"Supported: next, react, express\n"
            f"Found deps: {list(deps.keys())}"
        )

    content = _read_python_deps(project_dir).lower()
    if "fastapi" in content:
        return Framework.FASTAPI
    if "django" in content:
        return Framework.DJANGO
    if "flask" in content:
        return Framework.FLASK
    raise UnsupportedFrameworkError(
        "No supported Python framework found in requirements.\n"
        "Supported: fastapi, django, flask"
    )

def _detect_service_type(framework: Framework, project_dir: Path) -> ServiceType:
    if framework in (Framework.FASTAPI, Framework.FLASK, Framework.DJANGO,Framework.EXPRESS):
        return ServiceType.BACKEND_API

    if framework == Framework.REACT:
        return ServiceType.FRONTEND_STATIC
    for config_name in ("next.config.js", "next.config.ts","next.config.mjs"):
        config_path = project_dir / config_name
        if config_path.exists():
            content = config_path.read_text()
            if "output" in content and "export" in content:
                return ServiceType.FRONTEND_STATIC
            break

    return ServiceType.FRONTEND_SSR


def _detect_version(runtime: Runtime) -> str:
    import subprocess
    try:
        if runtime == Runtime.PYTHON:
            result = subprocess.run(["python", "--version"],capture_output=True, text=True)
            match = re.search(r"(\d+\.\d+)", result.stdout + result.stderr)
            return match.group(1) if match else "unknown"

        result = subprocess.run(["node", "--version"],capture_output=True, text=True)
        match = re.search(r"v?(\d+\.\d+)", result.stdout)
        return match.group(1) if match else "unknown"

    except FileNotFoundError:
        return "unknown"


def _read_python_deps(project_dir: Path) -> str:
    for filename in ("requirements.txt", "Pipfile"):
        path = project_dir / filename
        if path.exists():
            return path.read_text()

    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        return pyproject.read_text()

    return ""