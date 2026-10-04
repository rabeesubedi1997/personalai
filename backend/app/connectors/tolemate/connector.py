"""
Mock Tolemate connector (spec Section 17/19). Swapping this for a real
integration later means rewriting ONLY this file's method bodies — the
tools in tools.py, the agent in agent.py, and everything in the core
(orchestrator, tool registry, approval engine) stay exactly as they are.
"""
from __future__ import annotations

import uuid

from app.connectors.tolemate.mock_data import MOCK_PROVIDERS


class ProviderNotFoundError(ValueError):
    pass


class ProviderUnavailableError(ValueError):
    pass


class TolemateConnector:
    def __init__(self) -> None:
        self._providers = MOCK_PROVIDERS
        # In-memory only — a mock has nothing real to persist to. A real
        # connector wouldn't store bookings itself either; it would call
        # Tolemate's own API, which is the actual source of truth.
        self._bookings: dict[str, dict] = {}

    def search_providers(self, service: str, location: str | None = None) -> list[dict]:
        results = [
            p for p in self._providers if p["service_type"].lower() == service.lower()
        ]
        if location:
            results = [p for p in results if p["location"].lower() == location.lower()]
        return results

    def _get_provider(self, provider_id: str) -> dict:
        provider = next((p for p in self._providers if p["id"] == provider_id), None)
        if provider is None:
            raise ProviderNotFoundError(f"No provider found with id '{provider_id}'.")
        return provider

    def check_availability(self, provider_id: str, date: str) -> bool:
        provider = self._get_provider(provider_id)
        return date in provider["available_dates"]

    def create_booking(
        self, provider_id: str, date: str, customer_name: str, notes: str = ""
    ) -> dict:
        provider = self._get_provider(provider_id)
        if date not in provider["available_dates"]:
            raise ProviderUnavailableError(
                f"Provider '{provider['name']}' is not available on {date}."
            )
        booking_id = f"TOLEMATE-{uuid.uuid4().hex[:8].upper()}"
        booking = {
            "booking_id": booking_id,
            "provider_id": provider_id,
            "provider_name": provider["name"],
            "date": date,
            "customer_name": customer_name,
            "notes": notes,
            "status": "confirmed",
        }
        self._bookings[booking_id] = booking
        return booking


# Module-level singleton — mirrors how a real connector would hold one
# configured API client for the process, not one per tool instance.
tolemate_connector = TolemateConnector()
