"""
Regression tests for a real bug caught by the live frontend (not by the
existing test suite): React 18/19 StrictMode's dev-mode double-effect
invocation fired two near-simultaneous requests for a brand-new tenant's
subscription, and the second one 500'd on a unique-constraint violation
(which the browser reported as a confusing CORS error, since FastAPI's
default exception handling doesn't attach CORS headers to an unhandled
500).

The full incident had two layers:
1. The check-then-insert race itself (two requests both see "no row yet").
2. A first fix caught the resulting IntegrityError and called
   `db.rollback()` on the request's shared session — which stopped the
   500, but `rollback()` expires every object already loaded on that
   session, including `current_user` (loaded earlier by `get_current_user`
   on the SAME session, since FastAPI dependency-caches `Depends(get_db)`
   per request). The next plain attribute access on `current_user`
   anywhere later in that request then tried an implicit async lazy-reload
   outside a valid greenlet context and raised `MissingGreenlet`.

The real fix: these idempotent seed/create writes happen on their OWN
dedicated session, never on the caller's `db` — see
`app/services/billing.py::seed_default_plans`'s docstring.
"""
import asyncio
import uuid

import pytest

from app.db.session import async_session_factory
from app.services.billing import ensure_subscription
from app.services.marketplace import ensure_default_agents_installed, list_installed

pytestmark = pytest.mark.asyncio


async def test_concurrent_ensure_subscription_does_not_crash(db_session):
    """Two 'simultaneous' calls for the same brand-new tenant, each on its
    own DB session — exactly how two real HTTP requests behave (each gets
    its own session via FastAPI's Depends(get_db)) — must both succeed and
    agree on the same subscription, not raise an IntegrityError."""
    tenant_id = uuid.uuid4()

    async def call():
        async with async_session_factory() as session:
            return await ensure_subscription(session, tenant_id)

    results = await asyncio.gather(call(), call())
    assert results[0].tenant_id == tenant_id
    assert results[1].tenant_id == tenant_id
    assert results[0].plan_id == results[1].plan_id


async def test_concurrent_ensure_default_agents_installed_does_not_crash(db_session):
    tenant_id = uuid.uuid4()

    async def call():
        async with async_session_factory() as session:
            await ensure_default_agents_installed(session, tenant_id)

    await asyncio.gather(call(), call())

    installed = await list_installed(db_session, tenant_id)
    # Must have installed the catalog exactly once, not duplicated rows —
    # the unique constraint would have caught duplicates anyway, but this
    # confirms the end state is actually correct, not just crash-free.
    slugs = [i.agent_slug for i in installed]
    assert len(slugs) == len(set(slugs))
    assert len(slugs) > 0


async def test_concurrent_http_requests_for_brand_new_tenant_subscription(client, unique_email):
    """End-to-end regression test for the exact incident: two concurrent
    HTTP requests to GET /billing/subscription for a tenant that has never
    had one created yet, sharing current_user + db via FastAPI's per-request
    dependency cache — exactly what the browser's two near-simultaneous
    requests did. Both must return 200, never a 500/MissingGreenlet."""
    await client.post(
        "/api/v1/auth/bootstrap", json={"email": unique_email, "password": "pw123456"}
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": unique_email, "password": "pw123456"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    responses = await asyncio.gather(
        client.get("/api/v1/billing/subscription", headers=headers),
        client.get("/api/v1/billing/subscription", headers=headers),
    )
    for res in responses:
        assert res.status_code == 200
        assert res.json()["plan"]["slug"] == "free"
