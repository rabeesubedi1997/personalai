"""Ghar Nepal tools — thin wrappers around GharNepalConnector, same
pattern as app/connectors/tolemate/tools.py. Search/lookup is READ,
creating a new enquiry or viewing request is SAFE_WRITE (a new commitment,
not a change to anything existing)."""
from __future__ import annotations

from typing import Any

from app.connectors.ghar_nepal.connector import PropertyNotFoundError, ghar_nepal_connector
from app.tools.base import PermissionLevel, Tool, ToolContext, ToolExecutionError, ToolOutput


class SearchPropertiesTool(Tool):
    name = "search_properties"
    description = (
        "Search Ghar Nepal property listings by type, location, budget, and "
        "minimum bedrooms. All filters are optional."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "property_type": {"type": "string", "description": "e.g. apartment, house"},
            "location": {"type": "string"},
            "max_budget_npr": {"type": "integer"},
            "min_bedrooms": {"type": "integer"},
        },
    }
    permission_level = PermissionLevel.READ
    timeout_seconds = 10.0

    async def execute(
        self,
        context: ToolContext,
        property_type: str | None = None,
        location: str | None = None,
        max_budget_npr: int | None = None,
        min_bedrooms: int | None = None,
        **kwargs: Any,
    ) -> ToolOutput:
        results = ghar_nepal_connector.search_properties(
            property_type, location, max_budget_npr, min_bedrooms
        )
        if not results:
            return ToolOutput(content="No matching properties found.", data={"properties": []})
        summary = "; ".join(
            f"{p['title']} ({p['location']}, NPR {p['price_npr']:,}, {p['bedrooms']}BR, id={p['id']})"
            for p in results
        )
        return ToolOutput(content=summary, data={"properties": results})


class GetPropertyDetailsTool(Tool):
    name = "get_property_details"
    description = "Get full details for one Ghar Nepal property by its id."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"property_id": {"type": "string"}},
        "required": ["property_id"],
    }
    permission_level = PermissionLevel.READ
    timeout_seconds = 10.0

    async def execute(self, context: ToolContext, property_id: str, **kwargs: Any) -> ToolOutput:
        try:
            prop = ghar_nepal_connector.get_property(property_id)
        except PropertyNotFoundError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return ToolOutput(
            content=(
                f"{prop['title']}: {prop['bedrooms']}BR/{prop['bathrooms']}BA "
                f"{prop['property_type']} in {prop['location']}, NPR {prop['price_npr']:,}, "
                f"status={prop['status']}."
            ),
            data=prop,
        )


class CreatePropertyEnquiryTool(Tool):
    name = "create_property_enquiry"
    description = "Submit a buyer enquiry for a specific Ghar Nepal property."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "property_id": {"type": "string"},
            "customer_name": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["property_id", "customer_name"],
    }
    permission_level = PermissionLevel.SAFE_WRITE
    timeout_seconds = 10.0

    async def execute(
        self,
        context: ToolContext,
        property_id: str,
        customer_name: str,
        message: str = "",
        **kwargs: Any,
    ) -> ToolOutput:
        try:
            enquiry = ghar_nepal_connector.create_enquiry(property_id, customer_name, message)
        except PropertyNotFoundError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return ToolOutput(
            content=f"Enquiry {enquiry['enquiry_id']} submitted for {enquiry['property_title']}.",
            data=enquiry,
        )


class CreateViewingRequestTool(Tool):
    name = "create_viewing_request"
    description = "Request a viewing appointment for a specific Ghar Nepal property."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "property_id": {"type": "string"},
            "customer_name": {"type": "string"},
            "preferred_date": {"type": "string", "description": "YYYY-MM-DD"},
        },
        "required": ["property_id", "customer_name", "preferred_date"],
    }
    permission_level = PermissionLevel.SAFE_WRITE
    timeout_seconds = 10.0

    async def execute(
        self,
        context: ToolContext,
        property_id: str,
        customer_name: str,
        preferred_date: str,
        **kwargs: Any,
    ) -> ToolOutput:
        try:
            viewing = ghar_nepal_connector.create_viewing_request(
                property_id, customer_name, preferred_date
            )
        except PropertyNotFoundError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return ToolOutput(
            content=(
                f"Viewing request {viewing['viewing_id']} submitted for "
                f"{viewing['property_title']} on {viewing['preferred_date']}."
            ),
            data=viewing,
        )
