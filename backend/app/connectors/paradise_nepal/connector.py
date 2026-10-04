"""
Mock Paradise Nepal (hotel booking) connector — same pattern as
app/connectors/tolemate/connector.py and ghar_nepal/connector.py.
Swapping this for a real integration later means rewriting only this
file's method bodies; the tools, agent, and entire core stay unchanged.
"""
from __future__ import annotations

import uuid

from app.connectors.paradise_nepal.mock_data import MOCK_HOTELS


class HotelNotFoundError(ValueError):
    pass


class RoomNotFoundError(ValueError):
    pass


class RoomUnavailableError(ValueError):
    pass


class ParadiseNepalConnector:
    def __init__(self) -> None:
        self._hotels = MOCK_HOTELS
        self._bookings: dict[str, dict] = {}

    def search_hotels(
        self, location: str | None = None, min_rating: float | None = None
    ) -> list[dict]:
        results = self._hotels
        if location:
            results = [h for h in results if h["location"].lower() == location.lower()]
        if min_rating is not None:
            results = [h for h in results if h["rating"] >= min_rating]
        return results

    def _get_hotel(self, hotel_id: str) -> dict:
        hotel = next((h for h in self._hotels if h["id"] == hotel_id), None)
        if hotel is None:
            raise HotelNotFoundError(f"No hotel found with id '{hotel_id}'.")
        return hotel

    def get_hotel_details(self, hotel_id: str) -> dict:
        return self._get_hotel(hotel_id)

    def _get_room(self, hotel: dict, room_type: str) -> dict:
        room = next(
            (r for r in hotel["rooms"] if r["room_type"].lower() == room_type.lower()), None
        )
        if room is None:
            raise RoomNotFoundError(
                f"Hotel '{hotel['name']}' has no room type '{room_type}'."
            )
        return room

    def check_room_availability(self, hotel_id: str, room_type: str, checkin: str) -> bool:
        hotel = self._get_hotel(hotel_id)
        room = self._get_room(hotel, room_type)
        return checkin in room["available_checkin_dates"]

    def create_booking(
        self,
        hotel_id: str,
        room_type: str,
        checkin: str,
        checkout: str,
        guest_name: str,
        guests: int = 1,
    ) -> dict:
        hotel = self._get_hotel(hotel_id)
        room = self._get_room(hotel, room_type)
        if checkin not in room["available_checkin_dates"]:
            raise RoomUnavailableError(
                f"'{room_type}' at '{hotel['name']}' is not available for check-in on {checkin}."
            )
        if guests > room["max_occupancy"]:
            raise RoomUnavailableError(
                f"'{room_type}' at '{hotel['name']}' only accommodates up to "
                f"{room['max_occupancy']} guests."
            )
        booking_id = f"PARADISE-{uuid.uuid4().hex[:8].upper()}"
        booking = {
            "booking_id": booking_id,
            "hotel_id": hotel_id,
            "hotel_name": hotel["name"],
            "room_type": room_type,
            "checkin": checkin,
            "checkout": checkout,
            "guest_name": guest_name,
            "guests": guests,
            "price_per_night_npr": room["price_per_night_npr"],
            "status": "confirmed",
        }
        self._bookings[booking_id] = booking
        return booking


paradise_nepal_connector = ParadiseNepalConnector()
