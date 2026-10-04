"""Tolemate tools — thin wrappers around TolemateConnector. Each declares
its own permission level per spec Section 11: searching/checking is READ,
creating a new booking is SAFE_WRITE (a new commitment, not a change to an
existing one). Cancelling an existing booking uses the platform's generic
`cancel_booking` tool (SENSITIVE, approval-gated) rather than a
Tolemate-specific duplicate — see app/tools/mock_tools.py."""
from __future__ import annotations

from typing import Any

from app.connectors.tolemate.connector import (
    ProviderNotFoundError,
    ProviderUnavailableError,
    tolemate_connector,
)
from app.tools.base import PermissionLevel, Tool, ToolContext, ToolExecutionError, ToolOutput


class SearchServiceProvidersTool(Tool):
    name = "search_service_providers"
    description = (
        "Search Tolemate for service providers (e.g. electrician, plumber) by "
        "service type and optionally location."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "e.g. electrician, plumber"},
            "location": {"type": "string", "description": "e.g. Lalitpur"},
        },
        "required": ["service"],
    }
    permission_level = PermissionLevel.READ
    timeout_seconds = 10.0

    async def execute(
        self, context: ToolContext, service: str, location: str | None = None, **kwargs: Any
    ) -> ToolOutput:
        results = tolemate_connector.search_providers(service, location)
        if not results:
            return ToolOutput(
                content=f"No {service} providers found" + (f" in {location}." if location else "."),
                data={"providers": []},
            )
        summary = "; ".join(
            f"{p['name']} ({p['location']}, rating {p['rating']}, id={p['id']})" for p in results
        )
        return ToolOutput(content=summary, data={"providers": results})


class CheckProviderAvailabilityTool(Tool):
    name = "check_provider_availability"
    description = "Check whether a specific Tolemate provider is available on a given date."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "provider_id": {"type": "string"},
            "date": {"type": "string", "description": "YYYY-MM-DD"},
        },
        "required": ["provider_id", "date"],
    }
    permission_level = PermissionLevel.READ
    timeout_seconds = 10.0

    async def execute(
        self, context: ToolContext, provider_id: str, date: str, **kwargs: Any
    ) -> ToolOutput:
        try:
            available = tolemate_connector.check_availability(provider_id, date)
        except ProviderNotFoundError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return ToolOutput(
            content=f"Provider {provider_id} is {'available' if available else 'NOT available'} on {date}.",
            data={"provider_id": provider_id, "date": date, "available": available},
        )


class CreateServiceBookingTool(Tool):
    name = "create_service_booking"
    description = (
        "Create a new Tolemate service booking with a provider, once availability "
        "has been confirmed."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "provider_id": {"type": "string"},
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "customer_name": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["provider_id", "date", "customer_name"],
    }
    permission_level = PermissionLevel.SAFE_WRITE
    timeout_seconds = 10.0

    async def execute(
        self,
        context: ToolContext,
        provider_id: str,
        date: str,
        customer_name: str,
        notes: str = "",
        **kwargs: Any,
    ) -> ToolOutput:
        try:
            booking = tolemate_connector.create_booking(provider_id, date, customer_name, notes)
        except (ProviderNotFoundError, ProviderUnavailableError) as exc:
            raise ToolExecutionError(str(exc)) from exc
        return ToolOutput(
            content=(
                f"Booking confirmed: {booking['booking_id']} with "
                f"{booking['provider_name']} on {booking['date']}."
            ),
            data=booking,
        )
