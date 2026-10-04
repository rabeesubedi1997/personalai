"""
Mock Paradise Nepal hotel data.

IMPORTANT CORRECTION: the original master spec guessed Paradise Nepal was
a film-production business. Checking the real site
(https://paradisenepal.kitetool.com/) before building this showed
otherwise — its client bundle references hotels, rooms, checkin/checkout,
guests, bookings, rates, packages, and amenities (breakfast, pool, wifi).
It's a HOTEL BOOKING platform. No API docs or credentials were available
(a React/Vite SPA with no exposed API routes), so — same rule as
Tolemate/Ghar Nepal — this is clearly-labeled fictional data in a shape
consistent with what the real site's own code suggests, not a guess at
its actual inventory, rates, or business rules.
"""

MOCK_HOTELS = [
    {
        "id": "PARADISE-H001",
        "name": "Paradise Lakeside Resort",
        "location": "Pokhara",
        "rating": 4.7,
        "amenities": ["wifi", "breakfast", "pool", "parking"],
        "rooms": [
            {
                "room_type": "deluxe",
                "max_occupancy": 2,
                "price_per_night_npr": 8500,
                "available_checkin_dates": ["2026-11-01", "2026-11-02", "2026-11-05"],
            },
            {
                "room_type": "suite",
                "max_occupancy": 4,
                "price_per_night_npr": 15000,
                "available_checkin_dates": ["2026-11-03"],
            },
        ],
    },
    {
        "id": "PARADISE-H002",
        "name": "Paradise Heritage Inn",
        "location": "Kathmandu",
        "rating": 4.2,
        "amenities": ["wifi", "breakfast"],
        "rooms": [
            {
                "room_type": "standard",
                "max_occupancy": 2,
                "price_per_night_npr": 4500,
                "available_checkin_dates": ["2026-11-01", "2026-11-04"],
            },
        ],
    },
]
