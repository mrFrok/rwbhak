import os
from tempfile import TemporaryDirectory

_tmp = TemporaryDirectory(prefix="rwbhak-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}/test.db"

import pytest
from fastapi.testclient import TestClient

from api.db import Base, SessionLocal, engine
from api.main import app
from data.seed import seed


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db, reset=True)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)


def key(name: str) -> dict[str, str]:
    return {"Idempotency-Key": f"test-{name}-0001"}
