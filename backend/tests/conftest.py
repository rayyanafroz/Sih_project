import os
import tempfile
from pathlib import Path

import pytest

# Isolated database/storage for the test session — must be set before the app is imported.
_TMP = Path(tempfile.mkdtemp(prefix="verifyai-test-"))
os.environ["VERIFYAI_DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["VERIFYAI_STORAGE_DIR"] = str(_TMP / "storage")
os.environ["VERIFYAI_DEMO_DATA_DIR"] = str(_TMP / "demo_data")
os.environ["VERIFYAI_STEP_DELAY"] = "0"
os.environ["VERIFYAI_SECRET_KEY"] = "test-secret-key-for-the-test-suite-only-0123456789"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.demo.seed import reset  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    reset(quiet=True)
    with TestClient(app) as c:
        yield c


def login(client, email: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def scrutiny(client):
    return login(client, "scrutiny@verifyai.demo")


@pytest.fixture(scope="session")
def verifier(client):
    return login(client, "verification@verifyai.demo")


@pytest.fixture(scope="session")
def admin(client):
    return login(client, "admin@verifyai.demo")


@pytest.fixture(scope="session")
def demo_dir() -> Path:
    return settings.demo_data_dir
