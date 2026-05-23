import re
from pathlib import Path


SECRET_KEYWORDS = (
    "SECRET", "KEY", "PASSWORD", "TOKEN",
    "PRIVATE", "CREDENTIAL", "AUTH",
)

CONFIG_KEYWORDS = (
    "URL", "HOST", "DATABASE", "REDIS", "URI",
    "ENDPOINT", "BUCKET", "PORT",
)

RUNTIME_CONFIG_KEYS = (
    "NODE_ENV", "DEBUG", "ENVIRONMENT", "APP_ENV",
)


class MissingEnvExampleError(Exception):
    pass


def scan_env_vars(project_dir: Path) -> dict[str, str]:
    project_dir = Path(project_dir)
    env_example = project_dir / ".env.example"

    if not env_example.exists():
        _raise_missing_error(project_dir)

    content = env_example.read_text()
    result = {}

    for line in content.splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key = line.split("=", 1)[0].strip()

        if not key:
            continue

        result[key] = _classify(key)

    return result


def _classify(key: str) -> str:
    upper = key.upper()

    if upper in RUNTIME_CONFIG_KEYS:
        return "runtime_config"

    if any(kw in upper for kw in SECRET_KEYWORDS):
        return "secret"

    if any(kw in upper for kw in CONFIG_KEYWORDS):
        return "config"

    return "unknown"


def _raise_missing_error(project_dir: Path) -> None:
    env_file = project_dir / ".env"

    if env_file.exists():
        raise MissingEnvExampleError(
            "No .env.example found.\n"
            "We found a .env file but will not read it (contains real secrets).\n"
            "Create .env.example with your variable names and empty values:\n\n"
            "  DATABASE_URL=\n"
            "  SECRET_KEY=\n"
            "  REDIS_URL=\n\n"
            "Then run infragen deploy again."
        )

    raise MissingEnvExampleError(
        "No .env.example found.\n"
        "Create one in your project root listing all environment variables\n"
        "your app needs, with empty values:\n\n"
        "  DATABASE_URL=\n"
        "  SECRET_KEY=\n\n"
        "Then run infragen deploy again."
    )