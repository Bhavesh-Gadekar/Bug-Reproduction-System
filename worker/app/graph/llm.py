"""LLM client protocol and stub implementation.

The ``LLMClient`` Protocol defines the interface every LLM backend must satisfy.
``FakeLLMClient`` provides canned responses indexed by ``hypothesis_index`` so
the full graph can be exercised end-to-end in tests without burning real API
tokens.

Design note
-----------
``hypothesis_gen`` increments ``state.hypothesis_index`` BEFORE returning
the updated state.  By the time ``script_gen`` is called, the index has
already advanced.  The ``FakeLLMClient`` therefore:

* ``generate_hypothesis`` uses ``state.hypothesis_index`` *before* increment
  (index == 0 on the first pass, 1 on the second, …)
* ``generate_repro_script`` uses ``state.hypothesis_index`` *after* increment
  (index == 1 on the first pass, 2 on the second, …)

Both are keyed so that the script content reflects which attempt is in
progress — the ``FakeSandboxClient`` (in sandbox.py) then produces matching
or non-matching stdout based on whether "AssertionError" appears in the script.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.graph.state import BugReportState


# ---------------------------------------------------------------------------
# Protocol (interface for real + fake implementations)
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMClient(Protocol):
    """Minimal interface required by hypothesis_gen and script_gen nodes."""

    async def generate_hypothesis(self, state: "BugReportState") -> str:
        """
        Given the current reproduction state, produce a natural-language
        hypothesis about what code change would trigger the reported bug.
        """
        ...

    async def generate_repro_script(self, state: "BugReportState") -> str:
        """
        Given the current hypothesis, produce a self-contained Python script
        that, when executed, should reproduce the bug and exit non-zero.
        """
        ...


# ---------------------------------------------------------------------------
# Fake implementation for tests (no API calls, deterministic output)
# ---------------------------------------------------------------------------

# Canned hypotheses returned by index (keyed by hypothesis_index BEFORE
# the increment in hypothesis_gen).
_HYPOTHESES: dict[int, str] = {
    0: (
        "First attempt: the bug may be caused by a type mismatch "
        "in the comparison — try raising a ValueError."
    ),
    1: (
        "Second attempt: the bug is an AssertionError when comparing "
        "expected vs actual values in the test."
    ),
}

# Canned scripts returned by index (keyed by hypothesis_index AFTER
# the increment in hypothesis_gen — i.e. 1-based).
# The FakeSandboxClient inspects the script text to decide the output:
#   script contains "AssertionError" → stdout reproduces the error (matched)
#   otherwise                        → stdout shows a different error (no_match)
_SCRIPTS: dict[int, str] = {
    1: (
        "# Attempt 1 — wrong error type, will not match the stack trace\n"
        "raise ValueError('Unexpected condition encountered')\n"
    ),
    2: (
        "# Attempt 2 — correct error, matches the raw_stack_trace signature\n"
        "raise AssertionError('Expected values to be equal')\n"
    ),
}

# Fallback for any index beyond what's explicitly canned.
_DEFAULT_SCRIPT = (
    "# Fallback script — always reproduces AssertionError\n"
    "raise AssertionError('Expected values to be equal')\n"
)


class FakeLLMClient:
    """
    Deterministic LLM stub for unit and integration tests.

    If ``match_on_first_attempt=True`` (default), returns an ``AssertionError``
    script immediately on the first iteration, satisfying single-pass tests.
    If ``match_on_first_attempt=False``, returns a ``ValueError`` script on the
    first iteration (producing a ``no_match`` verdict) and an ``AssertionError``
    script on the second iteration, testing the retry loop.
    """

    def __init__(self, match_on_first_attempt: bool = True):
        self.match_on_first_attempt = match_on_first_attempt

    async def generate_hypothesis(self, state: "BugReportState") -> str:
        idx = state.hypothesis_index  # BEFORE increment
        if self.match_on_first_attempt:
            return _HYPOTHESES.get(1, "Hypothesis attempt 1")
        return _HYPOTHESES.get(idx, f"Hypothesis attempt {idx}")

    async def generate_repro_script(self, state: "BugReportState") -> str:
        idx = state.hypothesis_index  # AFTER increment (hypothesis_gen already ran)
        if self.match_on_first_attempt:
            return _SCRIPTS.get(2, _DEFAULT_SCRIPT)
        return _SCRIPTS.get(idx, _DEFAULT_SCRIPT)
