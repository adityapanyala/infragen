import concurrent.futures
from pathlib import Path
from typing import TypedDict

from langgraph.graph import StateGraph, END, START

from models import InfraSpec
from agents.terraform_writer import run_terraform_writer
from agents.security_auditor import run_security_audit, SecurityFinding
from agents.cost_estimator import run_cost_estimate, CostLineItem


class PipelineState(TypedDict):
    spec: InfraSpec
    terraform_output_dir: Path | None
    security_findings: list[SecurityFinding] | None
    cost_items: list[CostLineItem] | None
    error: str | None


def _terraform_node(state: PipelineState) -> PipelineState:
    try:
        output_dir = run_terraform_writer(state["spec"])
        return {**state, "terraform_output_dir": output_dir}
    except Exception as e:
        return {**state, "error": f"Terraform generation failed: {e}"}


def _analysis_node(state: PipelineState) -> PipelineState:
    if state.get("error"):
        return state

    terraform_dir = state["terraform_output_dir"]
    mode = state["spec"].mode.value

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        sec_future = executor.submit(run_security_audit, terraform_dir)
        cost_future = executor.submit(run_cost_estimate, terraform_dir, mode)
        security_findings = sec_future.result()
        cost_items = cost_future.result()

    return {
        **state,
        "security_findings": security_findings,
        "cost_items": cost_items,
    }


def _build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("terraform", _terraform_node)
    graph.add_node("analysis", _analysis_node)

    graph.add_edge(START, "terraform")
    graph.add_edge("terraform", "analysis")
    graph.add_edge("analysis", END)

    return graph.compile()


def run_pipeline(spec: InfraSpec) -> PipelineState:
    pipeline = _build_graph()

    initial: PipelineState = {
        "spec": spec,
        "terraform_output_dir": None,
        "security_findings": None,
        "cost_items": None,
        "error": None,
    }

    return pipeline.invoke(initial)
