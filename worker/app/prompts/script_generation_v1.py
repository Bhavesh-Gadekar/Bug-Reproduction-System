"""Prompt template for reproduction script generation (v1).

Directs the LLM to generate a standalone, runnable reproduction script
that faithfully reproduces the reported bug in an isolated environment.
"""

from __future__ import annotations

from typing import Any

VERSION = "script_generation_v1"

PROMPT_TEMPLATE = """You are an automated bug reproduction engineer.
Your task is to write a standalone reproduction script in {language} that triggers the exact failure described below.

--- CURRENT HYPOTHESIS ---
{hypothesis}

--- TARGET ERROR SIGNATURE / STACK TRACE ---
{raw_stack_trace}

--- ENVIRONMENT & REPOSITORY CONTEXT ---
Language: {language}
Base Docker Image: {base_image}
Install Command: {install_command}
Framework: {framework}

--- REQUIREMENTS ---
1. The script must be completely self-contained and runnable via `python3 -c <script>` or direct execution.
2. It MUST reliably exit with a non-zero status code when the bug reproduces.
3. The script output (stdout/stderr) MUST produce the same error message or stack trace signature shown above.
4. Do NOT include setup or teardown scripts; focus solely on the reproducing code.
5. Return ONLY executable code inside a single ```{code_fence} ... ``` code block. No explanations before or after.
"""


def render_script_prompt(
    hypothesis: str,
    raw_stack_trace: str,
    language: str = "python",
    base_image: str = "python:3.11-slim",
    install_command: str = "",
    framework: str = "pytest",
) -> str:
    code_fence = language.lower() if language else "python"
    return PROMPT_TEMPLATE.format(
        hypothesis=hypothesis or "(No hypothesis provided)",
        raw_stack_trace=raw_stack_trace or "(No stack trace provided)",
        language=language or "python",
        base_image=base_image or "python:3.11-slim",
        install_command=install_command or "(None)",
        framework=framework or "unknown",
        code_fence=code_fence,
    ).strip()
