"""Simulated slow / unreliable dependencies, used only by the intentionally flaky tests.

Nothing in the API calls these. They use SystemRandom so results are not pinned by
pytest-randomly (which re-seeds the global `random` module before every test).
"""

import random
import time

from app import store

_rng = random.SystemRandom()

FAST_SECONDS = 0.01
SLOW_SECONDS = 0.2


def call_external_service(failure_rate: float) -> dict:
    """Pretend network call that fails with probability `failure_rate`."""
    store.record_operation("external_call")
    if _rng.random() < failure_rate:
        raise ConnectionError("simulated upstream failure")
    return {"status": "ok"}


def timed_lookup(slow_rate: float) -> None:
    """Pretend lookup that is usually fast but is slow with probability `slow_rate`."""
    store.record_operation("timed_lookup")
    time.sleep(SLOW_SECONDS if _rng.random() < slow_rate else FAST_SECONDS)
