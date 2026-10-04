from app.agents.base_agent import BaseAgent
from app.connectors.base import BusinessModule
from app.connectors.tolemate.agent import ServiceBookingAgent
from app.connectors.tolemate.tools import (
    CheckProviderAvailabilityTool,
    CreateServiceBookingTool,
    SearchServiceProvidersTool,
)
from app.tools.base import Tool


class TolemateModule(BusinessModule):
    name = "tolemate"
    description = (
        "Tolemate service marketplace (mock connector — no real API access "
        "confirmed yet; see app/connectors/tolemate/connector.py)."
    )

    def get_tools(self) -> list[Tool]:
        return [
            SearchServiceProvidersTool(),
            CheckProviderAvailabilityTool(),
            CreateServiceBookingTool(),
        ]

    def get_agents(self) -> list[BaseAgent]:
        return [ServiceBookingAgent()]
