from dataclasses import dataclass, field
from .enums import Runtime, Framework, ServiceType


@dataclass
class ScanResult:

    runtime: Runtime
    framework: Framework
    service_type: ServiceType
    runtime_version: str
    port: int | None
    has_dockerfile: bool

    needs_rds: bool
    rds_engine: str | None
    needs_elasticache: bool
    needs_s3: bool
    needs_ses: bool
    needs_sticky_sessions: bool

    env_vars: dict[str, str]

    build_command: str | None
    build_output_dir: str | None

    start_command: str | None

    django_project_name: str | None

    warnings: list[str] = field(default_factory=list)
    inferred_resources: list[str] = field(default_factory=list)
