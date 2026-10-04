"""
Mock Tolemate provider data. No real Tolemate API access has been
confirmed, so per the master spec ("DO NOT invent real API endpoints,
database tables, fields, credentials, or business rules" / "use mock
connectors" until real access exists), this is clearly-labeled fictional
data in the same SHAPE a real integration would return — not a guess at
Tolemate's actual provider catalog or business rules.
"""

MOCK_PROVIDERS = [
    {
        "id": "PRV-001",
        "name": "Bikash Electrical Services",
        "service_type": "electrician",
        "location": "Lalitpur",
        "rating": 4.6,
        "available_dates": ["2026-10-10", "2026-10-11", "2026-10-14"],
    },
    {
        "id": "PRV-002",
        "name": "Kathmandu Power Fix",
        "service_type": "electrician",
        "location": "Kathmandu",
        "rating": 4.2,
        "available_dates": ["2026-10-10", "2026-10-12"],
    },
    {
        "id": "PRV-003",
        "name": "Everest Plumbing Co.",
        "service_type": "plumber",
        "location": "Lalitpur",
        "rating": 4.8,
        "available_dates": ["2026-10-11", "2026-10-13"],
    },
]
