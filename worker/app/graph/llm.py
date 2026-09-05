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


# ---------------------------------------------------------------------------
# Real Gemini 2.5 Flash implementation
# ---------------------------------------------------------------------------


class GeminiLLMClient:
    """
    Production LLM client implementation wrapping Google Gemini 2.5 Flash.

    Conforms to the LLMClient protocol and logs all calls (prompt version,
    model version, tokens, latency) into the run_steps table via app.db.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 45.0,
        max_retries: int = 5,
    ):
        import logging
        from app.core.config import get_worker_settings

        self.logger = logging.getLogger(__name__)
        settings = get_worker_settings()
        self.api_key = api_key or settings.GEMINI_API_KEY
        raw_model = model or getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite")
        if raw_model in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"):
            self.model = "gemini-3.5-flash-lite"
        else:
            self.model = raw_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = None

        if not self.api_key:
            self.logger.warning("GeminiLLMClient initialized without GEMINI_API_KEY.")
        else:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Could not initialize google.genai Client: %s", exc)

    async def _call_gemini_with_retry(
        self,
        prompt: str,
        node_name: str,
        state: "BugReportState",
        prompt_version: str,
    ) -> str:
        import asyncio
        import time
        from app.db import log_run_step

        if not self._client:
            raise RuntimeError("GeminiLLMClient has no GEMINI_API_KEY configured.")

        start_time = time.monotonic()
        attempt = 0
        last_exc: Exception | None = None

        while attempt < self.max_retries:
            attempt += 1
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    response = await self._client.aio.models.generate_content(
                        model=self.model,
                        contents=prompt,
                    )

                text = response.text or ""
                latency_ms = int((time.monotonic() - start_time) * 1000)

                # Extract token usage if available
                tokens_used = 0
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    tokens_used = getattr(response.usage_metadata, "total_token_count", 0) or 0

                # Log step to run_steps table
                log_run_step(
                    run_id=state.run_id or state.bug_report_id,
                    node_name=node_name,
                    input_data={
                        "prompt_version": prompt_version,
                        "model": self.model,
                        "prompt": prompt,
                    },
                    output_data={
                        "prompt_version": prompt_version,
                        "model_version": self.model,
                        "response": text,
                    },
                    tokens_used=tokens_used,
                    latency_ms=latency_ms,
                )
                return text

            except Exception as exc:
                last_exc = exc
                self.logger.warning(
                    "Gemini call failed (attempt %d/%d) for node %s: %s",
                    attempt,
                    self.max_retries,
                    node_name,
                    exc,
                )
                if attempt < self.max_retries:
                    err_str = str(exc)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                        import re
                        m = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str, re.IGNORECASE)
                        if m:
                            backoff = max(float(m.group(1)) + 1.0, 30.0)
                        else:
                            backoff = 32.0
                        self.logger.info("Gemini rate-limited — waiting %.1fs before retry...", backoff)
                    else:
                        backoff = min((2 ** (attempt - 1)) + 1.0, 10.0)
                    await asyncio.sleep(backoff)

        latency_ms = int((time.monotonic() - start_time) * 1000)
        log_run_step(
            run_id=state.run_id or state.bug_report_id,
            node_name=node_name,
            input_data={"prompt_version": prompt_version, "model": self.model, "prompt": prompt},
            output_data={"error": str(last_exc), "prompt_version": prompt_version, "model_version": self.model},
            tokens_used=0,
            latency_ms=latency_ms,
        )
        raise RuntimeError(f"Gemini API call failed after {self.max_retries} attempts: {last_exc}") from last_exc

    async def generate_hypothesis(self, state: "BugReportState") -> str:
        """Analyze bug report and generate reproduction hypothesis using Gemini 2.5 Flash."""
        from app.prompts.hypothesis_generation_v1 import (
            VERSION as HYPOTHESIS_PROMPT_VERSION,
            render_hypothesis_prompt,
        )

        repo_meta = state.repo.model_dump() if hasattr(state.repo, "model_dump") else {}
        prompt = render_hypothesis_prompt(
            title=state.title,
            description=state.description,
            raw_stack_trace=state.raw_stack_trace,
            repo_meta=repo_meta,
        )
        return await self._call_gemini_with_retry(
            prompt=prompt,
            node_name="hypothesis_gen",
            state=state,
            prompt_version=HYPOTHESIS_PROMPT_VERSION,
        )

    async def generate_repro_script(self, state: "BugReportState") -> str:
        """Produce runnable reproduction script based on active hypothesis using Gemini 2.5 Flash."""
        from app.prompts.script_generation_v1 import (
            VERSION as SCRIPT_PROMPT_VERSION,
            render_script_prompt,
        )

        prompt = render_script_prompt(
            hypothesis=state.current_hypothesis,
            raw_stack_trace=state.raw_stack_trace,
            language=state.repo.language or "python",
            base_image=state.base_image or "python:3.11-slim",
            install_command=state.install_command or "",
            framework=state.repo.framework or "pytest",
        )
        raw_script = await self._call_gemini_with_retry(
            prompt=prompt,
            node_name="script_gen",
            state=state,
            prompt_version=SCRIPT_PROMPT_VERSION,
        )
        return self._clean_code(raw_script)

    async def compare_verdict(
        self,
        state: "BugReportState",
        stdout: str,
        stderr: str,
        exit_code: int,
        timed_out: bool = False,
    ) -> dict[str, Any]:
        """Perform semantic failure comparison against reported bug signature."""
        import json
        from app.prompts.verdict_comparison_v1 import (
            VERSION as VERDICT_PROMPT_VERSION,
            render_verdict_prompt,
        )

        prompt = render_verdict_prompt(
            raw_stack_trace=state.raw_stack_trace,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            timed_out=timed_out,
        )
        raw_response = await self._call_gemini_with_retry(
            prompt=prompt,
            node_name="verdict",
            state=state,
            prompt_version=VERDICT_PROMPT_VERSION,
        )
        try:
            cleaned = self._clean_code(raw_response)
            return json.loads(cleaned)
        except Exception:
            verdict = "matched" if "matched" in raw_response.lower() else "no_match"
            return {"verdict": verdict, "reasoning": raw_response}

    @staticmethod
    def _clean_code(text: str) -> str:
        """Strip markdown code block fences from LLM output."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned

