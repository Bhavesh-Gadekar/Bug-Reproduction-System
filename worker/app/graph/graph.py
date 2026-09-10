"""LangGraph state machine assembly for bug reproduction.

Constructs the complete reproduction workflow graph:
START → ingest → repo_analysis → env_setup → hypothesis_gen → script_gen
      → sandbox_exec → verdict ──(matched)──→ minimization → persist → END
                              └──(retry, idx < max)──→ hypothesis_gen
                              └──(exhausted)──→ persist → END
"""

import functools
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.core.config import get_worker_settings
from app.graph.llm import FakeLLMClient, LLMClient
from app.graph.nodes.dependency_install import dependency_install_node
from app.graph.nodes.env_setup import env_setup_node
from app.graph.nodes.hypothesis_gen import make_hypothesis_gen_node
from app.graph.nodes.ingest import ingest_node
from app.graph.nodes.minimization import minimization_node
from app.graph.nodes.persist import persist_node
from app.graph.nodes.repo_analysis import repo_analysis_node
from app.graph.nodes.sandbox_exec import make_sandbox_exec_node
from app.graph.nodes.script_gen import make_script_gen_node
from app.graph.nodes.verdict import verdict_node
from app.graph.sandbox import RealSandboxClient, SandboxClient
from app.graph.state import BugReportState

logger = logging.getLogger("worker.graph")


def wrap_node_with_structured_log(node_name: str, node_fn: Any):
    """Wrap a graph node to emit structured JSON logs tagged with run_id and workspace_id."""
    @functools.wraps(node_fn)
    async def _wrapped(state: BugReportState, *args: Any, **kwargs: Any) -> Any:
        run_id = str(getattr(state, "run_id", "") or getattr(state, "bug_report_id", "") or "")
        workspace_id = str(getattr(state, "workspace_id", "") or "")
        hypothesis_idx = getattr(state, "hypothesis_index", 1)
        start_time = time.monotonic()

        # Emit start log
        start_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "INFO",
            "service": "worker",
            "event": "node_execution_start",
            "node": node_name,
            "run_id": run_id,
            "workspace_id": workspace_id,
            "hypothesis_index": hypothesis_idx,
        }
        logger.info(json.dumps(start_record))

        try:
            result = await node_fn(state, *args, **kwargs)
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            complete_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "INFO",
                "service": "worker",
                "event": "node_execution_complete",
                "node": node_name,
                "run_id": run_id,
                "workspace_id": workspace_id,
                "duration_ms": duration_ms,
                "hypothesis_index": hypothesis_idx,
                "status": "success",
            }
            if isinstance(result, dict):
                if "verdict" in result:
                    complete_record["verdict"] = result["verdict"]
                if "reproduced" in result:
                    complete_record["reproduced"] = result["reproduced"]
                if "final_verdict" in result:
                    complete_record["final_verdict"] = result["final_verdict"]
            logger.info(json.dumps(complete_record))
            return result
        except Exception as exc:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            error_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "ERROR",
                "service": "worker",
                "event": "node_execution_error",
                "node": node_name,
                "run_id": run_id,
                "workspace_id": workspace_id,
                "duration_ms": duration_ms,
                "hypothesis_index": hypothesis_idx,
                "error": str(exc),
                "status": "error",
            }
            logger.error(json.dumps(error_record))
            raise

    return _wrapped


def route_after_dependency_install(state: BugReportState) -> str:
    """
    Determine the next node after dependency_install.

    - If dependency installation failed (state.error is set): route directly to persist.
    - Otherwise: proceed to hypothesis_gen.
    """
    if state.error:
        logger.error(
            "Dependency installation failed for %s: %s. Routing to persist.",
            state.bug_report_id,
            state.error,
        )
        return "persist"
    return "hypothesis_gen"


def route_after_verdict(state: BugReportState) -> str:
    """
    Determine the next node after evaluation in verdict_node.

    - If reproduced: proceed to minimization.
    - If not reproduced and attempts remain: loop back to hypothesis_gen.
    - Otherwise (exhausted retries): persist terminal state and finish.
    """
    if state.final_verdict == "infra_error" or (state.last_execution_record and state.last_execution_record.verdict == "infra_error"):
        logger.error(
            "Infrastructure error encountered for %s during sandbox execution. Routing directly to persist.",
            state.bug_report_id,
        )
        return "persist"

    if state.reproduced:
        logger.info(
            "Bug reproduced for %s! Proceeding to minimization.",
            state.bug_report_id,
        )
        return "minimization"

    if state.hypothesis_index < state.max_hypotheses:
        logger.info(
            "Hypothesis attempt %d/%d did not reproduce for %s. Retrying...",
            state.hypothesis_index,
            state.max_hypotheses,
            state.bug_report_id,
        )
        return "hypothesis_gen"

    logger.info(
        "Max hypotheses (%d) reached for %s without reproduction. Persisting...",
        state.max_hypotheses,
        state.bug_report_id,
    )
    return "persist"


def make_graph(
    llm: LLMClient | None = None,
    sandbox: SandboxClient | None = None,
    checkpointer: Any | None = None,
    timeout_seconds: int | None = None,
):
    """
    Build and compile the LangGraph bug-reproduction state graph.

    Args:
        llm: LLM client interface (defaults to FakeLLMClient).
        sandbox: Sandbox client interface (defaults to RealSandboxClient).
        checkpointer: LangGraph checkpointer instance (e.g. AsyncPostgresSaver or MemorySaver).
        timeout_seconds: Timeout per sandbox container run.
    """
    settings = get_worker_settings()
    llm_client = llm or FakeLLMClient()
    sandbox_client = sandbox or RealSandboxClient(settings.SANDBOX_URL)
    exec_timeout = timeout_seconds or settings.SANDBOX_TIMEOUT_SECONDS

    builder = StateGraph(BugReportState)

    def add_wrapped_node(name: str, fn: Any):
        builder.add_node(name, wrap_node_with_structured_log(name, fn))

    # 1. Register nodes with structured JSON logging wrapper
    add_wrapped_node("ingest", ingest_node)
    add_wrapped_node("repo_analysis", repo_analysis_node)
    add_wrapped_node("env_setup", env_setup_node)
    add_wrapped_node("dependency_install", dependency_install_node)
    add_wrapped_node("hypothesis_gen", make_hypothesis_gen_node(llm_client))
    add_wrapped_node("script_gen", make_script_gen_node(llm_client))
    add_wrapped_node("sandbox_exec", make_sandbox_exec_node(sandbox_client, timeout_seconds=exec_timeout))
    add_wrapped_node("verdict", verdict_node)
    add_wrapped_node("minimization", minimization_node)
    add_wrapped_node("persist", persist_node)

    # 2. Register linear edges
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "repo_analysis")
    builder.add_edge("repo_analysis", "env_setup")
    builder.add_edge("env_setup", "dependency_install")

    builder.add_conditional_edges(
        "dependency_install",
        route_after_dependency_install,
        {
            "hypothesis_gen": "hypothesis_gen",
            "persist": "persist",
        },
    )

    builder.add_edge("hypothesis_gen", "script_gen")
    builder.add_edge("script_gen", "sandbox_exec")
    builder.add_edge("sandbox_exec", "verdict")

    # 3. Register conditional routing after verdict
    builder.add_conditional_edges(
        "verdict",
        route_after_verdict,
        {
            "minimization": "minimization",
            "hypothesis_gen": "hypothesis_gen",
            "persist": "persist",
        },
    )

    # 4. Terminal path edges
    builder.add_edge("minimization", "persist")
    builder.add_edge("persist", END)

    return builder.compile(checkpointer=checkpointer)
