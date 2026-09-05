"""Versioned prompt templates for the bug reproduction worker."""

from app.prompts.hypothesis_generation_v1 import (
    VERSION as HYPOTHESIS_PROMPT_VERSION,
    render_hypothesis_prompt,
)
from app.prompts.script_generation_v1 import (
    VERSION as SCRIPT_PROMPT_VERSION,
    render_script_prompt,
)
from app.prompts.verdict_comparison_v1 import (
    VERSION as VERDICT_PROMPT_VERSION,
    render_verdict_prompt,
)

__all__ = [
    "HYPOTHESIS_PROMPT_VERSION",
    "render_hypothesis_prompt",
    "SCRIPT_PROMPT_VERSION",
    "render_script_prompt",
    "VERDICT_PROMPT_VERSION",
    "render_verdict_prompt",
]
