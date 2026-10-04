"""
The concrete guarantee behind "you can add multiple businesses later":
this test defines a brand-new business module from scratch, right here in
the test file — not by editing app/tools/registry.py, app/agents/registry.py,
or any other core file — registers it with one function call, and proves
it is immediately usable through the real API: listed, selectable, and
able to run a full agent turn using its own tool.

This simulates adding Paradise Nepal (film production enquiries) as a
concrete stand-in for "any future business," deliberately using different
domain vocabulary than Tolemate's service bookings to show nothing here is
tied to one business's shape.
"""
from typing import Any

import pytest

from app.agents.base_agent import BaseAgent
from app.connectors.base import BusinessModule
from app.connectors.registry import register_business_module
from app.services.ai.base import GenerationResult, ToolCall
from app.tools.base import PermissionLevel, Tool, ToolContext, ToolOutput
from tests.fakes import FakeAIProvider

pytestmark = pytest.mark.asyncio


class _SearchCrewAvailabilityTool(Tool):
    """A fictional Paradise Nepal-style tool — crew-scheduling lookup for a
    film production, nothing like Tolemate's bookings or Ghar Nepal's
    properties. Proves the platform imposes no business-shape assumptions."""

    name = "search_crew_availability"
    description = "Search for available film crew by role and date."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "role": {"type": "string", "description": "e.g. cinematographer, gaffer"},
            "date": {"type": "string"},
        },
        "required": ["role", "date"],
    }
    permission_level = PermissionLevel.READ
    timeout_seconds = 10.0

    async def execute(self, context: ToolContext, role: str, date: str, **kwargs: Any) -> ToolOutput:
        return ToolOutput(
            content=f"2 {role}(s) available on {date}: Hari Thapa, Suman K.C.",
            data={"role": role, "date": date, "crew": ["Hari Thapa", "Suman K.C."]},
        )


class _ProductionEnquiryAgent(BaseAgent):
    name = "paradise_nepal_demo_agent"
    description = "Demo Paradise Nepal production enquiry agent, defined entirely in a test."
    system_prompt = "You help with film production crew enquiries. Use your tool; never invent crew names."
    allowed_tools = ["search_crew_availability"]


class _ParadiseNepalDemoModule(BusinessModule):
    name = "paradise_nepal_demo"
    description = "Ad-hoc demo module proving the extensibility mechanism — not a real connector."

    def get_tools(self) -> list[Tool]:
        return [_SearchCrewAvailabilityTool()]

    def get_agents(self) -> list[BaseAgent]:
        return [_ProductionEnquiryAgent()]


@pytest.fixture(scope="module", autouse=True)
def _register_demo_business_module():
    # This is the entire "add a business" action — one function call, no
    # other file touched. Registered once for this test module.
    register_business_module(_ParadiseNepalDemoModule())


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_new_business_tool_appears_in_tool_registry(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.get("/api/v1/tools", headers=headers)
    tool_names = [t["name"] for t in res.json()]
    assert "search_crew_availability" in tool_names


async def test_new_business_agent_appears_in_agent_registry(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    res = await client.get("/api/v1/agents", headers=headers)
    agent_names = [a["name"] for a in res.json()]
    assert "paradise_nepal_demo_agent" in agent_names


async def test_new_business_agent_runs_end_to_end(client, unique_email, monkeypatch):
    fake = FakeAIProvider(
        [
            GenerationResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="1",
                        name="search_crew_availability",
                        arguments={"role": "cinematographer", "date": "2026-11-01"},
                    )
                ],
                model="fake",
            ),
            GenerationResult(content="Two cinematographers are available.", model="fake"),
        ]
    )
    monkeypatch.setattr("app.api.v1.agents.get_ai_provider", lambda: fake)
    headers = await _auth_headers(client, unique_email)

    res = await client.post(
        "/api/v1/agents/run",
        json={
            "agent": "paradise_nepal_demo_agent",
            "message": "Is a cinematographer available on Nov 1?",
        },
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["tool_trace"][0]["tool"] == "search_crew_availability"
    assert "Hari Thapa" in body["tool_trace"][0]["result"]
