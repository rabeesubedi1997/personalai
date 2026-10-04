"""
The "acting user" for public, API-key-authenticated agent runs (website
chat widgets). A widget's visitors are never PersonalOps platform
users — they never log in, have no email/password here — but every
AgentRun/Approval/Notification in this platform is keyed to a `user_id`,
and reworking that schema just to make it nullable would ripple through
billing, approvals, and notifications for one niche entry point. Instead,
each tenant gets one lazily-created, unlogged-into-able system User that
all of that tenant's public widget traffic is attributed to — same
pattern as `ensure_subscription`/`ensure_default_agents_installed`
(get-or-create, race-safe via its own session).
"""
from __future__ import annotations

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.user import Role, User
from app.security.passwords import hash_password

_WIDGET_EMAIL_DOMAIN = "widget.personalops.internal"


def _widget_email(tenant_id: uuid.UUID) -> str:
    return f"widget-{tenant_id}@{_WIDGET_EMAIL_DOMAIN}"


async def get_or_create_widget_user(db: AsyncSession, tenant_id: uuid.UUID) -> User:
    email = _widget_email(tenant_id)
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    try:
        async with async_session_factory() as write_db:
            write_db.add(
                User(
                    tenant_id=tenant_id,
                    email=email,
                    hashed_password=hash_password(secrets.token_urlsafe(32)),
                    full_name="Public Widget",
                    role=Role.VIEWER,
                    is_active=True,
                )
            )
            await write_db.commit()
    except IntegrityError:
        pass  # a concurrent request for this tenant's first widget call won the race

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        raise RuntimeError(f"Failed to create or find a widget user for tenant {tenant_id}")
    return user
