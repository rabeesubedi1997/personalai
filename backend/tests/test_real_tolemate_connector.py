"""
Tests for RealTolemateConnector against a stubbed HTTP transport (no real
ToleMate instance needs to be running) — mirrors the pattern already used
for OllamaProvider in test_ai_provider.py. A real, live round-trip against
an actual running ToleMate instance is verified separately (manual check,
not CI), same as the Ollama smoke test.
"""
import httpx
import pytest

from app.connectors.tolemate.connector import (
    MissingCustomerInfoError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)
from app.connectors.tolemate.real_connector import RealTolemateConnector, _decode_id, _encode_id

pytestmark = pytest.mark.asyncio


def _json_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(status_code, json=payload, request=httpx.Request("GET", "http://test"))


async def test_encode_decode_id_roundtrip():
    assert _decode_id(_encode_id(5, 42)) == (5, 42)


async def test_decode_id_rejects_garbage():
    with pytest.raises(ProviderNotFoundError):
        _decode_id("not-a-real-id")


async def test_search_providers_maps_real_response_shape(monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        if url.endswith("/availability"):
            return _json_response(
                200, {"availability": [{"day_of_week": 1, "start_time": "09:00", "end_time": "17:00", "is_available": True}]}
            )
        assert url.endswith("/api/services/search")
        return _json_response(
            200,
            {
                "data": [
                    {
                        "id": 7,
                        "name": "Deep House Cleaning",
                        "price": 200,
                        "vendor": {
                            "id": 2,
                            "business_name": "Sparkling Clean Services",
                            "rating": 4.9,
                            "user": {"lat": 27.7172, "lng": 85.3240},
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    connector = RealTolemateConnector("http://tolemate.test")
    results = await connector.asearch_providers("deep house cleaning", "Kathmandu")

    assert len(results) == 1
    p = results[0]
    assert p["id"] == "v2-s7"
    assert p["vendor_name"] == "Sparkling Clean Services"
    assert p["location"] == "Kathmandu"
    assert p["price"] == 200
    # The top result's schedule is fetched eagerly and folded in, so the
    # agent can offer it without a second, separate LLM round-trip.
    assert p["open_days"] == ["Monday 09:00-17:00"]


async def test_search_falls_back_to_broad_query_when_geo_filter_empty(monkeypatch):
    calls = []

    async def fake_get(self, url, params=None, **kwargs):
        if url.endswith("/availability"):
            return _json_response(200, {"availability": []})
        calls.append(params or {})
        if "lat" in (params or {}):
            return _json_response(200, {"data": []})
        return _json_response(
            200,
            {"data": [{"id": 1, "name": "X", "vendor": {"id": 1, "business_name": "Y", "rating": 5}}]},
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    connector = RealTolemateConnector("http://tolemate.test")
    results = await connector.asearch_providers("plumber", "Kathmandu")

    assert len(results) == 1
    assert len(calls) == 2
    assert "lat" in calls[0]
    assert "lat" not in calls[1]


async def test_search_unrecognized_location_skips_geo_filter_entirely(monkeypatch):
    calls = []

    async def fake_get(self, url, params=None, **kwargs):
        calls.append(params or {})
        return _json_response(200, {"data": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    connector = RealTolemateConnector("http://tolemate.test")
    # A service term with no category mapping, so only the plain query is
    # tried — isolates this test from the category-fallback behavior below.
    await connector.asearch_providers("aquarium cleaning", "Nowhereville")

    assert len(calls) == 1
    assert "lat" not in calls[0]


async def test_search_falls_back_to_category_when_query_text_matches_nothing(monkeypatch):
    calls = []

    async def fake_get(self, url, params=None, **kwargs):
        calls.append((url, params or {}))
        if url.endswith("/api/categories"):
            return _json_response(200, [{"id": 8, "name": "Plumbing"}])
        if (params or {}).get("category_id") == 8:
            return _json_response(
                200,
                {
                    "data": [
                        {
                            "id": 3,
                            "name": "Pipe Repair and Installation",
                            "price": "500.00",
                            "vendor": {"id": 5, "business_name": "Quick Fix Plumbing", "rating": "4.60"},
                        }
                    ]
                },
            )
        return _json_response(200, {"data": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    connector = RealTolemateConnector("http://tolemate.test")
    results = await connector.asearch_providers("plumber")

    assert len(results) == 1
    assert results[0]["vendor_name"] == "Quick Fix Plumbing"
    urls = [u for u, _ in calls]
    assert any(u.endswith("/api/categories") for u in urls)


async def test_search_with_unmapped_term_never_calls_categories(monkeypatch):
    calls = []

    async def fake_get(self, url, params=None, **kwargs):
        calls.append(url)
        return _json_response(200, {"data": []})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    connector = RealTolemateConnector("http://tolemate.test")
    await connector.asearch_providers("aquarium cleaning")

    assert not any(u.endswith("/api/categories") for u in calls)


async def test_get_schedule_returns_readable_open_days(monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        return _json_response(
            200,
            {
                "availability": [
                    {"day_of_week": 0, "start_time": "09:00", "end_time": "17:00", "is_available": False},
                    {"day_of_week": 1, "start_time": "09:00", "end_time": "17:00", "is_available": True},
                    {"day_of_week": 2, "start_time": "09:00", "end_time": "17:00", "is_available": True},
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    connector = RealTolemateConnector("http://tolemate.test")
    schedule = await connector.aget_schedule(_encode_id(2, 7))

    assert schedule["open_days"] == ["Monday 09:00-17:00", "Tuesday 09:00-17:00"]


async def test_get_schedule_vendor_not_found(monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        return httpx.Response(404, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    connector = RealTolemateConnector("http://tolemate.test")
    with pytest.raises(ProviderNotFoundError):
        await connector.aget_schedule(_encode_id(999, 1))


async def test_check_availability_maps_day_of_week(monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        return _json_response(200, {"availability": [{"day_of_week": 1, "is_available": True}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    connector = RealTolemateConnector("http://tolemate.test")
    # 2026-10-05 is a Monday -> ToleMate's day_of_week=1
    assert await connector.acheck_availability(_encode_id(2, 7), "2026-10-05") is True


async def test_check_availability_vendor_not_found(monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        return httpx.Response(404, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    connector = RealTolemateConnector("http://tolemate.test")
    with pytest.raises(ProviderNotFoundError):
        await connector.acheck_availability(_encode_id(999, 1), "2026-10-05")


async def test_create_booking_requires_email():
    connector = RealTolemateConnector("http://tolemate.test")
    with pytest.raises(MissingCustomerInfoError):
        await connector.acreate_booking(_encode_id(2, 7), "2026-10-05", "Ram Shrestha")


async def test_create_booking_registers_and_books(monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        return _json_response(200, {"availability": [{"day_of_week": 1, "is_available": True}]})

    async def fake_post(self, url, headers=None, json=None, **kwargs):
        if url.endswith("/api/register"):
            assert json["email"] == "ram@example.com"
            return _json_response(201, {"access_token": "tok123", "user": {"id": 99}})
        if url.endswith("/api/bookings"):
            assert headers["Authorization"] == "Bearer tok123"
            assert json["service_id"] == 7
            return _json_response(201, {"booking": {"id": 55, "status": "pending"}})
        raise AssertionError(f"unexpected POST {url}")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    connector = RealTolemateConnector("http://tolemate.test")
    booking = await connector.acreate_booking(
        _encode_id(2, 7), "2026-10-05", "Ram Shrestha", customer_email="ram@example.com"
    )

    assert booking["booking_id"] == "TOLEMATE-55"
    assert booking["status"] == "pending"


async def test_create_booking_rejects_when_unavailable(monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        return _json_response(200, {"availability": [{"day_of_week": 1, "is_available": False}]})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    connector = RealTolemateConnector("http://tolemate.test")
    with pytest.raises(ProviderUnavailableError):
        await connector.acreate_booking(
            _encode_id(2, 7), "2026-10-05", "Ram", customer_email="ram@example.com"
        )


async def test_create_booking_duplicate_email_gives_clear_error(monkeypatch):
    async def fake_get(self, url, params=None, **kwargs):
        return _json_response(200, {"availability": [{"day_of_week": 1, "is_available": True}]})

    async def fake_post(self, url, headers=None, json=None, **kwargs):
        return _json_response(422, {"errors": {"email": ["already taken"]}})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    connector = RealTolemateConnector("http://tolemate.test")
    with pytest.raises(ProviderUnavailableError, match="already has a ToleMate account"):
        await connector.acreate_booking(
            _encode_id(2, 7), "2026-10-05", "Ram", customer_email="ram@example.com"
        )
