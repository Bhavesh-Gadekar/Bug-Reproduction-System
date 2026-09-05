"""Sandbox client protocol, real HTTP implementation, and test fake.

``SandboxClient`` is the interface the ``sandbox_exec`` node uses.
``RealSandboxClient`` calls the sandbox service (http://sandbox:8001/run).
``FakeSandboxClient`` returns deterministic responses based on script content
so tests never need a live Docker daemon.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared result model
# ---------------------------------------------------------------------------


class SandboxResult(BaseModel):
    """Response from the sandbox execution service."""

    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    timed_out: bool


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SandboxClient(Protocol):
    """Minimal interface required by the sandbox_exec node."""

    async def run(
        self,
        base_image: str,
        command: list[str],
        timeout_seconds: int,
    ) -> SandboxResult:
        """Execute *command* inside a sandboxed container and return the result."""
        ...


# ---------------------------------------------------------------------------
# Real HTTP implementation
# ---------------------------------------------------------------------------


class RealSandboxClient:
    """
    Calls ``POST <sandbox_url>/run`` on the sandbox runner service.

    Should be instantiated once and reused across calls (shares the
    underlying httpx.AsyncClient connection pool).
    """

    def __init__(self, sandbox_url: str, http_client: httpx.AsyncClient | None = None):
        self._base_url = sandbox_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(timeout=120.0)

    async def run(
        self,
        base_image: str,
        command: list[str],
        timeout_seconds: int,
    ) -> SandboxResult:
        response = await self._client.post(
            f"{self._base_url}/run",
            json={
                "base_image": base_image,
                "command": command,
                "timeout_seconds": timeout_seconds,
            },
        )
        response.raise_for_status()
        data = response.json()
        return SandboxResult(**data)

    async def aclose(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Fake implementation for tests
# ---------------------------------------------------------------------------


class FakeSandboxClient:
    """
    Deterministic sandbox stub for unit tests.

    Inspects the *last element* of ``command`` (the Python script passed via
    ``-c``) and returns:

    * ``AssertionError`` in the script → stdout reproduces the error (matched)
    * Anything else                    → stdout shows ``ValueError`` (no_match)

    This pairs directly with ``FakeLLMClient``:
    - Attempt 1 script raises ``ValueError``  → ``FakeSandboxClient`` returns
      ``ValueError`` stdout → verdict is ``no_match``
    - Attempt 2 script raises ``AssertionError`` → sandbox returns matching
      stdout → verdict is ``matched``
    """

    async def run(
        self,
        base_image: str,
        command: list[str],
        timeout_seconds: int,
    ) -> SandboxResult:
        # Extract the script text (last element of ["python3", "-c", "<script>"])
        script = command[-1] if command else ""

        if "AssertionError" in script:
            return SandboxResult(
                stdout="Traceback (most recent call last):\n"
                       "  File \"<string>\", line 2, in <module>\n"
                       "AssertionError: Expected values to be equal\n",
                stderr="",
                exit_code=1,
                duration_seconds=0.05,
                timed_out=False,
            )
        else:
            return SandboxResult(
                stdout="Traceback (most recent call last):\n"
                       "  File \"<string>\", line 2, in <module>\n"
                       "ValueError: Unexpected condition encountered\n",
                stderr="",
                exit_code=1,
                duration_seconds=0.05,
                timed_out=False,
            )
