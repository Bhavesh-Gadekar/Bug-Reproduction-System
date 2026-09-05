"""[Repo Analysis] node — detect language, framework, and build system."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Any

from app.graph.state import BugReportState, RepoMeta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Heuristics — extend as needed
# ---------------------------------------------------------------------------

# Maps URL path keywords → (language, framework, build_system)
_URL_HEURISTICS: list[tuple[str, str, str, str]] = [
    # pattern, language, framework, build_system
    (r"pytest|django|flask|fastapi", "python", "pytest", "pip"),
    (r"\.py$|python", "python", "pytest", "pip"),
    (r"jest|react|nextjs|next\.js|vue|angular", "typescript", "jest", "npm"),
    (r"\.ts$|\.js$|node", "typescript", "jest", "npm"),
    (r"junit|spring|gradle|maven", "java", "junit", "maven"),
    (r"\.java$|java", "java", "junit", "maven"),
    (r"rspec|rails|sinatra|ruby", "ruby", "rspec", "bundler"),
    (r"\.rb$|ruby", "ruby", "rspec", "bundler"),
    (r"cargo|rust", "rust", "cargo-test", "cargo"),
    (r"\.rs$|rust", "rust", "cargo-test", "cargo"),
    (r"go test|golang|\.go$", "go", "go-test", "go"),
]

# Maps detected language → (framework, build_system) defaults
_LANGUAGE_DEFAULTS: dict[str, tuple[str, str]] = {
    "python": ("pytest", "pip"),
    "typescript": ("jest", "npm"),
    "javascript": ("jest", "npm"),
    "java": ("junit", "maven"),
    "ruby": ("rspec", "bundler"),
    "rust": ("cargo-test", "cargo"),
    "go": ("go-test", "go"),
}


def _detect_from_url(git_url: str) -> tuple[str | None, str | None, str | None]:
    """Return (language, framework, build_system) by pattern-matching the URL."""
    lower = git_url.lower()
    for pattern, lang, fw, bs in _URL_HEURISTICS:
        if re.search(pattern, lower):
            return lang, fw, bs
    return None, None, None


def _verify_repo_accessible(git_url: str) -> bool:
    """
    Run ``git ls-remote --heads <url>`` to verify the repo is reachable.
    Returns False (rather than raising) if git is not installed or the URL
    is unreachable — the graph continues with whatever language was detected.
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", git_url],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=15,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        return result.returncode == 0
    except Exception as exc:  # noqa: BLE001
        logger.debug("git ls-remote failed for %s: %s", git_url, exc)
        return False


async def repo_analysis_node(state: BugReportState) -> dict[str, Any]:
    """
    Populate ``repo.language``, ``repo.framework``, and ``repo.build_system``.

    Strategy (in priority order):
    1. If the values are already set in the incoming state, keep them.
    2. Detect from the git URL using keyword heuristics.
    3. Fall back to ``python`` / ``pytest`` / ``pip`` defaults.

    Also attempts a non-blocking ``git ls-remote`` to verify accessibility;
    logs a warning but does not block the pipeline if it fails.
    """
    repo = state.repo

    language = repo.language
    framework = repo.framework
    build_system = repo.build_system

    if not (language and framework and build_system):
        detected_lang, detected_fw, detected_bs = _detect_from_url(repo.git_url)
        language = language or detected_lang or "python"
        if language in _LANGUAGE_DEFAULTS:
            default_fw, default_bs = _LANGUAGE_DEFAULTS[language]
        else:
            default_fw, default_bs = "pytest", "pip"
        framework = framework or detected_fw or default_fw
        build_system = build_system or detected_bs or default_bs

    accessible = _verify_repo_accessible(repo.git_url)
    if not accessible:
        logger.warning("Repo %s may not be accessible (git ls-remote failed)", repo.git_url)

    updated_repo = RepoMeta(
        git_url=repo.git_url,
        branch=repo.branch,
        language=language,
        framework=framework,
        build_system=build_system,
    )

    return {"repo": updated_repo}
