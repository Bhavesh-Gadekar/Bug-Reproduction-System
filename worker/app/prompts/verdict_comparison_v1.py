"""Prompt template for verdict comparison (v1).

Directs the LLM to compare actual sandbox execution output (stdout/stderr/exit_code)
against the target bug signature and decide if the bug was reproduced.
"""

from __future__ import annotations

import json

VERSION = "verdict_comparison_v1"

PROMPT_TEMPLATE = """You are a software quality verification agent.
Your task is to evaluate whether a reproduction attempt successfully reproduced a reported bug.

--- REPORTED BUG SIGNATURE / STACK TRACE ---
{raw_stack_trace}

--- ACTUAL SANDBOX EXECUTION OUTPUT ---
Exit Code: {exit_code}
Timed Out: {timed_out}
Stdout:
{stdout}

Stderr:
{stderr}

--- INSTRUCTIONS ---
Compare the actual execution output against the reported bug signature.
Decide one of:
- "matched": The script failed with the same error type, message, or traceback as reported.
- "no_match": The script failed with an unrelated error, succeeded without error, or produced completely different output.
- "error": The execution environment timed out or failed catastrophically before running the reproduction logic.

Respond with ONLY a JSON object formatted exactly as:
{{
  "verdict": "matched" | "no_match" | "error",
  "reasoning": "Brief explanation of the decision"
}}
"""


def render_verdict_prompt(
    raw_stack_trace: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    timed_out: bool = False,
) -> str:
    return PROMPT_TEMPLATE.format(
        raw_stack_trace=raw_stack_trace or "(No stack trace provided)",
        exit_code=exit_code,
        timed_out=timed_out,
        stdout=stdout or "(Empty stdout)",
        stderr=stderr or "(Empty stderr)",
    ).strip()
