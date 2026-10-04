"""Paradise Nepal (hotel booking) tools — same pattern as
app/connectors/tolemate/tools.py. Search/lookup/availability is READ,
creating a new booking is SAFE_WRITE."""
from __future__ import annotations

from typing import Any

from app.connectors.paradise_nepal.connector import (
    HotelNotFoundError,
    RoomNotFoundError,
    RoomUnavailableError,
    paradise_nepal_connector,
)
from app.tools.base import PermissionLevel, Tool, ToolContext, ToolExecutionError, ToolOutput


class SearchHotelsTool(Tool):
    name = "search_hotels"
    description = "Search Paradise Nepal hotels by location and optional minimum rating."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "e.g. Pokhara"},
            "min_rating": {"type": "number"},
        },
    }
    permission_level = PermissionLevel.READ
    timeout_seconds = 10.0

    async def execute(
        self,
        context: ToolContext,
        location: str | None = None,
        min_rating: float | None = None,
        **kwargs: Any,
    ) -> ToolOutput:
        results = paradise_nepal_connector.search_hotels(location, min_rating)
        if not results:
            return ToolOutput(content="No matching hotels found.", data={"hotels": []})
        summary = "; ".join(
            f"{h['name']} ({h['location']}, rating {h['rating']}, id={h['id']})" for h in results
        )
        return ToolOutput(content=summary, data={"hotels": results})


class GetHotelDetailsTool(Tool):
    name = "get_hotel_details"
    description = "Get room types, rates, and amenities for one Paradise Nepal hotel by id."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"hotel_id": {"type": "string"}},
        "required": ["hotel_id"],
    }
    permission_level = PermissionLevel.READ
    timeout_seconds = 10.0

    async def execute(self, context: ToolContext, hotel_id: str, **kwargs: Any) -> ToolOutput:
        try:
            hotel = paradise_nepal_connector.get_hotel_details(hotel_id)
        except HotelNotFoundError as exc:
            raise ToolExecutionError(str(exc)) from exc
        rooms_summary = "; ".join(
            f"{r['room_type']} (up to {r['max_occupancy']} guests, NPR {r['price_per_night_npr']:,}/night)"
            for r in hotel["rooms"]
        )
        amenities = ", ".join(hotel["amenities"])
        return ToolOutput(
            content=f"{hotel['name']} in {hotel['location']} — rooms: {rooms_summary}. Amenities: {amenities}.",
            data=hotel,
        )


class CheckRoomAvailabilityTool(Tool):
    name = "check_room_availability"
    description = "Check whether a specific room type at a Paradise Nepal hotel is available for a check-in date."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "hotel_id": {"type": "string"},
            "room_type": {"type": "string"},
            "checkin": {"type": "string", "description": "YYYY-MM-DD"},
        },
        "required": ["hotel_id", "room_type", "checkin"],
    }
    permission_level = PermissionLevel.READ
    timeout_seconds = 10.0

    async def execute(
        self, context: ToolContext, hotel_id: str, room_type: str, checkin: str, **kwargs: Any
    ) -> ToolOutput:
        try:
            available = paradise_nepal_connector.check_room_availability(
                hotel_id, room_type, checkin
            )
        except (HotelNotFoundError, RoomNotFoundError) as exc:
            raise ToolExecutionError(str(exc)) from exc
        return ToolOutput(
            content=(
                f"{room_type} at {hotel_id} is "
                f"{'available' if available else 'NOT available'} for check-in on {checkin}."
            ),
            data={"hotel_id": hotel_id, "room_type": room_type, "checkin": checkin, "available": available},
        )


class CreateHotelBookingTool(Tool):
    name = "create_hotel_booking"
    description = (
        "Create a new Paradise Nepal hotel booking once availability has been confirmed."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "hotel_id": {"type": "string"},
            "room_type": {"type": "string"},
            "checkin": {"type": "string", "description": "YYYY-MM-DD"},
            "checkout": {"type": "string", "description": "YYYY-MM-DD"},
            "guest_name": {"type": "string"},
            "guests": {"type": "integer"},
        },
        "required": ["hotel_id", "room_type", "checkin", "checkout", "guest_name"],
    }
    permission_level = PermissionLevel.SAFE_WRITE
    timeout_seconds = 10.0

    async def execute(
        self,
        context: ToolContext,
        hotel_id: str,
        room_type: str,
        checkin: str,
        checkout: str,
        guest_name: str,
        guests: int = 1,
        **kwargs: Any,
    ) -> ToolOutput:
        try:
            booking = paradise_nepal_connector.create_booking(
                hotel_id, room_type, checkin, checkout, guest_name, guests
            )
        except (HotelNotFoundError, RoomNotFoundError, RoomUnavailableError) as exc:
            raise ToolExecutionError(str(exc)) from exc
        return ToolOutput(
            content=(
                f"Booking confirmed: {booking['booking_id']} at {booking['hotel_name']} "
                f"({booking['room_type']}, {booking['checkin']} to {booking['checkout']})."
            ),
            data=booking,
        )
