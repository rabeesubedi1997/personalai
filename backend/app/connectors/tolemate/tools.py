"""Tolemate tools — thin wrappers around TolemateConnector. Each declares
its own permission level per spec Section 11: searching/checking is READ,
creating a new booking is SAFE_WRITE (a new commitment, not a change to an
existing one). Cancelling an existing booking uses the platform's generic
`cancel_booking` tool (SENSITIVE, approval-gated) rather than a
Tolemate-specific duplicate — see app/tools/mock_tools.py."""
from __future__ import annotations

from typing import Any

from app.connectors.tolemate.connector import (
    MissingCustomerInfoError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)
from app.connectors.tolemate.connector_factory import get_connector
from app.tools.base import PermissionLevel, Tool, ToolContext, ToolExecutionError, ToolOutput


def _describe_provider(p: dict[str, Any]) -> str:
    # Mock providers have a flat `name`; real ones additionally have a
    # separate `vendor_name` and `price` — include whatever's present
    # rather than assuming either connector's exact shape.
    label = p["name"]
    if p.get("vendor_name"):
        label = f"{label} by {p['vendor_name']}"
    price_part = f", {p['price']}" if p.get("price") is not None else ""
    return f"{label} ({p['location']}, rating {p['rating']}{price_part}, id={p['id']})"


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
        connector = await get_connector(context.db, context.tenant_id)
        results = await connector.asearch_providers(service, location)
        if not results:
            return ToolOutput(
                content=f"No {service} providers found" + (f" in {location}." if location else "."),
                data={"providers": []},
            )
        summary = "; ".join(_describe_provider(p) for p in results)
        return ToolOutput(content=summary, data={"providers": results})


class GetProviderScheduleTool(Tool):
    name = "get_provider_schedule"
    description = (
        "Get a Tolemate provider's regular open days/hours (or, for a provider "
        "with no regular schedule, their specific available dates) — call this "
        "right after finding a provider so you can offer the customer real "
        "options to choose from, instead of asking them to guess a date to check."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"provider_id": {"type": "string"}},
        "required": ["provider_id"],
    }
    permission_level = PermissionLevel.READ
    timeout_seconds = 10.0

    async def execute(self, context: ToolContext, provider_id: str, **kwargs: Any) -> ToolOutput:
        connector = await get_connector(context.db, context.tenant_id)
        try:
            schedule = await connector.aget_schedule(provider_id)
        except ProviderNotFoundError as exc:
            raise ToolExecutionError(str(exc)) from exc

        if schedule.get("open_days"):
            content = "Regularly open: " + ", ".join(schedule["open_days"]) + "."
        elif schedule.get("available_dates"):
            content = "Available on: " + ", ".join(schedule["available_dates"]) + "."
        else:
            content = "No regular availability found for this provider."
        return ToolOutput(content=content, data=schedule)


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
        connector = await get_connector(context.db, context.tenant_id)
        try:
            available = await connector.acheck_availability(provider_id, date)
        except (ProviderNotFoundError, ProviderUnavailableError) as exc:
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
            "customer_email": {
                "type": "string",
                "description": (
                    "The customer's email. Not every connection needs this, but ask for "
                    "it if a booking attempt says it's required."
                ),
            },
            "notes": {"type": "string"},
        },
        "required": ["provider_id", "date", "customer_name"],
    }
    permission_level = PermissionLevel.SAFE_WRITE
    timeout_seconds = 20.0

    async def execute(
        self,
        context: ToolContext,
        provider_id: str,
        date: str,
        customer_name: str,
        customer_email: str | None = None,
        notes: str = "",
        **kwargs: Any,
    ) -> ToolOutput:
        connector = await get_connector(context.db, context.tenant_id)
        try:
            booking = await connector.acreate_booking(
                provider_id, date, customer_name, notes, customer_email
            )
        except (ProviderNotFoundError, ProviderUnavailableError, MissingCustomerInfoError) as exc:
            raise ToolExecutionError(str(exc)) from exc
        provider_part = f" with {booking['provider_name']}" if booking.get("provider_name") else ""
        return ToolOutput(
            content=f"Booking confirmed: {booking['booking_id']}{provider_part} on {booking['date']}.",
            data=booking,
        )
