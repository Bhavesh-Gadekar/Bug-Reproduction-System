import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from svix.webhooks import Webhook

from app.core.config import get_settings
from app.db.session import get_db
from app.models.workspace import User, Workspace

logger = logging.getLogger("webhooks")
settings = get_settings()

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/clerk", status_code=status.HTTP_200_OK)
async def handle_clerk_webhook(
    request: Request,
    db: Session = Depends(get_db),
    svix_id: str | None = Header(None, alias="svix-id"),
    svix_timestamp: str | None = Header(None, alias="svix-timestamp"),
    svix_signature: str | None = Header(None, alias="svix-signature"),
):
    """
    Clerk Webhook endpoint that verifies Svix signatures and synchronizes
    `user.created`, `organization.created`, and related events into local PostgreSQL tables.
    """
    body_bytes = await request.body()
    webhook_secret = settings.CLERK_WEBHOOK_SECRET

    if webhook_secret:
        if not svix_id or not svix_timestamp or not svix_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing Svix verification headers",
            )
        headers = {
            "svix-id": svix_id,
            "svix-timestamp": svix_timestamp,
            "svix-signature": svix_signature,
        }
        try:
            wh = Webhook(webhook_secret)
            wh.verify(body_bytes, headers)
        except Exception as e:
            logger.warning("Invalid Clerk webhook signature: %s", e)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid webhook signature: {e!s}",
            ) from e

    try:
        payload: dict[str, Any] = json.loads(body_bytes.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON body",
        ) from e

    event_type = payload.get("type")
    data = payload.get("data", {})
    logger.info("Processing Clerk webhook event: %s", event_type)

    # 1. Handle organization.created / organization.updated
    if event_type in ("organization.created", "organization.updated"):
        clerk_org_id = data.get("id")
        name = data.get("name") or "Unnamed Organization"

        if clerk_org_id:
            stmt = select(Workspace).where(Workspace.clerk_org_id == clerk_org_id)
            workspace = db.scalars(stmt).first()

            if not workspace:
                workspace = Workspace(
                    id=uuid.uuid4(),
                    name=name,
                    clerk_org_id=clerk_org_id,
                )
                db.add(workspace)
                logger.info("Created local Workspace for Clerk org: %s (%s)", name, clerk_org_id)
            else:
                workspace.name = name
                logger.info("Updated local Workspace for Clerk org: %s (%s)", name, clerk_org_id)

            db.commit()
            return {"status": "success", "event": event_type, "workspace_id": str(workspace.id)}

    # 2. Handle user.created / user.updated
    elif event_type in ("user.created", "user.updated"):
        clerk_user_id = data.get("id")
        if not clerk_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing user id in webhook data",
            )

        # Extract primary email
        email_addresses = data.get("email_addresses", [])
        primary_email_id = data.get("primary_email_address_id")
        email = None

        if primary_email_id:
            for item in email_addresses:
                if item.get("id") == primary_email_id:
                    email = item.get("email_address")
                    break

        if not email and email_addresses:
            email = email_addresses[0].get("email_address")

        if not email:
            email = f"{clerk_user_id}@placeholder.clerk.dev"

        # Check existing user
        stmt = select(User).where(User.clerk_user_id == clerk_user_id)
        user = db.scalars(stmt).first()

        if not user:
            # Check or assign workspace:
            # 1. Look up by clerk_org_id if present in public metadata or org list
            clerk_org_id = data.get("public_metadata", {}).get("clerk_org_id")
            workspace: Workspace | None = None

            if clerk_org_id:
                ws_stmt = select(Workspace).where(Workspace.clerk_org_id == clerk_org_id)
                workspace = db.scalars(ws_stmt).first()

            if not workspace:
                # Find or create a default personal workspace for the user
                default_name = f"{email.split('@')[0]}'s Workspace"
                workspace = Workspace(
                    id=uuid.uuid4(),
                    name=default_name,
                    clerk_org_id=None,
                )
                db.add(workspace)
                db.flush()

            user = User(
                id=uuid.uuid4(),
                workspace_id=workspace.id,
                clerk_user_id=clerk_user_id,
                email=email,
                role="admin",
            )
            db.add(user)
            logger.info("Created local User %s in Workspace %s", email, workspace.id)
        else:
            user.email = email
            logger.info("Updated local User %s (%s)", email, clerk_user_id)

        db.commit()
        return {"status": "success", "event": event_type, "user_id": str(user.id)}

    # 3. Handle organizationMembership.created
    elif event_type == "organizationMembership.created":
        org_data = data.get("organization", {})
        public_user_data = data.get("public_user_data", {})
        clerk_org_id = org_data.get("id")
        clerk_user_id = public_user_data.get("user_id")
        role = data.get("role", "member")

        if clerk_org_id and clerk_user_id:
            ws_stmt = select(Workspace).where(Workspace.clerk_org_id == clerk_org_id)
            workspace = db.scalars(ws_stmt).first()

            user_stmt = select(User).where(User.clerk_user_id == clerk_user_id)
            user = db.scalars(user_stmt).first()

            if workspace and user:
                user.workspace_id = workspace.id
                user.role = role
                db.commit()
                logger.info(
                    "Linked User %s to Workspace %s with role %s",
                    clerk_user_id,
                    workspace.id,
                    role,
                )

        return {"status": "success", "event": event_type}

    return {"status": "ignored", "event": event_type}
