from app.agents.base_agent import BaseAgent
from app.connectors.base import BusinessModule
from app.connectors.ghar_nepal.agent import PropertyAgent
from app.connectors.ghar_nepal.tools import (
    CreatePropertyEnquiryTool,
    CreateViewingRequestTool,
    GetPropertyDetailsTool,
    SearchPropertiesTool,
)
from app.tools.base import Tool


class GharNepalModule(BusinessModule):
    name = "ghar_nepal"
    description = (
        "Ghar Nepal property marketplace (mock connector — no real API access "
        "confirmed yet; see app/connectors/ghar_nepal/connector.py)."
    )

    def get_tools(self) -> list[Tool]:
        return [
            SearchPropertiesTool(),
            GetPropertyDetailsTool(),
            CreatePropertyEnquiryTool(),
            CreateViewingRequestTool(),
        ]

    def get_agents(self) -> list[BaseAgent]:
        return [PropertyAgent()]
