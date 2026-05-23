import re
from pathlib import Path

from models import Framework, ServiceType

FRAMEWORK_DEFAULT_PORTS = {
    Framework.FASTAPI: 8000,
    Framework.FLASK:   5000,
    Framework.DJANGO:  8000,
    Framework.EXPRESS: 3000,
    Framework.NEXTJS:  3000,
    Framework.REACT:   None,
}

def detect_port(project_dir: Path,framework: Framework,service_type: ServiceType,) -> int | None:
    project_dir = Path(project_dir)

    if service_type == ServiceType.FRONTEND_STATIC:
        return None

    port = _port_from_dockerfile(project_dir)
    if port:
        return port

    port = _port_from_env_example(project_dir)
    if port:
        return port

    port = _port_from_source(project_dir, framework)
    if port:
        return port

    return FRAMEWORK_DEFAULT_PORTS.get(framework)


def _port_from_dockerfile(project_dir: Path) -> int | None:
    dockerfile = project_dir / "Dockerfile"
    if not dockerfile.exists():
        return None

    content = dockerfile.read_text()
    match = re.search(r"^EXPOSE\s+(\d+)", content, re.MULTILINE)
    if match:
        return int(match.group(1))
    return None


def _port_from_env_example(project_dir: Path) -> int | None:
    env_example = project_dir / ".env.example"
    if not env_example.exists():
        return None

    content = env_example.read_text()
    match = re.search(r"^PORT=(\d+)", content, re.MULTILINE)
    if match:
        return int(match.group(1))
    return None


def _port_from_source(project_dir: Path, framework: Framework) -> int | None:
    if framework in (Framework.FASTAPI, Framework.FLASK,Framework.DJANGO):
        return _port_from_python_source(project_dir)

    if framework in (Framework.EXPRESS, Framework.NEXTJS):
        return _port_from_node_source(project_dir)

    return None


def _port_from_python_source(project_dir: Path) -> int | None:
    patterns = [r"uvicorn\.run\([^)]*port\s*=\s*(\d+)", r"app\.run\([^)]*port\s*=\s*(\d+)",]
    for py_file in project_dir.rglob("*.py"):
        try:
            content = py_file.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                return int(match.group(1))
    return None


def _port_from_node_source(project_dir: Path) -> int | None:
    patterns = [
        r"app\.listen\((\d+)",
        r"server\.listen\((\d+)",
    ]
    for ext in ("*.js", "*.ts", "*.mjs"):
        for js_file in project_dir.rglob(ext):
            if "node_modules" in js_file.parts:
                continue
            try:
                content = js_file.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    return int(match.group(1))
    return None