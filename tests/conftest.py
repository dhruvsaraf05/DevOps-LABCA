import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app


def quarantined_ids(root: Path) -> set[str]:
    """Test ids listed in <root>/quarantine.json (empty if the file does not exist)."""
    path = root / "quarantine.json"
    if not path.exists():
        return set()
    return {entry["id"] for entry in json.loads(path.read_text(encoding="utf-8"))["tests"]}


def pytest_collection_modifyitems(config, items):
    """Normal runs: quarantined tests may fail without failing the run (xfail, not strict).

    CI detection runs set IGNORE_QUARANTINE=1 so that results are raw: the detector,
    not this hook, decides what quarantine means at the gate.
    """
    if os.environ.get("IGNORE_QUARANTINE") == "1":
        return
    quarantined = quarantined_ids(config.rootpath)
    for item in items:
        if item.nodeid in quarantined:
            item.add_marker(pytest.mark.xfail(strict=False, reason="quarantined: flaky"))


@pytest.fixture(autouse=True)
def clean_store():
    """Every test starts and ends with an empty store, so stable tests are order-independent."""
    store.reset()
    yield
    store.reset()


@pytest.fixture
def client():
    return TestClient(app)
