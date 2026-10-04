import pytest

from app.connectors.paradise_nepal.connector import (
    HotelNotFoundError,
    ParadiseNepalConnector,
    RoomNotFoundError,
    RoomUnavailableError,
)


def test_search_filters_by_location_and_rating():
    connector = ParadiseNepalConnector()
    results = connector.search_hotels(location="Pokhara")
    assert len(results) == 1
    assert results[0]["id"] == "PARADISE-H001"


def test_search_min_rating_filter():
    connector = ParadiseNepalConnector()
    results = connector.search_hotels(min_rating=4.5)
    assert all(h["rating"] >= 4.5 for h in results)


def test_get_hotel_details_unknown_id_raises():
    connector = ParadiseNepalConnector()
    with pytest.raises(HotelNotFoundError):
        connector.get_hotel_details("NOPE")


def test_check_availability_true_and_false():
    connector = ParadiseNepalConnector()
    assert connector.check_room_availability("PARADISE-H001", "deluxe", "2026-11-01") is True
    assert connector.check_room_availability("PARADISE-H001", "deluxe", "2099-01-01") is False


def test_check_availability_unknown_room_type_raises():
    connector = ParadiseNepalConnector()
    with pytest.raises(RoomNotFoundError):
        connector.check_room_availability("PARADISE-H001", "penthouse", "2026-11-01")


def test_create_booking_succeeds_when_available():
    connector = ParadiseNepalConnector()
    booking = connector.create_booking(
        "PARADISE-H001", "deluxe", "2026-11-01", "2026-11-03", "Anil Rai", guests=2
    )
    assert booking["status"] == "confirmed"
    assert booking["booking_id"].startswith("PARADISE-")


def test_create_booking_rejects_unavailable_date():
    connector = ParadiseNepalConnector()
    with pytest.raises(RoomUnavailableError):
        connector.create_booking(
            "PARADISE-H001", "deluxe", "2099-01-01", "2099-01-03", "Anil Rai"
        )


def test_create_booking_rejects_too_many_guests():
    connector = ParadiseNepalConnector()
    with pytest.raises(RoomUnavailableError):
        connector.create_booking(
            "PARADISE-H001", "deluxe", "2026-11-01", "2026-11-03", "Anil Rai", guests=5
        )
