from app.agents.base_agent import BaseAgent
from app.connectors.base import BusinessModule
from app.connectors.tolemate.agent import ServiceBookingAgent
from app.connectors.tolemate.tools import (
    CheckProviderAvailabilityTool,
    CreateServiceBookingTool,
    GetProviderScheduleTool,
    SearchServiceProvidersTool,
)
from app.tools.base import Tool


class TolemateModule(BusinessModule):
    name = "tolemate"
    description = (
        "Tolemate service marketplace — uses a built-in mock connector until "
        "a tenant configures a real one via Integrations > Business data "
        "connections (see app/connectors/tolemate/connector_factory.py)."
    )

    def get_tools(self) -> list[Tool]:
        return [
            SearchServiceProvidersTool(),
            GetProviderScheduleTool(),
            CheckProviderAvailabilityTool(),
            CreateServiceBookingTool(),
        ]

    def get_agents(self) -> list[BaseAgent]:
        return [ServiceBookingAgent()]
