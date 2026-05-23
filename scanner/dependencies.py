import json
import re
from pathlib import Path

from models import Runtime, ScanResult


def scan_dependencies(project_dir: Path, runtime: Runtime) -> dict:
    project_dir = Path(project_dir)

    if runtime == Runtime.PYTHON:
        return _scan_python_deps(project_dir)

    return _scan_node_deps(project_dir)


def _scan_python_deps(project_dir: Path) -> dict:
    content = _read_requirements(project_dir).lower()
    packages = _parse_requirements(content)

    needs_rds = False
    rds_engine = None
    needs_elasticache = False
    needs_s3 = False
    needs_ses = False
    needs_sticky_sessions = False
    inferred = []
    warnings = []

    if any(p in packages for p in ("psycopg2", "psycopg2-binary", "asyncpg")):
        needs_rds = True
        rds_engine = "postgres"
        inferred.append("PostgreSQL (psycopg2/asyncpg in requirements.txt)")

    if any(p in packages for p in ("pymysql", "mysqlclient")):
        needs_rds = True
        rds_engine = "mysql"
        inferred.append("MySQL (pymysql/mysqlclient in requirements.txt)")

    if any(p in packages for p in ("redis", "aioredis")):
        needs_elasticache = True
        inferred.append("Redis (redis-py/aioredis in requirements.txt)")

    if "django-storages" in packages:
        needs_s3 = True
        inferred.append("S3 (django-storages in requirements.txt)")

    if any(p in packages for p in ("boto3", "botocore")):
        needs_s3 = True
        inferred.append("S3 (boto3 in requirements.txt)")

    if "celery" in packages:
        warnings.append("Background worker detected (celery) — not managed by infragen")

    if any(p in packages for p in ("gunicorn",)):
        pass

    return {
        "needs_rds": needs_rds,
        "rds_engine": rds_engine,
        "needs_elasticache": needs_elasticache,
        "needs_s3": needs_s3,
        "needs_ses": needs_ses,
        "needs_sticky_sessions": needs_sticky_sessions,
        "inferred_resources": inferred,
        "warnings": warnings,
    }


def _scan_node_deps(project_dir: Path) -> dict:
    pkg_path = project_dir / "package.json"
    pkg = json.loads(pkg_path.read_text())
    deps = {
        **pkg.get("dependencies", {}),
        **pkg.get("devDependencies", {}),
    }
    packages = set(deps.keys())

    needs_rds = False
    rds_engine = None
    needs_elasticache = False
    needs_s3 = False
    needs_ses = False
    needs_sticky_sessions = False
    inferred = []
    warnings = []

    if any(p in packages for p in ("pg", "postgres")):
        needs_rds = True
        rds_engine = "postgres"
        inferred.append("PostgreSQL (pg in package.json)")

    if any(p in packages for p in ("mysql2", "mysql")):
        needs_rds = True
        rds_engine = "mysql"
        inferred.append("MySQL (mysql2 in package.json)")

    if any(p in packages for p in ("ioredis", "redis")):
        needs_elasticache = True
        inferred.append("Redis (ioredis/redis in package.json)")

    if "multer" in packages:
        needs_s3 = True
        inferred.append("S3 (multer in package.json)")

    if "@aws-sdk/client-s3" in packages:
        needs_s3 = True
        inferred.append("S3 (@aws-sdk/client-s3 in package.json)")

    if "socket.io" in packages:
        needs_sticky_sessions = True
        inferred.append("Sticky sessions (socket.io in package.json)")

    if any(p in packages for p in ("bull", "bullmq")):
        warnings.append("Job queue detected (bull/bullmq) — not managed by infragen")

    if "nodemailer" in packages:
        needs_ses = True
        inferred.append("SES (nodemailer in package.json)")

    return {
        "needs_rds": needs_rds,
        "rds_engine": rds_engine,
        "needs_elasticache": needs_elasticache,
        "needs_s3": needs_s3,
        "needs_ses": needs_ses,
        "needs_sticky_sessions": needs_sticky_sessions,
        "inferred_resources": inferred,
        "warnings": warnings,
    }


def _read_requirements(project_dir: Path) -> str:
    for filename in ("requirements.txt", "Pipfile"):
        path = project_dir / filename
        if path.exists():
            return path.read_text()

    pyproject = project_dir / "pyproject.toml"
    if pyproject.exists():
        return pyproject.read_text()

    return ""


def _parse_requirements(content: str) -> set:
    packages = set()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[>=<!~\[]", line)[0].strip().lower()
        if name:
            packages.add(name)
    return packages


