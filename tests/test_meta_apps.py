from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import main, meta
from app.models import InstagramAccount, MetaApp, OAuthState


@pytest.fixture
def panel(tmp_path, monkeypatch):
    for name, value in {
        "app_encryption_key": Fernet.generate_key().decode(),
        "admin_email": "admin@example.invalid",
        "admin_password": "synthetic-password",
        "meta_instagram_app_id": "101",
        "meta_instagram_app_secret": "legacy-secret",
        "meta_graph_api_version": "v99.0",
        "meta_redirect_uri": "https://connect.example.invalid/api/meta/callback",
        "meta_oauth_authorize_url": "https://www.instagram.com/oauth/authorize",
    }.items():
        monkeypatch.setattr(main.settings, name, value)
    monkeypatch.setattr(main, "reload_runtime_settings", lambda: None)
    monkeypatch.setattr(main, "queue_account_campaign_sync", lambda _: None)
    engine = create_engine(f"sqlite:///{tmp_path / 'synthetic.db'}")
    main.Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)

    def db():
        with sessions() as session:
            yield session

    monkeypatch.setitem(main.app.dependency_overrides, main.db, db)
    client = TestClient(main.app, follow_redirects=False)
    try:
        yield client, sessions
    finally:
        client.close()
        engine.dispose()


def login(client):
    result = client.post("/api/auth/login", json={
        "email": "admin@example.invalid", "password": "synthetic-password",
    })
    assert result.status_code == 200


def app_payload():
    return {"instagram_client_id": "202", "instagram_client_secret": "synthetic-secret"}


def params(location):
    return parse_qs(urlparse(location).query)


def test_admin_registers_and_rotates_without_exposing_secret(panel):
    client, sessions = panel
    assert client.get("/api/meta/apps").status_code == 401
    assert client.post("/api/meta/apps", json=app_payload()).status_code == 401
    login(client)
    assert client.post("/api/meta/apps", json=app_payload()).json() == {"alias": "app-2"}
    assert client.post("/api/meta/apps", json=app_payload()).status_code == 409
    assert client.put("/api/meta/apps/app-2/secret", json={
        "instagram_client_secret": "replacement-secret",
    }).status_code == 200
    listing = client.get("/api/meta/apps")
    assert [item["alias"] for item in listing.json()["apps"]] == ["app-1", "app-2"]
    assert "secret" not in listing.text
    with sessions() as session:
        stored = session.scalar(select(MetaApp))
        assert stored.encrypted_secret != "replacement-secret"
        assert meta.decrypt(stored.encrypted_secret) == "replacement-secret"


def test_oauth_keeps_selected_app_through_callback_and_reconnection(panel, monkeypatch):
    client, sessions = panel
    login(client)
    assert client.post("/api/meta/apps", json=app_payload()).status_code == 201
    start = "/api/meta/oauth/start"
    callback = "/api/meta/oauth/callback"
    assert params(client.get(start).headers["location"])["client_id"] == ["101"]
    assert client.get(start, params={"app": "app-9"}).status_code == 404
    selected = params(client.get(start, params={"app": "app-2"}).headers["location"])
    assert selected["client_id"] == ["202"]
    state = selected["state"][0]

    exchange = AsyncMock(return_value=("synthetic-token", None))
    profile = AsyncMock(return_value={"account_id": "99", "username": "synthetic"})
    monkeypatch.setattr(meta, "exchange_code", exchange)
    monkeypatch.setattr(meta, "profile", profile)
    result = client.get(callback, params={"state": state, "code": "synthetic-code", "app": "app-1"})
    assert result.status_code == 200
    exchange.assert_awaited_once_with("synthetic-code", "202", "synthetic-secret", selected["redirect_uri"][0])
    assert client.get(callback, params={"state": state, "code": "reused"}).status_code == 400

    with sessions() as session:
        account = session.scalar(select(InstagramAccount))
        assert account.meta_app_id == 1
        account_id = account.id

    reconnect = params(client.get("/api/meta/oauth/url", params={
        "account_id": account_id, "app": "app-1",
    }).json()["url"])
    assert reconnect["client_id"] == ["202"]
    profile.return_value = {"account_id": "88", "username": "other"}
    assert client.get(callback, params={"state": reconnect["state"][0], "code": "other"}).status_code == 409
    profile.return_value = {"account_id": "99", "username": "synthetic"}
    legacy = params(client.get(start).headers["location"])
    assert client.get(callback, params={"state": legacy["state"][0], "code": "wrong-app"}).status_code == 409
    assert client.get("/api/meta/accounts").json()[0]["meta_app"] == "app-2"
    with sessions() as session:
        assert len(session.scalars(select(InstagramAccount)).all()) == 1


def test_expired_state_never_reaches_meta(panel, monkeypatch):
    client, sessions = panel
    selected = params(client.get("/api/meta/oauth/start").headers["location"])
    state = selected["state"][0]
    with sessions() as session:
        session.get(OAuthState, state).created_at = datetime.utcnow() - timedelta(minutes=16)
        session.commit()
    exchange = AsyncMock()
    monkeypatch.setattr(meta, "exchange_code", exchange)
    assert client.get("/api/meta/oauth/callback", params={"state": state, "code": "late"}).status_code == 400
    exchange.assert_not_awaited()
