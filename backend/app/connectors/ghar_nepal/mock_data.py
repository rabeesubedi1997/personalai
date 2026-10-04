"""
Mock Ghar Nepal property data. No real Ghar Nepal API access has been
confirmed, so — same rule as Tolemate — this is clearly-labeled fictional
data in the shape a real integration would return, not a guess at Ghar
Nepal's actual listings or business rules.
"""

MOCK_PROPERTIES = [
    {
        "id": "GN-001",
        "title": "2BHK Apartment in Jhamsikhel",
        "property_type": "apartment",
        "location": "Lalitpur",
        "price_npr": 14_500_000,
        "bedrooms": 2,
        "bathrooms": 2,
        "status": "available",
    },
    {
        "id": "GN-002",
        "title": "3BHK House in Budhanilkantha",
        "property_type": "house",
        "location": "Kathmandu",
        "price_npr": 28_000_000,
        "bedrooms": 3,
        "bathrooms": 3,
        "status": "available",
    },
    {
        "id": "GN-003",
        "title": "Studio Apartment in Patan",
        "property_type": "apartment",
        "location": "Lalitpur",
        "price_npr": 8_200_000,
        "bedrooms": 1,
        "bathrooms": 1,
        "status": "sold",
    },
]
