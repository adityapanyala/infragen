import re
from dataclasses import dataclass
from pathlib import Path

from rich.table import Table


MONTHLY_PRICES = {
    "aws_instance":                 8.47,
    "aws_db_instance":             25.55,
    "aws_elasticache_cluster":     12.41,
    "aws_lb":                      16.20,
    "aws_nat_gateway":             32.40,
    "aws_ecr_repository":           1.00,
    "aws_ecs_service":             14.82,
    "aws_s3_bucket":                0.00,
    "aws_cloudfront_distribution":  0.00,
}

FREE_TIER_RESOURCES = {
    "aws_instance",
    "aws_db_instance",
    "aws_s3_bucket",
    "aws_cloudfront_distribution",
    "aws_ecr_repository",
}

DISPLAY_NAMES = {
    "aws_instance":                 "EC2 Instance",
    "aws_db_instance":              "RDS Database",
    "aws_elasticache_cluster":      "ElastiCache (Redis)",
    "aws_lb":                       "Load Balancer (ALB)",
    "aws_nat_gateway":              "NAT Gateway",
    "aws_ecr_repository":           "ECR Repository",
    "aws_ecs_service":              "ECS Fargate",
    "aws_s3_bucket":                "S3 Bucket",
    "aws_cloudfront_distribution":  "CloudFront CDN",
    "aws_ssm_parameter":            "SSM Parameters",
}

HIDDEN_TYPES = {
    "aws_lb_target_group", "aws_lb_listener", "aws_iam_role",
    "aws_iam_role_policy_attachment", "aws_iam_role_policy",
    "aws_security_group", "aws_vpc", "aws_subnet", "aws_route_table",
    "aws_route_table_association", "aws_internet_gateway", "aws_eip",
    "aws_ecs_cluster", "aws_ecs_task_definition", "aws_cloudwatch_log_group",
    "aws_ecr_lifecycle_policy",
}


@dataclass
class CostLineItem:
    resource_type: str
    display_name: str
    monthly_cost: float
    is_free_tier: bool = False
    note: str = ""


def run_cost_estimate(terraform_dir: Path, mode: str = "free") -> list[CostLineItem]:
    resources = _parse_tf_resources(terraform_dir)
    return _calculate_costs(resources, mode)


def _parse_tf_resources(terraform_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tf_file in terraform_dir.glob("*.tf"):
        content = tf_file.read_text()
        for resource_type, _ in re.findall(r'resource\s+"(aws_\w+)"\s+"(\w+)"', content):
            counts[resource_type] = counts.get(resource_type, 0) + 1
    return counts


def _calculate_costs(counts: dict[str, int], mode: str) -> list[CostLineItem]:
    items = []

    for resource_type, count in counts.items():
        if resource_type in HIDDEN_TYPES:
            continue

        monthly_cost = MONTHLY_PRICES.get(resource_type, 0.0)
        is_free = mode == "free" and resource_type in FREE_TIER_RESOURCES

        if monthly_cost == 0.0 and not is_free and resource_type not in DISPLAY_NAMES:
            continue

        name = DISPLAY_NAMES.get(resource_type, resource_type)
        if resource_type == "aws_ssm_parameter":
            name = f"SSM Parameters ({count})"

        note = ""
        if is_free:
            note = "free tier (12 months)"
        elif resource_type == "aws_nat_gateway":
            note = "largest cost — consider VPC endpoints for dev"
        elif resource_type == "aws_db_instance" and mode == "prod":
            note = "reserved instance saves ~30%"
        elif resource_type in {"aws_instance", "aws_db_instance"} and not is_free:
            note = f"~${MONTHLY_PRICES[resource_type]:.2f}/mo after free tier"

        items.append(CostLineItem(
            resource_type=resource_type,
            display_name=name,
            monthly_cost=0.0 if is_free else monthly_cost,
            is_free_tier=is_free,
            note=note,
        ))

    items.sort(key=lambda i: -i.monthly_cost)
    return items


def format_cost_table(items: list[CostLineItem]) -> Table:
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Resource", min_width=28)
    table.add_column("Monthly Cost", justify="right", min_width=14)
    table.add_column("Note", style="dim")

    total = 0.0
    for item in items:
        cost_str = "[dim]free[/dim]" if item.is_free_tier else (
            "[dim]$0.00[/dim]" if item.monthly_cost == 0.0 else f"${item.monthly_cost:.2f}"
        )
        table.add_row(item.display_name, cost_str, item.note)
        total += item.monthly_cost

    table.add_section()
    total_str = "[green]$0.00 / month[/green]" if total == 0.0 else f"[bold]${total:.2f} / month[/bold]"
    table.add_row("[bold]Total[/bold]", total_str, "")

    return table


def get_total_cost(items: list[CostLineItem]) -> float:
    return sum(i.monthly_cost for i in items)
