"""INTENTIONALLY FLAKY TESTS. Do not fix them.

They exist so the CI pipeline has real flakiness to detect and quarantine. Each one
represents a common real-world category of flaky test. FLAKE_RATE (default 0.3) tunes them.
"""

import os
import time

from app import external, store


def flake_rate() -> float:
    return float(os.environ.get("FLAKE_RATE", "0.3"))


def test_flaky_random_dependency():
    """INTENTIONALLY FLAKY (non-determinism): the simulated upstream call fails with
    probability FLAKE_RATE and the test does not handle it."""
    assert external.call_external_service(flake_rate()) == {"status": "ok"}


def test_flaky_timing():
    """INTENTIONALLY FLAKY (timing/race): the lookup is slow with probability FLAKE_RATE,
    and the test asserts a tight deadline."""
    start = time.perf_counter()
    external.timed_lookup(flake_rate())
    assert time.perf_counter() - start < 0.1


def test_flaky_order_dependent():
    """INTENTIONALLY FLAKY (shared state): relies on `store.last_operation`, which is only
    set when one of the two tests above has already run. With pytest-randomly shuffling the
    order, this test runs first about 1 time in 3 (independent of FLAKE_RATE) and fails."""
    assert store.last_operation is not None
