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


class MissingCustomerInfoError(ValueError):
    """Raised when a real connector needs info the mock never required
    (e.g. an email, to register a real customer account) and the caller
    didn't supply it. Mock bookings never raise this."""


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

    # --- Async wrappers -------------------------------------------------
    # The real connector (real_connector.py) does actual network I/O, so
    # its methods are async. Tools call through this same async interface
    # for both, rather than branching on which connector they got back —
    # these wrappers just call the sync logic above directly (no real I/O
    # here, so there's nothing to actually await).

    async def asearch_providers(self, service: str, location: str | None = None) -> list[dict]:
        return self.search_providers(service, location)

    async def acheck_availability(self, provider_id: str, date: str) -> bool:
        return self.check_availability(provider_id, date)

    async def aget_schedule(self, provider_id: str) -> dict:
        # The mock has no weekly open-hours concept — just a fixed list of
        # discrete dates it's "available" on — so that's what's offered
        # here instead of the real connector's Mon-Fri-style open_days.
        provider = self._get_provider(provider_id)
        return {"provider_id": provider_id, "available_dates": provider["available_dates"]}

    async def acreate_booking(
        self,
        provider_id: str,
        date: str,
        customer_name: str,
        notes: str = "",
        customer_email: str | None = None,
    ) -> dict:
        # customer_email is accepted (and ignored) so tools.py can pass it
        # uniformly to whichever connector it got back.
        return self.create_booking(provider_id, date, customer_name, notes)


# Module-level singleton — mirrors how a real connector would hold one
# configured API client for the process, not one per tool instance.
tolemate_connector = TolemateConnector()
