"""[Repro Script Generation] node — turn the current hypothesis into runnable code."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.graph.llm import LLMClient
    from app.graph.state import BugReportState

logger = logging.getLogger(__name__)


def make_script_gen_node(llm: "LLMClient"):
    """
    Return an async LangGraph node that generates the reproduction script.

    Called after ``hypothesis_gen`` in every retry cycle.  By the time this
    node runs, ``state.hypothesis_index`` has already been incremented, so
    ``FakeLLMClient.generate_repro_script`` can use it to select the correct
    canned script for this iteration.
    """

    async def script_gen_node(state: "BugReportState") -> dict[str, Any]:
        logger.info(
            "Generating repro script (hypothesis_index=%d) for bug_report_id=%s",
            state.hypothesis_index,
            state.bug_report_id,
        )
        script = await llm.generate_repro_script(state)
        return {"current_script": script}

    return script_gen_node
