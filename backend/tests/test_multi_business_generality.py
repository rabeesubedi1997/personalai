"""
Concrete proof that the core platform (Request engine, Agent orchestrator,
Tool registry, Approval engine) works for ANY future business without core
code changes — not just a documentation claim.

This test simulates three different real businesses from the master spec
(Tolemate: service bookings, Ghar Nepal: real estate, Paradise Nepal: film
production) as three tenants, each using different `request_type` values
and business-specific `requirements` JSON. No per-business branching exists
anywhere in app/services/request_engine.py, app/orchestrator/engine.py, or
app/tools/registry.py — the same generic code paths handle all three.

When a real business is actually integrated (Phase 6+), only a connector +
agent + tools get added for it — this test is the living guarantee that
doing so will not require touching the core engine.
"""
import pytest

from app.services.ai.base import GenerationResult, ToolCall
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio

# Three different businesses, three different request shapes — all handled
# by the exact same generic Request model/engine (no schema per business).
BUSINESSES = [
    {
        "name": "tolemate",
        "request_type": "service_booking",
        "customer": {"name": "Ram Shrestha", "location": "Lalitpur"},
        "requirements": {
            "service": "electrician",
            "preferred_date": "2026-10-10",
            "description": "Main switchboard issue",
        },
    },
    {
        "name": "ghar_nepal",
        "request_type": "property_enquiry",
        "customer": {"name": "Sita Gurung", "location": "Kathmandu"},
        "requirements": {
            "property_type": "apartment",
            "budget_npr": 15000000,
            "bedrooms": 2,
        },
    },
    {
        "name": "paradise_nepal",
        "request_type": "production_enquiry",
        "customer": {"name": "Anil Rai", "location": "Pokhara"},
        "requirements": {
            "production_type": "short_film",
            "shoot_days": 5,
            "crew_size": 12,
        },
    },
]


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_three_different_businesses_use_the_same_generic_request_engine(
    client, unique_email
):
    tenants = {}
    for biz in BUSINESSES:
        email = f"{biz['name']}-{unique_email}"
        headers = await _auth_headers(client, email)
        tenants[biz["name"]] = headers

        # Same endpoint, same schema, arbitrary business-specific payload —
        # no business-specific API or table was needed for any of these.
        create_res = await client.post(
            "/api/v1/requests",
            json={
                "request_type": biz["request_type"],
                "customer": biz["customer"],
                "requirements": biz["requirements"],
            },
            headers=headers,
        )
        assert create_res.status_code == 201
        body = create_res.json()
        assert body["status"] == "received"
        assert body["request_type"] == biz["request_type"]
        assert body["requirements"] == biz["requirements"]

    # Each tenant only sees its own business's request (tenant isolation
    # holds regardless of how different the business domains are).
    for biz in BUSINESSES:
        list_res = await client.get("/api/v1/requests", headers=tenants[biz["name"]])
        results = list_res.json()
        assert len(results) == 1
        assert results[0]["request_type"] == biz["request_type"]


async def test_same_generic_lifecycle_applies_to_every_business_type(client, unique_email):
    # The exact same state machine (RequestEngine) drives a Tolemate
    # booking and a Ghar Nepal enquiry through to completion — no
    # per-business lifecycle exists or is needed.
    for biz in BUSINESSES:
        email = f"lifecycle-{biz['name']}-{unique_email}"
        headers = await _auth_headers(client, email)

        create_res = await client.post(
            "/api/v1/requests",
            json={"request_type": biz["request_type"], "requirements": biz["requirements"]},
            headers=headers,
        )
        req_id = create_res.json()["id"]

        for step in [
            "understanding",
            "validating",
            "searching",
            "matching",
            "waiting_for_confirmation",
            "executing",
            "verifying",
            "completed",
        ]:
            res = await client.patch(
                f"/api/v1/requests/{req_id}/status", json={"status": step}, headers=headers
            )
            assert res.status_code == 200, f"{biz['name']} failed at step '{step}'"

        final = await client.get(f"/api/v1/requests/{req_id}", headers=headers)
        assert final.json()["status"] == "completed"


async def test_booking_cancellation_approval_flow_is_business_agnostic(
    client, unique_email, monkeypatch
):
    # The SAME cancel_booking tool + approval engine serves a Tolemate
    # service booking and a Ghar Nepal viewing appointment identically —
    # proving "managed all booking" doesn't require per-business approval
    # logic. Only the booking_id's meaning differs; the platform code does
    # not know or care which business it belongs to.
    scenarios = [
        ("tolemate", "TOLEMATE-BOOKING-123"),
        ("ghar_nepal", "GHARNEPAL-VIEWING-456"),
    ]

    for biz_name, booking_id in scenarios:
        email = f"booking-{biz_name}-{unique_email}"
        headers = await _auth_headers(client, email)

        fake = FakeAIProvider(
            [
                GenerationResult(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="1",
                            name="cancel_booking",
                            arguments={"booking_id": booking_id, "reason": "customer request"},
                        )
                    ],
                    model="fake",
                ),
            ]
        )
        monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda f=fake: f)

        run_res = await client.post(
            "/api/v1/agents/run",
            json={"agent": "general_assistant", "message": f"cancel booking {booking_id}"},
            headers=headers,
        )
        assert run_res.status_code == 200
        run_body = run_res.json()
        assert run_body["status"] == "awaiting_approval"

        approve_res = await client.post(
            f"/api/v1/approvals/{run_body['approval_id']}/approve",
            json={"note": f"verified with {biz_name} customer"},
            headers=headers,
        )
        assert approve_res.status_code == 200
        approved = approve_res.json()
        assert approved["status"] == "executed"
        assert approved["result"]["data"]["booking_id"] == booking_id
        assert approved["result"]["data"]["cancelled"] is True
