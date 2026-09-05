"""[Repo Analysis] node — detect language, framework, and build system via real cloning and inspection."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from app.graph.state import BugReportState, RepoMeta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Heuristics & Defaults
# ---------------------------------------------------------------------------

_URL_HEURISTICS: list[tuple[str, str, str, str]] = [
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


def _detect_from_filesystem(repo_path: Path) -> tuple[str | None, str | None, str | None]:
    """Inspect cloned repository files for language, framework, and build system."""
    if not repo_path.is_dir():
        return None, None, None

    # Python indicators
    if (
        (repo_path / "setup.py").exists()
        or (repo_path / "pyproject.toml").exists()
        or (repo_path / "requirements.txt").exists()
        or (repo_path / "setup.cfg").exists()
    ):
        build_sys = "pip"
        if (repo_path / "poetry.lock").exists():
            build_sys = "poetry"
        elif (repo_path / "uv.lock").exists():
            build_sys = "uv"
        return "python", "pytest", build_sys

    # JavaScript / TypeScript indicators
    if (repo_path / "package.json").exists():
        has_ts = (repo_path / "tsconfig.json").exists() or list(repo_path.glob("**/*.ts"))
        lang = "typescript" if has_ts else "javascript"
        build_sys = "npm"
        if (repo_path / "yarn.lock").exists():
            build_sys = "yarn"
        elif (repo_path / "pnpm-lock.yaml").exists():
            build_sys = "pnpm"
        return lang, "jest", build_sys

    # Rust
    if (repo_path / "Cargo.toml").exists():
        return "rust", "cargo-test", "cargo"

    # Java
    if (repo_path / "pom.xml").exists():
        return "java", "junit", "maven"
    if (repo_path / "build.gradle").exists() or (repo_path / "build.gradle.kts").exists():
        return "java", "junit", "gradle"

    # Go
    if (repo_path / "go.mod").exists():
        return "go", "go-test", "go"

    return None, None, None


def _get_repo_base_dir() -> Path:
    """Return the base directory for cloned repositories."""
    # Check if /repos is mounted in container or local override
    env_dir = os.getenv("REPOS_CACHE_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if Path("/repos").is_dir():
        return Path("/repos")
    fallback = Path("/tmp/repos")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _clone_and_checkout_repo(
    git_url: str,
    target_dir: Path,
    commit_sha: str | None = None,
    branch: str = "main",
) -> bool:
    """Clone git repository and checkout the target commit or branch."""
    if "example.com" in git_url or "example/" in git_url or not git_url.startswith("http"):
        return False

    try:
        if not target_dir.exists() or not (target_dir / ".git").exists():
            logger.info("Cloning %s into %s...", git_url, target_dir)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            res = subprocess.run(
                [
                    "git",
                    "-c", "http.connectTimeout=5",
                    "-c", "http.lowSpeedTime=5",
                    "clone",
                    git_url,
                    str(target_dir),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            if res.returncode != 0:
                logger.warning("git clone failed for %s: %s", git_url, res.stderr.strip())
                return False

        # Checkout specific commit sha or branch
        target_ref = commit_sha or branch
        if target_ref:
            logger.info("Checking out %s in %s...", target_ref, target_dir)
            res = subprocess.run(
                ["git", "checkout", target_ref],
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                timeout=20,
            )
            if res.returncode != 0:
                logger.warning("git checkout %s failed: %s", target_ref, res.stderr.strip())
                return False

        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error cloning/checking out repo %s: %s", git_url, exc)
        return False


async def repo_analysis_node(state: BugReportState) -> dict[str, Any]:
    """
    Clones the repository at base_commit_sha / branch, inspects project files,
    and populates ``repo.language``, ``repo.framework``, and ``repo.build_system``.
    """
    repo = state.repo
    base_dir = _get_repo_base_dir()
    slug = state.bug_report_id or "default_repo"
    target_dir = base_dir / slug

    # Attempt real git clone and checkout
    cloned_ok = _clone_and_checkout_repo(
        git_url=repo.git_url,
        target_dir=target_dir,
        commit_sha=repo.base_commit_sha,
        branch=repo.branch,
    )

    detected_lang = None
    detected_fw = None
    detected_bs = None

    if cloned_ok:
        detected_lang, detected_fw, detected_bs = _detect_from_filesystem(target_dir)

    if not (detected_lang and detected_fw and detected_bs):
        url_lang, url_fw, url_bs = _detect_from_url(repo.git_url)
        detected_lang = detected_lang or url_lang or "python"
        if detected_lang in _LANGUAGE_DEFAULTS:
            default_fw, default_bs = _LANGUAGE_DEFAULTS[detected_lang]
        else:
            default_fw, default_bs = "pytest", "pip"
        detected_fw = detected_fw or url_fw or default_fw
        detected_bs = detected_bs or url_bs or default_bs

    language = repo.language or detected_lang
    framework = repo.framework or detected_fw
    build_system = repo.build_system or detected_bs

    from app.core.config import get_worker_settings
    settings = get_worker_settings()
    volume_name = (
        settings.REPOS_VOLUME_NAME
        if Path("/repos").is_dir()
        else (str(target_dir) if cloned_ok else None)
    )

    updated_repo = RepoMeta(
        git_url=repo.git_url,
        branch=repo.branch,
        base_commit_sha=repo.base_commit_sha,
        fix_commit_sha=repo.fix_commit_sha,
        local_path=str(target_dir) if cloned_ok else None,
        volume_name=volume_name,
        language=language,
        framework=framework,
        build_system=build_system,
    )

    return {"repo": updated_repo}
