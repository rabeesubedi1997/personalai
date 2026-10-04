import pytest

from app.connectors.tolemate.connector import (
    ProviderNotFoundError,
    ProviderUnavailableError,
    TolemateConnector,
)


def test_search_providers_filters_by_service_and_location():
    connector = TolemateConnector()
    results = connector.search_providers("electrician", "Lalitpur")
    assert len(results) == 1
    assert results[0]["id"] == "PRV-001"


def test_search_providers_no_location_filter_returns_all_matching_service():
    connector = TolemateConnector()
    results = connector.search_providers("electrician")
    assert len(results) == 2


def test_check_availability_true_and_false():
    connector = TolemateConnector()
    assert connector.check_availability("PRV-001", "2026-10-10") is True
    assert connector.check_availability("PRV-001", "2099-01-01") is False


def test_check_availability_unknown_provider_raises():
    connector = TolemateConnector()
    with pytest.raises(ProviderNotFoundError):
        connector.check_availability("NOPE", "2026-10-10")


def test_create_booking_succeeds_when_available():
    connector = TolemateConnector()
    booking = connector.create_booking("PRV-001", "2026-10-10", "Ram Shrestha")
    assert booking["status"] == "confirmed"
    assert booking["booking_id"].startswith("TOLEMATE-")


def test_create_booking_rejects_unavailable_date():
    connector = TolemateConnector()
    with pytest.raises(ProviderUnavailableError):
        connector.create_booking("PRV-001", "2099-01-01", "Ram Shrestha")


@pytest.mark.asyncio
async def test_aget_schedule_returns_providers_available_dates():
    connector = TolemateConnector()
    schedule = await connector.aget_schedule("PRV-001")
    assert schedule["available_dates"] == ["2026-10-10", "2026-10-11", "2026-10-14"]


@pytest.mark.asyncio
async def test_aget_schedule_unknown_provider_raises():
    connector = TolemateConnector()
    with pytest.raises(ProviderNotFoundError):
        await connector.aget_schedule("NOPE")
