"""Proves the usage limit is actually enforced, not just stored. Uses a
test-only, very-low-limit plan directly inserted into the DB rather than
making 1000 real calls against the free tier's generous default limit."""
import uuid

import pytest
from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.billing import Plan, SubscriptionStatus, TenantSubscription
from app.models.user import User
from app.services.ai.base import GenerationResult
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _pin_tenant_to_tiny_plan(email: str, max_runs: int) -> None:
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()

        tiny_plan = Plan(
            slug=f"tiny-{uuid.uuid4().hex[:8]}",
            name="Tiny (test only)",
            price_usd_per_month=0,
            max_agent_runs_per_month=max_runs,
            max_tool_calls_per_month=max_runs * 5,
            max_users=1,
        )
        db.add(tiny_plan)
        await db.flush()

        db.add(
            TenantSubscription(
                tenant_id=user.tenant_id, plan_id=tiny_plan.id, status=SubscriptionStatus.ACTIVE
            )
        )
        await db.commit()


async def test_run_succeeds_under_the_limit(client, unique_email, monkeypatch):
    fake = FakeAIProvider([GenerationResult(content="hi", model="fake")])
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)
    await _pin_tenant_to_tiny_plan(unique_email, max_runs=1)

    res = await client.post(
        "/api/v1/agents/run", json={"agent": "general_assistant", "message": "hi"}, headers=headers
    )
    assert res.status_code == 200


async def test_run_blocked_once_limit_reached(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [GenerationResult(content="hi", model="fake"), GenerationResult(content="hi again", model="fake")]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)
    await _pin_tenant_to_tiny_plan(unique_email, max_runs=1)

    first = await client.post(
        "/api/v1/agents/run", json={"agent": "general_assistant", "message": "hi"}, headers=headers
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/agents/run", json={"agent": "general_assistant", "message": "hi again"}, headers=headers
    )
    assert second.status_code == 402
    assert "limit" in second.json()["detail"].lower()


async def test_other_tenants_unaffected_by_one_tenants_limit(client, unique_email, monkeypatch):
    fake = FakeAIProvider([GenerationResult(content="hi", model="fake")])
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)

    limited_email = f"limited-{unique_email}"
    limited_headers = await _auth_headers(client, limited_email)
    await _pin_tenant_to_tiny_plan(limited_email, max_runs=0)

    blocked = await client.post(
        "/api/v1/agents/run", json={"agent": "general_assistant", "message": "hi"}, headers=limited_headers
    )
    assert blocked.status_code == 402

    other_headers = await _auth_headers(client, f"other-{unique_email}")
    ok = await client.post(
        "/api/v1/agents/run", json={"agent": "general_assistant", "message": "hi"}, headers=other_headers
    )
    assert ok.status_code == 200
