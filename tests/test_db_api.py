import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.deps import get_db
from data.database import get_session_factory


@pytest.fixture()
def client(tmp_path):
    db_path = f"sqlite:///{tmp_path / 'test.db'}"
    factory = get_session_factory(db_path)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_session_factory_is_cached(tmp_path):
    db_path = f"sqlite:///{tmp_path / 'cache.db'}"
    assert get_session_factory(db_path) is get_session_factory(db_path)


def test_stats_empty(client):
    res = client.get("/api/db/stats")
    assert res.status_code == 200
    assert res.json() == {"races": 0, "horses": 0, "entries": 0, "results": 0}


def test_unknown_table_returns_404(client):
    res = client.get("/api/db/unknown_table")
    assert res.status_code == 404


def test_by_date_invalid_date_returns_400(client):
    res = client.get("/api/scrape/by-date?date_str=not-a-date")
    assert res.status_code == 400


def test_predict_untrained_returns_error(client, monkeypatch):
    import backend.routers.model as model_module
    monkeypatch.setattr(model_module, "_predictor", None)
    res = client.post("/api/model/predict?normalize=true",
                      json=[{"jockey": "テスト", "horse": "テスト馬"}])
    assert res.status_code == 200
    assert res.json() == {"error": "モデル未学習"}
