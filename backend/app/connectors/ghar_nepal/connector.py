"""
Mock Ghar Nepal connector (spec Section 16/19). Exactly the same pattern
as app/connectors/tolemate/connector.py: swapping this for a real
integration later means rewriting only this file's method bodies — the
tools, the agent, and the entire core stay unchanged.
"""
from __future__ import annotations

import uuid

from app.connectors.ghar_nepal.mock_data import MOCK_PROPERTIES


class PropertyNotFoundError(ValueError):
    pass


class GharNepalConnector:
    def __init__(self) -> None:
        self._properties = MOCK_PROPERTIES
        self._enquiries: dict[str, dict] = {}
        self._viewing_requests: dict[str, dict] = {}

    def search_properties(
        self,
        property_type: str | None = None,
        location: str | None = None,
        max_budget_npr: int | None = None,
        min_bedrooms: int | None = None,
    ) -> list[dict]:
        results = [p for p in self._properties if p["status"] == "available"]
        if property_type:
            results = [p for p in results if p["property_type"].lower() == property_type.lower()]
        if location:
            results = [p for p in results if p["location"].lower() == location.lower()]
        if max_budget_npr is not None:
            results = [p for p in results if p["price_npr"] <= max_budget_npr]
        if min_bedrooms is not None:
            results = [p for p in results if p["bedrooms"] >= min_bedrooms]
        return results

    def _get(self, property_id: str) -> dict:
        prop = next((p for p in self._properties if p["id"] == property_id), None)
        if prop is None:
            raise PropertyNotFoundError(f"No property found with id '{property_id}'.")
        return prop

    def get_property(self, property_id: str) -> dict:
        return self._get(property_id)

    def create_enquiry(self, property_id: str, customer_name: str, message: str = "") -> dict:
        prop = self._get(property_id)
        enquiry_id = f"GN-ENQ-{uuid.uuid4().hex[:8].upper()}"
        enquiry = {
            "enquiry_id": enquiry_id,
            "property_id": property_id,
            "property_title": prop["title"],
            "customer_name": customer_name,
            "message": message,
            "status": "received",
        }
        self._enquiries[enquiry_id] = enquiry
        return enquiry

    def create_viewing_request(
        self, property_id: str, customer_name: str, preferred_date: str
    ) -> dict:
        prop = self._get(property_id)
        if prop["status"] != "available":
            raise PropertyNotFoundError(
                f"Property '{property_id}' is not currently available for viewing."
            )
        viewing_id = f"GN-VIEW-{uuid.uuid4().hex[:8].upper()}"
        viewing = {
            "viewing_id": viewing_id,
            "property_id": property_id,
            "property_title": prop["title"],
            "customer_name": customer_name,
            "preferred_date": preferred_date,
            "status": "requested",
        }
        self._viewing_requests[viewing_id] = viewing
        return viewing


ghar_nepal_connector = GharNepalConnector()
