"""This test ALWAYS FAILS — by design.

The sandbox runner's integration tests mount this file into a container
and verify that the runner correctly captures the failure (exit_code != 0,
"FAILED" in stdout).
"""


def test_always_fails():
    """Assertion that is permanently false — the runner must capture this."""
    assert 1 == 2, "This assertion is deliberately false for sandbox runner testing"
