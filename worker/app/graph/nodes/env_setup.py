"""[Environment Setup] node — choose base Docker image and install command."""

from __future__ import annotations

from typing import Any

from app.graph.state import BugReportState

# Maps (language, build_system) → (base_image, install_command)
_ENV_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("python", "pip"):      ("python:3.11-slim", "pip install -r requirements.txt"),
    ("python", "poetry"):   ("python:3.11-slim", "pip install poetry && poetry install"),
    ("python", "uv"):       ("python:3.11-slim", "pip install uv && uv sync"),
    ("typescript", "npm"):  ("node:20-slim",     "npm ci"),
    ("typescript", "yarn"): ("node:20-slim",     "yarn install --frozen-lockfile"),
    ("typescript", "pnpm"): ("node:20-slim",     "npm i -g pnpm && pnpm install --frozen-lockfile"),
    ("javascript", "npm"):  ("node:20-slim",     "npm ci"),
    ("java", "maven"):      ("maven:3.9-eclipse-temurin-21", "mvn dependency:resolve -q"),
    ("java", "gradle"):     ("gradle:8-jdk21",   "gradle dependencies -q"),
    ("ruby", "bundler"):    ("ruby:3.3-slim",    "bundle install"),
    ("rust", "cargo"):      ("rust:1.78-slim",   "cargo fetch"),
    ("go", "go"):           ("golang:1.22-alpine", "go mod download"),
}

_FALLBACK_IMAGE = "python:3.11-slim"
_FALLBACK_INSTALL = "pip install -r requirements.txt"


async def env_setup_node(state: BugReportState) -> dict[str, Any]:
    """
    Derive ``base_image`` and ``install_command`` from the detected language
    and build system.  Falls back to a Python slim image if the combination
    is unknown.
    """
    lang = (state.repo.language or "python").lower()
    bs = (state.repo.build_system or "pip").lower()

    base_image, install_command = _ENV_MAP.get(
        (lang, bs),
        (_FALLBACK_IMAGE, _FALLBACK_INSTALL),
    )

    # Respect caller-supplied values (set by tests or future deep-analysis)
    return {
        "base_image": state.base_image or base_image,
        "install_command": state.install_command or install_command,
    }
