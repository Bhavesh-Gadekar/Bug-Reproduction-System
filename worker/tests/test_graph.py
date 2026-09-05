"""End-to-end unit and integration tests for the LangGraph reproduction state machine.

Exercises:
1. Happy path: FakeLLMClient matches on the first hypothesis attempt.
2. Retry loop: FakeLLMClient produces a non-matching script on attempt 1, then a
   matching script on attempt 2. Asserts retry loopback, execution history accumulation,
   and hypothesis index progression.
3. Exhausted retries: Max hypotheses reached without reproduction.
"""

from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.graph.graph import make_graph
from app.graph.llm import FakeLLMClient
from app.graph.sandbox import FakeSandboxClient


def _make_bug_report_input(max_hypotheses: int = 5, bug_id: str = "bug-123") -> dict:
    return {
        "bug_report_id": bug_id,
        "workspace_id": "ws-456",
        "title": "AssertionError in calculation",
        "description": "calc(2, 2) raised AssertionError instead of returning 4",
        "raw_stack_trace": (
            "Traceback (most recent call last):\n"
            '  File "test_calc.py", line 10, in test_calc\n'
            "    assert calc(2, 2) == 4\n"
            "AssertionError: Expected values to be equal\n"
        ),
        "repo": {
            "git_url": "https://github.com/example/repo",
            "branch": "main",
        },
        "max_hypotheses": max_hypotheses,
    }


@pytest.mark.asyncio
async def test_graph_happy_path():
    """Verify single-pass reproduction where first hypothesis matches immediately."""
    llm = FakeLLMClient(match_on_first_attempt=True)
    sandbox = FakeSandboxClient()
    checkpointer = MemorySaver()

    graph = make_graph(llm=llm, sandbox=sandbox, checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "happy-path-thread"}}
    initial_input = _make_bug_report_input(max_hypotheses=5, bug_id="happy-bug")

    final_state = await graph.ainvoke(initial_input, config=config)

    assert final_state["reproduced"] is True
    assert final_state["hypothesis_index"] == 1
    assert len(final_state["execution_history"]) == 1
    assert final_state["execution_history"][0].verdict == "matched"
    assert final_state["execution_history"][0].exit_code == 1
    assert "AssertionError" in final_state["execution_history"][0].stdout
    assert final_state["minimized_script"] != ""
    assert final_state["final_verdict"] in ("matched", "succeeded")


@pytest.mark.asyncio
async def test_graph_retry_loop():
    """
    Verify the retry loop:
    1. First attempt returns a script that produces ValueError (verdict: no_match).
    2. Graph routes back to hypothesis_gen.
    3. Second attempt produces a script that produces AssertionError (verdict: matched).
    4. Graph routes to minimization -> persist -> END.
    """
    llm = FakeLLMClient(match_on_first_attempt=False)
    sandbox = FakeSandboxClient()
    checkpointer = MemorySaver()

    graph = make_graph(llm=llm, sandbox=sandbox, checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "retry-loop-thread"}}
    initial_input = _make_bug_report_input(max_hypotheses=3, bug_id="retry-bug")

    final_state = await graph.ainvoke(initial_input, config=config)

    # 1. Assert loopback occurred and hypothesis_index incremented twice
    assert final_state["hypothesis_index"] == 2

    # 2. Assert execution_history accumulated exactly 2 records
    history = final_state["execution_history"]
    assert len(history) == 2

    # 3. Assert first record was a no_match and second was matched
    assert history[0].hypothesis_index == 1
    assert history[0].verdict == "no_match"
    assert "ValueError" in history[0].stdout

    assert history[1].hypothesis_index == 2
    assert history[1].verdict == "matched"
    assert "AssertionError" in history[1].stdout

    # 4. Assert terminal state
    assert final_state["reproduced"] is True
    assert final_state["final_verdict"] in ("matched", "succeeded")
    assert final_state["minimized_script"] != ""


@pytest.mark.asyncio
async def test_graph_retries_exhausted():
    """Verify graph terminates cleanly at persist when max_hypotheses is reached without match."""
    class NeverMatchingLLM(FakeLLMClient):
        async def generate_repro_script(self, state):
            return "raise RuntimeError('Different error entirely')\n"

    llm = NeverMatchingLLM()
    sandbox = FakeSandboxClient()
    checkpointer = MemorySaver()

    graph = make_graph(llm=llm, sandbox=sandbox, checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "exhausted-thread"}}
    initial_input = _make_bug_report_input(max_hypotheses=2, bug_id="exhausted-bug")

    final_state = await graph.ainvoke(initial_input, config=config)

    assert final_state["reproduced"] is False
    assert final_state["hypothesis_index"] == 2
    assert len(final_state["execution_history"]) == 2
    assert final_state["execution_history"][0].verdict == "no_match"
    assert final_state["execution_history"][1].verdict == "no_match"
    assert final_state["final_verdict"] == "failed"
