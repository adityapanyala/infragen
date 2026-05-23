import re
from pathlib import Path

from models import Framework


TEMPLATE_DIR = Path(__file__).parent.parent / "docker_templates"


class DockerfileParseResult:
    def __init__(
        self,
        exists: bool,
        port: int | None = None,
        runs_as_root: bool = False,
        has_healthcheck: bool = False,
        base_image: str | None = None,
        generated_content: str | None = None,
    ):
        self.exists = exists
        self.port = port
        self.runs_as_root = runs_as_root
        self.has_healthcheck = has_healthcheck
        self.base_image = base_image
        self.generated_content = generated_content


def scan_dockerfile(
    project_dir: Path,
    framework: Framework,
    port: int | None,
    runtime_version: str,
    django_project_name: str | None = None,
) -> DockerfileParseResult:
    project_dir = Path(project_dir)
    dockerfile_path = project_dir / "Dockerfile"

    if dockerfile_path.exists():
        return _parse_existing(dockerfile_path)

    return _generate(framework, port, runtime_version, django_project_name)


def _parse_existing(dockerfile_path: Path) -> DockerfileParseResult:
    content = dockerfile_path.read_text()

    port = None
    expose_match = re.search(r"^EXPOSE\s+(\d+)", content, re.MULTILINE)
    if expose_match:
        port = int(expose_match.group(1))

    runs_as_root = "USER " not in content

    has_healthcheck = "HEALTHCHECK" in content

    base_image = None
    from_match = re.search(r"^FROM\s+(\S+)", content, re.MULTILINE)
    if from_match:
        base_image = from_match.group(1)

    return DockerfileParseResult(
        exists=True,
        port=port,
        runs_as_root=runs_as_root,
        has_healthcheck=has_healthcheck,
        base_image=base_image,
    )


def _generate(
    framework: Framework,
    port: int | None,
    runtime_version: str,
    django_project_name: str | None,
) -> DockerfileParseResult:
    template_map = {
        Framework.FASTAPI: "fastapi.dockerfile",
        Framework.FLASK:   "flask.dockerfile",
        Framework.DJANGO:  "django.dockerfile",
        Framework.EXPRESS: "express.dockerfile",
        Framework.NEXTJS:  "nextjs.dockerfile",
    }

    template_name = template_map.get(framework)
    if not template_name:
        return DockerfileParseResult(exists=False)

    template_path = TEMPLATE_DIR / template_name
    if not template_path.exists():
        return DockerfileParseResult(exists=False)

    content = template_path.read_text()

    port = port or _default_port(framework)
    content = content.replace("{port}", str(port))
    content = content.replace("{version}", runtime_version)

    if framework == Framework.DJANGO and django_project_name:
        content = content.replace("{project_name}", django_project_name)

    if framework == Framework.FASTAPI:
        content = content.replace("{module}", "main")

    if framework == Framework.FLASK:
        content = content.replace("{module}", "app")

    if framework == Framework.EXPRESS:
        content = content.replace("{entrypoint}", "index.js")

    return DockerfileParseResult(
        exists=False,
        port=port,
        runs_as_root=False,
        has_healthcheck=True,
        generated_content=content,
    )


def _default_port(framework: Framework) -> int:
    defaults = {
        Framework.FASTAPI: 8000,
        Framework.FLASK:   5000,
        Framework.DJANGO:  8000,
        Framework.EXPRESS: 3000,
        Framework.NEXTJS:  3000,
    }
    return defaults.get(framework, 8000)