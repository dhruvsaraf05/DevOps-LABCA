import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app


@pytest.fixture(autouse=True)
def clean_store():
    """Every test starts and ends with an empty store, so stable tests are order-independent."""
    store.reset()
    yield
    store.reset()


@pytest.fixture
def client():
    return TestClient(app)
