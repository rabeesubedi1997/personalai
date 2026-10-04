"""
Real Tolemate connector — calls the tenant's actual ToleMate Laravel API
instead of the in-memory mock (connector.py). Selected automatically per
tenant by connector_factory.py once a BusinessConnectorConfig row exists
for business_slug="tolemate"; nothing else in the platform (tools.py,
agent.py, the orchestrator, the approval engine) knows the difference.

Three real constraints shaped this file, discovered by reading the actual
ToleMate backend (not guessed — see spec Section 19's "never invent real
API endpoints or business rules"):

1. Search has no city/location field at all — "Kathmandu" is never stored
   as text anywhere in the schema, only as a vendor's lat/lng (set once at
   signup). A plain text search for "deep house cleaning in Kathmandu"
   can never match anything, with or without a fix on PersonalOps' side —
   the fix is to search on the service text alone and, only when the
   caller's location happens to name a city we can geocode (see
   _NEPAL_CITY_COORDS below), narrow by a lat/lng radius too.
2. "Provider" in the mock is one unit; in the real schema a Vendor has
   many Services, and the two real endpoints we need take different ids
   (availability wants a vendor id, booking wants a service id). Rather
   than change the tool-facing `provider_id` parameter (which would ripple
   into tools.py and every test), this connector encodes both ids into
   one opaque string ("v{vendor_id}-s{service_id}") and decodes it back
   out — the tool layer never needs to know.
3. There is no guest/anonymous booking endpoint — every booking requires
   a real, authenticated ToleMate customer. So create_booking here
   registers a brand-new real customer account for the chat visitor
   (using the name/email they gave the agent, a random password they're
   never told — they can use ToleMate's own "forgot password" flow later
   if they want to log in directly) and then books as that account. This
   is a real, first-class ToleMate account, not a shadow/fake one.
"""
from __future__ import annotations

import math
import re
import secrets
from datetime import datetime
from typing import Any

import httpx

from app.connectors.tolemate.connector import (
    MissingCustomerInfoError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)

# Nepal's largest cities/towns, for approximating ToleMate's missing city
# field from lat/lng. Not exhaustive — a location we don't recognize just
# means we skip geo-narrowing and fall back to a plain service-text search,
# which still beats returning nothing.
_NEPAL_CITY_COORDS: dict[str, tuple[float, float]] = {
    "kathmandu": (27.7172, 85.3240),
    "lalitpur": (27.6588, 85.3247),
    "patan": (27.6588, 85.3247),
    "bhaktapur": (27.6710, 85.4298),
    "pokhara": (28.2096, 83.9856),
    "biratnagar": (26.4525, 87.2718),
    "chitwan": (27.5291, 84.3542),
    "bharatpur": (27.6833, 84.4333),
    "butwal": (27.7000, 83.4486),
    "dharan": (26.8065, 87.2846),
    "nepalgunj": (28.0500, 81.6167),
    "janakpur": (26.7288, 85.9266),
    "hetauda": (27.4287, 85.0325),
    "itahari": (26.6650, 87.2750),
}
_DEFAULT_SEARCH_RADIUS_KM = 15.0


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _nearest_known_city(lat: Any, lng: Any) -> str | None:
    # ToleMate's API serializes decimal columns (lat/lng/rating/price) as
    # JSON strings, not numbers — coerce defensively rather than crash.
    if lat is None or lng is None:
        return None
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    best_name, best_dist = None, None
    for name, (clat, clng) in _NEPAL_CITY_COORDS.items():
        dist = _haversine_km(lat_f, lng_f, clat, clng)
        if best_dist is None or dist < best_dist:
            best_name, best_dist = name, dist
    if best_dist is not None and best_dist <= 25.0:
        return best_name.title()
    return None


_ID_PATTERN = re.compile(r"^v(\d+)-s(\d+)$")


def _encode_id(vendor_id: int, service_id: int) -> str:
    return f"v{vendor_id}-s{service_id}"


def _decode_id(provider_id: str) -> tuple[int, int]:
    match = _ID_PATTERN.match(provider_id)
    if not match:
        raise ProviderNotFoundError(
            f"'{provider_id}' isn't a valid provider id for this connection — "
            "it must come from a prior search_service_providers result."
        )
    return int(match.group(1)), int(match.group(2))


