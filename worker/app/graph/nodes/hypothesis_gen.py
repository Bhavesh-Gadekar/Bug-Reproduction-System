"""[Hypothesis Generation] node — ask the LLM for a reproduction hypothesis.

This node is a factory: ``make_hypothesis_gen_node(llm)`` captures the LLM
client in a closure and returns the async node function.  Injecting the
client at graph-compile time makes it trivial to swap in a fake for tests.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.graph.llm import LLMClient
    from app.graph.state import BugReportState

logger = logging.getLogger(__name__)


def make_hypothesis_gen_node(llm: "LLMClient"):
    """
    Return an async LangGraph node that generates the next hypothesis.

    State updates returned:
    * ``current_hypothesis`` — the generated hypothesis text
    * ``hypothesis_index``   — incremented by 1 (used as retry counter and
                               as the primary key when indexing canned responses
                               in ``FakeLLMClient``)
    """

    async def hypothesis_gen_node(state: "BugReportState") -> dict[str, Any]:
        logger.info(
            "Generating hypothesis %d/%d for bug_report_id=%s",
            state.hypothesis_index + 1,
            state.max_hypotheses,
            state.bug_report_id,
        )
        hypothesis = await llm.generate_hypothesis(state)
        return {
            "current_hypothesis": hypothesis,
            # Increment AFTER generating so the LLM sees the pre-increment
            # value (matching how FakeLLMClient indexes its canned responses).
            "hypothesis_index": state.hypothesis_index + 1,
        }

    return hypothesis_gen_node
