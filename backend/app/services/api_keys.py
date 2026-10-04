"""
API key issuance/verification for the public agent-chat endpoint
(app/api/v1/public.py). A key is scoped to exactly one tenant + one agent —
not a blanket "do anything" credential — so a compromised widget key can
only ever talk to the one agent it was issued for.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import AgentApiKey

_KEY_PREFIX = "pak_"  # "PersonalOps Agent Key"


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _generate_raw_key() -> str:
    return _KEY_PREFIX + secrets.token_urlsafe(32)


async def create_api_key(
    db: AsyncSession, *, tenant_id: uuid.UUID, agent_slug: str, label: str
) -> tuple[AgentApiKey, str]:
    """Returns (record, plaintext_key). The plaintext is never recoverable
    again after this call returns — only its hash is persisted."""
    raw_key = _generate_raw_key()
    record = AgentApiKey(
        tenant_id=tenant_id,
        agent_slug=agent_slug,
        label=label,
        key_prefix=raw_key[: len(_KEY_PREFIX) + 8],
        key_hash=_hash_key(raw_key),
        is_active=True,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record, raw_key


async def list_api_keys(db: AsyncSession, tenant_id: uuid.UUID) -> list[AgentApiKey]:
    result = await db.execute(
        select(AgentApiKey)
        .where(AgentApiKey.tenant_id == tenant_id)
        .order_by(AgentApiKey.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_api_key(
    db: AsyncSession, *, tenant_id: uuid.UUID, key_id: uuid.UUID
) -> AgentApiKey | None:
    result = await db.execute(
        select(AgentApiKey).where(AgentApiKey.id == key_id, AgentApiKey.tenant_id == tenant_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None
    record.is_active = False
    await db.commit()
    await db.refresh(record)
    return record


async def authenticate_api_key(db: AsyncSession, raw_key: str) -> AgentApiKey | None:
    if not raw_key or not raw_key.startswith(_KEY_PREFIX):
        return None
    result = await db.execute(
        select(AgentApiKey).where(
            AgentApiKey.key_hash == _hash_key(raw_key), AgentApiKey.is_active.is_(True)
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None
    record.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return record