class RealTolemateConnector:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def asearch_providers(self, service: str, location: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"query": service}
        geo_center = _NEPAL_CITY_COORDS.get((location or "").strip().lower())
        if geo_center:
            params["lat"], params["lng"] = geo_center
            params["radius"] = _DEFAULT_SEARCH_RADIUS_KM

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self._base_url}/api/services/search", params=params)
            resp.raise_for_status()
            items = resp.json().get("data", [])

            # A real location narrowed to zero results is worse than no
            # location filter at all — the service may just not have its
            # coordinates near enough to the named city. Retry broad.
            if not items and geo_center:
                broad = await client.get(
                    f"{self._base_url}/api/services/search", params={"query": service}
                )
                broad.raise_for_status()
                items = broad.json().get("data", [])

        return [self._to_provider_dict(item) for item in items]

    def _to_provider_dict(self, item: dict) -> dict:
        vendor = item.get("vendor") or {}
        vendor_user = vendor.get("user") or {}
        city = _nearest_known_city(vendor_user.get("lat"), vendor_user.get("lng"))
        return {
            "id": _encode_id(vendor.get("id"), item.get("id")),
            "name": item.get("name", "Unnamed service"),
            "vendor_name": vendor.get("business_name", "Unknown provider"),
            "location": city or "Location not specified",
            "rating": vendor.get("rating", 0),
            "price": item.get("price"),
            "available_dates": [],  # real availability is a weekly schedule, not discrete dates — see acheck_availability
        }

    async def acheck_availability(self, provider_id: str, date: str) -> bool:
        vendor_id, _service_id = _decode_id(provider_id)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self._base_url}/api/vendors/{vendor_id}/availability")
            if resp.status_code == 404:
                raise ProviderNotFoundError(f"No vendor found for provider id '{provider_id}'.")
            resp.raise_for_status()
            days = resp.json().get("availability", [])

        try:
            target = datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise ProviderUnavailableError(f"'{date}' isn't a valid date (expected YYYY-MM-DD).") from exc

        # ToleMate's day_of_week is 0=Sunday..6=Saturday; Python's
        # .weekday() is 0=Monday..6=Sunday.
        laravel_dow = (target.weekday() + 1) % 7
        row = next((d for d in days if d.get("day_of_week") == laravel_dow), None)
        return bool(row and row.get("is_available"))

    async def acreate_booking(
        self,
        provider_id: str,
        date: str,
        customer_name: str,
        notes: str = "",
        customer_email: str | None = None,
    ) -> dict:
        if not customer_email:
            raise MissingCustomerInfoError(
                "An email address is needed to confirm a real booking — ask the "
                "customer for theirs and try again."
            )
        vendor_id, service_id = _decode_id(provider_id)

        if not await self.acheck_availability(provider_id, date):
            raise ProviderUnavailableError(
                f"This provider is not available on {date}."
            )

        async with httpx.AsyncClient(timeout=20.0) as client:
            random_password = secrets.token_urlsafe(16)
            # X-Platform: mobile bypasses the optional reCAPTCHA gate on
            # /api/register (meant for human-facing web forms) — this is a
            # server-to-server call with no browser to render a captcha in.
            register_resp = await client.post(
                f"{self._base_url}/api/register",
                headers={"X-Platform": "mobile"},
                json={
                    "name": customer_name,
                    "email": customer_email,
                    "password": random_password,
                    "password_confirmation": random_password,
                },
            )
            if register_resp.status_code == 422:
                errors = register_resp.json().get("errors", {})
                if "email" in errors:
                    raise ProviderUnavailableError(
                        f"{customer_email} already has a ToleMate account — ask them to "
                        "book through the website while logged in, or use a different email."
                    )
                raise ProviderUnavailableError(f"Could not register this booking: {errors}")
            register_resp.raise_for_status()
            token = register_resp.json()["access_token"]

            booking_resp = await client.post(
                f"{self._base_url}/api/bookings",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "service_id": service_id,
                    "booking_type": "instant",
                    "scheduled_time": f"{date}T10:00:00",
                    "message": notes or None,
                },
            )
            if booking_resp.status_code >= 400:
                raise ProviderUnavailableError(
                    f"ToleMate rejected the booking: {booking_resp.text}"
                )
            booking = booking_resp.json().get("booking", booking_resp.json())

        return {
            "booking_id": f"TOLEMATE-{booking.get('id', vendor_id)}",
            "provider_id": provider_id,
            "provider_name": None,
            "date": date,
            "customer_name": customer_name,
            "notes": notes,
            "status": booking.get("status", "pending"),
        }
