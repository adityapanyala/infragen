from dataclasses import dataclass
from pathlib import Path
from .enums import DeployMode
from .scan_result import ScanResult


@dataclass
class InfraSpec:
    scan: ScanResult

    mode: DeployMode
    user_description: str
    region: str
    project_name: str
    environment: str

    instance_type: str
    rds_instance_class: str

    confirmed_rds: bool
    confirmed_elasticache: bool
    confirmed_s3: bool

    backend_api_url: str | None

    terraform_output_dir: Path