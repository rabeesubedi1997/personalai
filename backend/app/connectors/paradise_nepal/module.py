from app.agents.base_agent import BaseAgent
from app.connectors.base import BusinessModule
from app.connectors.paradise_nepal.agent import HotelBookingAgent
from app.connectors.paradise_nepal.tools import (
    CheckRoomAvailabilityTool,
    CreateHotelBookingTool,
    GetHotelDetailsTool,
    SearchHotelsTool,
)
from app.tools.base import Tool


class ParadiseNepalModule(BusinessModule):
    name = "paradise_nepal"
    description = (
        "Paradise Nepal hotel booking platform (mock connector — no real API "
        "access confirmed yet; see app/connectors/paradise_nepal/connector.py). "
        "Confirmed to be a hotel booking business by inspecting the real site, "
        "correcting the master spec's original film-production assumption."
    )

    def get_tools(self) -> list[Tool]:
        return [
            SearchHotelsTool(),
            GetHotelDetailsTool(),
            CheckRoomAvailabilityTool(),
            CreateHotelBookingTool(),
        ]

    def get_agents(self) -> list[BaseAgent]:
        return [HotelBookingAgent()]
