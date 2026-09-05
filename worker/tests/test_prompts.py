"""Unit tests for versioned prompt templates and formatting."""

from __future__ import annotations

from app.prompts import (
    HYPOTHESIS_PROMPT_VERSION,
    SCRIPT_PROMPT_VERSION,
    VERDICT_PROMPT_VERSION,
    render_hypothesis_prompt,
    render_script_prompt,
    render_verdict_prompt,
)


def test_hypothesis_prompt_rendering():
    """Verify hypothesis prompt template formatting and versioning."""
    assert HYPOTHESIS_PROMPT_VERSION == "hypothesis_generation_v1"

    prompt = render_hypothesis_prompt(
        title="NullPointerException in UserAuth",
        description="UserAuth.login fails when email is missing domain",
        raw_stack_trace="NullPointerException at UserAuth.java:42",
        repo_meta={
            "git_url": "https://github.com/org/auth-service",
            "branch": "main",
            "language": "java",
            "framework": "junit",
            "build_system": "maven",
        },
    )

    assert "NullPointerException in UserAuth" in prompt
    assert "UserAuth.java:42" in prompt
    assert "https://github.com/org/auth-service" in prompt
    assert "java" in prompt
    assert "junit" in prompt


def test_script_prompt_rendering():
    """Verify script generation prompt formatting and code fence instructions."""
    assert SCRIPT_PROMPT_VERSION == "script_generation_v1"

    prompt = render_script_prompt(
        hypothesis="Index out of bounds on empty list",
        raw_stack_trace="IndexError: list index out of range",
        language="python",
        base_image="python:3.11-slim",
        install_command="pip install pytest",
        framework="pytest",
    )

    assert "Index out of bounds on empty list" in prompt
    assert "IndexError: list index out of range" in prompt
    assert "python:3.11-slim" in prompt
    assert "pip install pytest" in prompt
    assert "```{code_fence}" not in prompt  # fence variable was interpolated


def test_verdict_prompt_rendering():
    """Verify verdict comparison prompt formatting and output JSON schema instructions."""
    assert VERDICT_PROMPT_VERSION == "verdict_comparison_v1"

    prompt = render_verdict_prompt(
        raw_stack_trace="ZeroDivisionError: division by zero",
        stdout="Calculating...\nZeroDivisionError: division by zero",
        stderr="",
        exit_code=1,
        timed_out=False,
    )

    assert "ZeroDivisionError: division by zero" in prompt
    assert "Exit Code: 1" in prompt
    assert "Timed Out: False" in prompt
    assert '"verdict": "matched" | "no_match" | "error"' in prompt
