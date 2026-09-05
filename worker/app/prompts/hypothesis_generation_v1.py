"""Prompt template for hypothesis generation (v1).

Directs the LLM to analyze the bug report and repo context, generating a concise,
actionable technical hypothesis explaining why the bug occurs and how to trigger it.
"""

from __future__ import annotations

from typing import Any

VERSION = "hypothesis_generation_v1"

PROMPT_TEMPLATE = """You are an expert automated debugging assistant.
Your task is to analyze the following bug report and repository metadata, and propose a concise, technical hypothesis explaining the root cause of the bug and how to reproduce it.

--- BUG REPORT ---
Title: {title}
Description:
{description}

Raw Stack Trace / Error Signature:
{raw_stack_trace}

--- REPOSITORY CONTEXT ---
Repository URL: {git_url}
Branch: {branch}
Language: {language}
Framework: {framework}
Build System: {build_system}

--- INSTRUCTIONS ---
1. Analyze the stack trace and error message to identify the specific component, function, or condition failing.
2. Formulate a single, clear hypothesis describing what input, state, or code path triggers the reported error.
3. Keep your response focused on the technical root cause and reproduction condition.
4. Provide only the hypothesis explanation (no conversational filler).
"""


def render_hypothesis_prompt(
    title: str,
    description: str,
    raw_stack_trace: str,
    repo_meta: dict[str, Any] | None = None,
) -> str:
    repo = repo_meta or {}
    return PROMPT_TEMPLATE.format(
        title=title or "(No title provided)",
        description=description or "(No description provided)",
        raw_stack_trace=raw_stack_trace or "(No stack trace provided)",
        git_url=repo.get("git_url", "unknown"),
        branch=repo.get("branch", "main"),
        language=repo.get("language", "python"),
        framework=repo.get("framework", "unknown"),
        build_system=repo.get("build_system", "unknown"),
    ).strip()
