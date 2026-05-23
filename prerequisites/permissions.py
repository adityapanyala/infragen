import boto3
from dataclasses import dataclass


REQUIRED_PERMISSIONS = [
    "ec2:CreateVpc",
    "ec2:CreateSubnet",
    "ec2:CreateSecurityGroup",
    "ec2:RunInstances",
    "ec2:AllocateAddress",
    "ec2:CreateKeyPair",
    "ecs:CreateCluster",
    "ecs:RegisterTaskDefinition",
    "ecs:CreateService",
    "rds:CreateDBInstance",
    "rds:CreateDBSubnetGroup",
    "s3:CreateBucket",
    "s3:PutObject",
    "s3:PutBucketPolicy",
    "cloudfront:CreateDistribution",
    "ssm:PutParameter",
    "ssm:GetParameter",
    "elasticloadbalancing:CreateLoadBalancer",
    "elasticloadbalancing:CreateTargetGroup",
    "ecr:CreateRepository",
    "ecr:GetAuthorizationToken",
    "iam:CreateRole",
    "iam:AttachRolePolicy",
    "iam:PassRole",
]


@dataclass
class PermissionResult:
    action: str
    allowed: bool


def check_permissions() -> list[PermissionResult]:
    try:
        iam = boto3.client("iam")
        sts = boto3.client("sts")

        identity = sts.get_caller_identity()
        arn = identity["Arn"]

        response = iam.simulate_principal_policy(
            PolicySourceArn=arn,
            ActionNames=REQUIRED_PERMISSIONS,
            ResourceArns=["*"],
        )

        results = []
        for evaluation in response["EvaluationResults"]:
            results.append(PermissionResult(
                action=evaluation["EvalActionName"],
                allowed=evaluation["EvalDecision"] == "allowed",
            ))

        return results

    except Exception as e:
        return [
            PermissionResult(
                action=f"Error checking permissions: {e}",
                allowed=False,
            )
        ]


def all_passed(results: list[PermissionResult]) -> bool:
    return all(r.allowed for r in results)


def failed_permissions(results: list[PermissionResult]) -> list[str]:
    return [r.action for r in results if not r.allowed]
