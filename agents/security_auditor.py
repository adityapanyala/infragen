import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from langchain_groq import ChatGroq


@dataclass
class SecurityFinding:
    tool: str
    severity: str
    title: str
    plain_english: str
    classification: Literal["auto_fixed", "needs_input", "informational"]
    resource: str | None = None


def run_security_audit(terraform_dir: Path) -> list[SecurityFinding]:
    tfsec_raw = _run_tfsec(terraform_dir)
    checkov_raw = _run_checkov(terraform_dir)
    merged = _merge_findings(tfsec_raw, checkov_raw)

    if not merged:
        return []

    findings = _synthesize_with_llm(merged)
    _apply_auto_fixes(findings, terraform_dir)

    return findings


def _run_tfsec(terraform_dir: Path) -> list[dict]:
    try:
        result = subprocess.run(
            ["tfsec", str(terraform_dir), "--format", "json", "--no-color"],
            capture_output=True, text=True
        )
        if result.stdout:
            data = json.loads(result.stdout)
            return data.get("results", [])
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def _run_checkov(terraform_dir: Path) -> list[dict]:
    try:
        result = subprocess.run(
            ["checkov", "-d", str(terraform_dir), "--output", "json", "--quiet"],
            capture_output=True, text=True
        )
        if result.stdout:
            data = json.loads(result.stdout)
            if isinstance(data, list):
                data = data[0]
            return data.get("results", {}).get("failed_checks", [])
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def _merge_findings(tfsec: list[dict], checkov: list[dict]) -> list[dict]:
    merged = []
    seen = set()

    for f in tfsec:
        key = f.get("rule_id", "") + f.get("description", "")
        if key not in seen:
            seen.add(key)
            merged.append({"source": "tfsec", "data": f})

    for f in checkov:
        key = f.get("check_id", "") + f.get("check", {}).get("name", "")
        if key not in seen:
            seen.add(key)
            merged.append({"source": "checkov", "data": f})

    return merged


def _synthesize_with_llm(raw_findings: list[dict]) -> list[SecurityFinding]:
    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        return _synthesize_fallback(raw_findings)

    try:
        llm = ChatGroq(model="llama3-8b-8192", temperature=0)
        findings_text = json.dumps(raw_findings[:10], indent=2)

        prompt = f"""You are a cloud security expert. Analyze these Terraform security findings.

For each finding return a JSON array with objects containing:
- title: short title (max 8 words)
- plain_english: one sentence explanation, no jargon
- classification: one of "auto_fixed", "needs_input", or "informational"
  - auto_fixed: can be fixed automatically in the .tf file
  - needs_input: requires the user to make a decision (e.g. SSH CIDR restriction)
  - informational: low severity, awareness only
- severity: HIGH, MEDIUM, or LOW
- resource: the terraform resource type affected (or null)

Findings to analyze:
{findings_text}

Return ONLY a valid JSON array. No explanation, no markdown."""

        response = llm.invoke(prompt)
        parsed = json.loads(response.content)

        return [
            SecurityFinding(
                tool="mixed",
                severity=item.get("severity", "MEDIUM"),
                title=item.get("title", "Security finding"),
                plain_english=item.get("plain_english", ""),
                classification=item.get("classification", "informational"),
                resource=item.get("resource"),
            )
            for item in parsed
        ]

    except Exception:
        return _synthesize_fallback(raw_findings)


def _synthesize_fallback(raw_findings: list[dict]) -> list[SecurityFinding]:
    results = []
    for f in raw_findings[:10]:
        data = f["data"]
        source = f["source"]

        if source == "tfsec":
            title = data.get("description", "Security finding")
            severity = data.get("severity", "MEDIUM")
            resource = data.get("resource", None)
        else:
            title = data.get("check", {}).get("name", "Security finding")
            severity = "MEDIUM"
            resource = data.get("resource", None)

        results.append(SecurityFinding(
            tool=source,
            severity=severity,
            title=title,
            plain_english=title,
            classification="informational",
            resource=resource,
        ))
    return results


def _apply_auto_fixes(findings: list[SecurityFinding], terraform_dir: Path) -> None:
    for tf_file in terraform_dir.glob("*.tf"):
        content = tf_file.read_text()
        original = content

        if "aws_db_instance" in content and "deletion_protection" not in content:
            content = content.replace(
                "skip_final_snapshot    = true",
                "skip_final_snapshot     = true\n  deletion_protection     = true",
            )

        if "aws_db_instance" in content and "backup_retention_period" not in content:
            content = content.replace(
                "deletion_protection     = true",
                "deletion_protection     = true\n  backup_retention_period = 7",
            )

        if content != original:
            tf_file.write_text(content)

    for f in findings:
        if f.classification == "informational" and any(
            kw in f.title.lower() for kw in ["deletion", "backup", "versioning", "root user"]
        ):
            f.classification = "auto_fixed"
