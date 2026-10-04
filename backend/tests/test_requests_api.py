import pytest

pytestmark = pytest.mark.asyncio


async def _auth_headers(client, email: str) -> dict:
    await client.post("/api/v1/auth/bootstrap", json={"email": email, "password": "pw123456"})
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw123456"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_and_get_request(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    create_res = await client.post(
        "/api/v1/requests",
        json={
            "request_type": "service_booking",
            "customer": {"name": "John", "location": "Lalitpur"},
            "requirements": {"service": "electrician"},
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    body = create_res.json()
    assert body["status"] == "received"
    assert body["request_type"] == "service_booking"

    get_res = await client.get(f"/api/v1/requests/{body['id']}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == body["id"]


async def test_list_requests_filters_by_type_and_status(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    await client.post(
        "/api/v1/requests", json={"request_type": "property_search"}, headers=headers
    )
    await client.post(
        "/api/v1/requests", json={"request_type": "service_booking"}, headers=headers
    )

    all_res = await client.get("/api/v1/requests", headers=headers)
    assert len(all_res.json()) == 2

    filtered = await client.get(
        "/api/v1/requests", params={"request_type": "service_booking"}, headers=headers
    )
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["request_type"] == "service_booking"

    by_status = await client.get(
        "/api/v1/requests", params={"status": "received"}, headers=headers
    )
    assert len(by_status.json()) == 2


async def test_valid_status_transition(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    create_res = await client.post(
        "/api/v1/requests", json={"request_type": "service_booking"}, headers=headers
    )
    req_id = create_res.json()["id"]

    update_res = await client.patch(
        f"/api/v1/requests/{req_id}/status",
        json={"status": "understanding", "note": "classifying request"},
        headers=headers,
    )
    assert update_res.status_code == 200
    body = update_res.json()
    assert body["status"] == "understanding"
    assert body["status_history"][-1]["note"] == "classifying request"


async def test_invalid_status_transition_rejected(client, unique_email):
    headers = await _auth_headers(client, unique_email)
    create_res = await client.post(
        "/api/v1/requests", json={"request_type": "service_booking"}, headers=headers
    )
    req_id = create_res.json()["id"]

    # RECEIVED -> COMPLETED is not a legal jump.
    update_res = await client.patch(
        f"/api/v1/requests/{req_id}/status", json={"status": "completed"}, headers=headers
    )
    assert update_res.status_code == 409


async def test_tenant_cannot_access_another_tenants_request(client, unique_email):
    # unique_email and unique_email+"2" each get their own tenant via bootstrap.
    tenant_a_headers = await _auth_headers(client, unique_email)
    tenant_b_headers = await _auth_headers(client, f"b-{unique_email}")

    create_res = await client.post(
        "/api/v1/requests", json={"request_type": "service_booking"}, headers=tenant_a_headers
    )
    req_id = create_res.json()["id"]

    # Tenant B must not be able to read tenant A's request.
    get_res = await client.get(f"/api/v1/requests/{req_id}", headers=tenant_b_headers)
    assert get_res.status_code == 404

    # Nor list it.
    list_res = await client.get("/api/v1/requests", headers=tenant_b_headers)
    assert all(r["id"] != req_id for r in list_res.json())

    # Nor modify it.
    patch_res = await client.patch(
        f"/api/v1/requests/{req_id}/status",
        json={"status": "understanding"},
        headers=tenant_b_headers,
    )
    assert patch_res.status_code == 404


async def test_requests_require_auth(client):
    assert (await client.get("/api/v1/requests")).status_code == 401
    assert (await client.post("/api/v1/requests", json={"request_type": "x"})).status_code == 401
