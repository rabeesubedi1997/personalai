import pytest

from app.connectors.ghar_nepal.connector import GharNepalConnector, PropertyNotFoundError


def test_search_filters_by_type_location_budget_bedrooms():
    connector = GharNepalConnector()
    results = connector.search_properties(property_type="apartment", location="Lalitpur")
    # GN-003 is also an apartment in Lalitpur but status="sold" — must be excluded.
    assert len(results) == 1
    assert results[0]["id"] == "GN-001"


def test_search_excludes_sold_properties_by_default():
    connector = GharNepalConnector()
    results = connector.search_properties()
    assert all(p["status"] == "available" for p in results)
    assert "GN-003" not in [p["id"] for p in results]


def test_search_budget_filter():
    connector = GharNepalConnector()
    results = connector.search_properties(max_budget_npr=15_000_000)
    assert all(p["price_npr"] <= 15_000_000 for p in results)


def test_get_property_unknown_id_raises():
    connector = GharNepalConnector()
    with pytest.raises(PropertyNotFoundError):
        connector.get_property("NOPE")


def test_create_enquiry_succeeds():
    connector = GharNepalConnector()
    enquiry = connector.create_enquiry("GN-001", "Sita Gurung", "Interested in viewing soon")
    assert enquiry["status"] == "received"
    assert enquiry["enquiry_id"].startswith("GN-ENQ-")


def test_create_viewing_request_rejects_sold_property():
    connector = GharNepalConnector()
    with pytest.raises(PropertyNotFoundError):
        connector.create_viewing_request("GN-003", "Sita Gurung", "2026-10-15")


def test_create_viewing_request_succeeds_for_available_property():
    connector = GharNepalConnector()
    viewing = connector.create_viewing_request("GN-001", "Sita Gurung", "2026-10-15")
    assert viewing["status"] == "requested"
    assert viewing["viewing_id"].startswith("GN-VIEW-")
