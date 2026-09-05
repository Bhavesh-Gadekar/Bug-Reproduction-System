"""Shared pytest configuration for sandbox tests.

Adds the sandbox package root (the ``sandbox/`` directory) to sys.path so
that ``from app.xxx import ...`` resolves correctly when running pytest
locally from the repo root OR from inside the sandbox/ directory.

Inside Docker the WORKDIR is /app, so Python already finds ``app.*``
directly — no path manipulation needed there.
"""

import sys
from pathlib import Path

# sandbox/tests/conftest.py
# parents[0] = sandbox/tests
# parents[1] = sandbox        <-- the package root we want on sys.path
_sandbox_root = Path(__file__).resolve().parent.parent
if str(_sandbox_root) not in sys.path:
    sys.path.insert(0, str(_sandbox_root))
