import pytest

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_billing_requires_auth(client):
    assert (await client.get("/api/v1/billing/plans")).status_code == 401
    assert (await client.get("/api/v1/billing/subscription")).status_code == 401


async def test_plans_catalog_is_seeded(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.get("/api/v1/billing/plans", headers=headers)
    assert res.status_code == 200
    slugs = {p["slug"] for p in res.json()}
    assert slugs == {"free", "starter", "pro"}


async def test_new_tenant_defaults_to_free_plan_with_zero_usage(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.get("/api/v1/billing/subscription", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["plan"]["slug"] == "free"
    assert body["status"] == "active"
    assert body["current_period_agent_runs"] == 0


async def test_usage_reflects_actual_agent_runs(client, unique_email, monkeypatch):
    from app.services.ai.base import GenerationResult
    from tests.fakes import FakeAIProvider

    fake = FakeAIProvider([GenerationResult(content="hi", model="fake")])
    monkeypatch.setattr("app.services.agent_execution.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    await client.post(
        "/api/v1/agents/run", json={"agent": "general_assistant", "message": "hi"}, headers=headers
    )
    res = await client.get("/api/v1/billing/subscription", headers=headers)
    assert res.json()["current_period_agent_runs"] == 1


async def test_platform_admin_can_switch_plan(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.post(
        "/api/v1/billing/subscription", json={"plan_slug": "pro"}, headers=headers
    )
    assert res.status_code == 200
    assert res.json()["plan"]["slug"] == "pro"

    confirm = await client.get("/api/v1/billing/subscription", headers=headers)
    assert confirm.json()["plan"]["slug"] == "pro"


async def test_switching_to_unknown_plan_404s(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.post(
        "/api/v1/billing/subscription", json={"plan_slug": "nonexistent"}, headers=headers
    )
    assert res.status_code == 404


async def test_non_admin_cannot_switch_plan(client, unique_email):
    from sqlalchemy import select

    from app.db.session import async_session_factory
    from app.models.user import Role, User

    headers = await _auth_headers(client, unique_email)
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == unique_email))
        user = result.scalar_one()
        user.role = Role.VIEWER
        db.add(user)
        await db.commit()

    res = await client.post(
        "/api/v1/billing/subscription", json={"plan_slug": "pro"}, headers=headers
    )
    assert res.status_code == 403


async def test_subscription_is_tenant_isolated(client, unique_email):
    tenant_a_headers = await _auth_headers(client, unique_email)
    tenant_b_headers = await _auth_headers(client, f"b-{unique_email}")

    await client.post(
        "/api/v1/billing/subscription", json={"plan_slug": "pro"}, headers=tenant_a_headers
    )

    tenant_b_sub = await client.get("/api/v1/billing/subscription", headers=tenant_b_headers)
    assert tenant_b_sub.json()["plan"]["slug"] == "free"
