import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from svix.webhooks import Webhook

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.workspace import User, Workspace

TEST_SIGNING_SECRET = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2NTNySw"


def generate_svix_headers(payload_dict: dict, secret: str = TEST_SIGNING_SECRET) -> dict[str, str]:
    """Generate valid Svix webhook signature headers for a payload dictionary."""
    payload_str = json.dumps(payload_dict)
    now = datetime.now(UTC)
    msg_id = f"msg_{int(now.timestamp() * 1000)}"
    timestamp_str = str(int(now.timestamp()))

    wh = Webhook(secret)
    # Svix sign format: wh.sign(msg_id, datetime, payload_str)
    signature = wh.sign(msg_id, now, payload_str)

    return {
        "svix-id": msg_id,
        "svix-timestamp": timestamp_str,
        "svix-signature": signature,
        "content-type": "application/json",
    }


def test_clerk_webhook_organization_and_user_creation(postgres_engine, monkeypatch):
    """
    Test that /webhooks/clerk parses organization.created and user.created events
    with valid Svix signatures, creating and linking local Workspace and User records.
    """
    # Override settings to use the test signing secret
    settings = get_settings()
    monkeypatch.setattr(settings, "CLERK_WEBHOOK_SECRET", TEST_SIGNING_SECRET)

    # Dependency override to use the test database engine
    def override_get_db():
        with Session(bind=postgres_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        # 1. Send organization.created event
        org_id = "org_clerk_avengers_101"
        org_name = "Avengers Initiative"
        org_payload = {
            "type": "organization.created",
            "data": {
                "id": org_id,
                "name": org_name,
                "slug": "avengers-initiative",
            },
        }
        org_headers = generate_svix_headers(org_payload)

        response = client.post(
            "/webhooks/clerk",
            content=json.dumps(org_payload),
            headers=org_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["event"] == "organization.created"

        # Verify Workspace was persisted in the test database
        with Session(bind=postgres_engine) as session:
            ws = session.scalars(select(Workspace).where(Workspace.clerk_org_id == org_id)).first()
            assert ws is not None
            assert ws.name == org_name
            workspace_id = ws.id

        # 2. Send user.created event linked to the created organization
        user_id = "user_clerk_ironman_3000"
        user_email = "tony.stark@avengers.org"
        user_payload = {
            "type": "user.created",
            "data": {
                "id": user_id,
                "email_addresses": [
                    {"id": "email_1", "email_address": user_email},
                ],
                "primary_email_address_id": "email_1",
                "public_metadata": {
                    "clerk_org_id": org_id,
                },
            },
        }
        user_headers = generate_svix_headers(user_payload)

        response = client.post(
            "/webhooks/clerk",
            content=json.dumps(user_payload),
            headers=user_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["event"] == "user.created"

        # Verify User was persisted and correctly associated with the Workspace
        with Session(bind=postgres_engine) as session:
            user = session.scalars(select(User).where(User.clerk_user_id == user_id)).first()
            assert user is not None
            assert user.email == user_email
            assert user.workspace_id == workspace_id
            assert user.role == "admin"

    finally:
        app.dependency_overrides.clear()


def test_clerk_webhook_invalid_signature_rejected(postgres_engine, monkeypatch):
    """
    Test that /webhooks/clerk rejects requests with invalid or forged Svix signatures.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "CLERK_WEBHOOK_SECRET", TEST_SIGNING_SECRET)

    def override_get_db():
        with Session(bind=postgres_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        now = datetime.now(UTC)
        payload = {"type": "user.created", "data": {"id": "user_fake_1"}}
        headers = {
            "svix-id": "msg_forged_123",
            "svix-timestamp": str(int(now.timestamp())),
            "svix-signature": "v1,invalid_forged_signature_hash",
            "content-type": "application/json",
        }

        response = client.post(
            "/webhooks/clerk",
            content=json.dumps(payload),
            headers=headers,
        )
        assert response.status_code == 400
        assert "Invalid webhook signature" in response.json()["detail"]

    finally:
        app.dependency_overrides.clear()
