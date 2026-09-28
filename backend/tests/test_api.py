"""End-to-end API tests. They call the gateway, so start the stack first (from the project folder):

    docker compose up --build -d
    pip install pytest httpx
    pytest backend/tests -v            # or: API_URL=http://other-host:8080 pytest ...
"""
import os
import uuid
from datetime import date

import httpx
import pytest

API = os.getenv("API_URL", "http://localhost:8080")
MONTH = date.today().strftime("%Y-%m")


@pytest.fixture(scope="module")
def http():
    with httpx.Client(base_url=API, timeout=10) as c:
        yield c


def new_user(http, name="Test User"):
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    r = http.post("/api/auth/register", json={"name": name, "email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    body = r.json()
    return email, {"Authorization": f"Bearer {body['token']}"}


PROPERTY = {"name": "Maple", "street": "123 Maple St", "unit": "A", "city": "Dublin", "state": "oh", "zip": "43017", "monthlyRent": 1800}


# ---------- health ----------

@pytest.mark.parametrize("svc", ["auth", "properties", "renters", "payments", "dashboard"])
def test_health(http, svc):
    r = http.get(f"/api/{svc}/health")
    assert r.status_code == 200 and r.json()["service"] == svc


# ---------- auth ----------

def test_register_login_me(http):
    email, headers = new_user(http, "Krishnan")
    assert http.post("/api/auth/register", json={"name": "x", "email": email, "password": "password123"}).status_code == 409
    assert http.post("/api/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401
    assert http.post("/api/auth/login", json={"email": "nobody@example.com", "password": "password123"}).status_code == 401
    r = http.post("/api/auth/login", json={"email": email.upper(), "password": "password123"})
    assert r.status_code == 200 and r.json()["user"]["name"] == "Krishnan"
    me = http.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert me.json()["email"] == email


def test_short_password_rejected(http):
    r = http.post("/api/auth/register", json={"name": "x", "email": "a@example.com", "password": "short"})
    assert r.status_code == 422


@pytest.mark.parametrize("path", ["/api/properties", "/api/renters", "/api/payments", "/api/dashboard", "/api/auth/me"])
def test_requires_token(http, path):
    assert http.get(path).status_code == 401
    assert http.get(path, headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


# ---------- properties ----------

def test_property_crud_and_validation(http):
    _, h = new_user(http)
    r = http.post("/api/properties", json=PROPERTY, headers=h)
    assert r.status_code == 201
    prop = r.json()
    assert prop["state"] == "OH" and prop["monthlyRent"] == 1800

    assert http.post("/api/properties", json={**PROPERTY, "zip": "abc"}, headers=h).status_code == 422
    assert http.post("/api/properties", json={**PROPERTY, "monthlyRent": -5}, headers=h).status_code == 422

    r = http.put(f"/api/properties/{prop['id']}", json={**PROPERTY, "monthlyRent": 1900.555}, headers=h)
    assert r.json()["monthlyRent"] == 1900.56
    assert [p["id"] for p in http.get("/api/properties", headers=h).json()] == [prop["id"]]


def test_users_cannot_see_each_others_data(http):
    _, alice = new_user(http, "Alice")
    _, bob = new_user(http, "Bob")
    prop = http.post("/api/properties", json=PROPERTY, headers=alice).json()

    assert http.get("/api/properties", headers=bob).json() == []
    assert http.get(f"/api/properties/{prop['id']}", headers=bob).status_code == 404
    assert http.put(f"/api/properties/{prop['id']}", json=PROPERTY, headers=bob).status_code == 404
    assert http.delete(f"/api/properties/{prop['id']}", headers=bob).status_code == 404
    # Bob can't attach renters or payments to Alice's property either
    r = http.post("/api/renters", json={"propertyId": prop["id"], "name": "Mallory"}, headers=bob)
    assert r.status_code == 404
    r = http.post("/api/payments", json={"propertyId": prop["id"], "month": MONTH, "amount": 1, "date": str(date.today())}, headers=bob)
    assert r.status_code == 404


# ---------- renters ----------

def test_renters(http):
    _, h = new_user(http)
    prop = http.post("/api/properties", json=PROPERTY, headers=h).json()
    jane = http.post("/api/renters", json={"propertyId": prop["id"], "name": "Jane", "email": "jane@example.com", "phone": "(614) 555-0101"}, headers=h)
    assert jane.status_code == 201
    john = http.post("/api/renters", json={"propertyId": prop["id"], "name": "John", "role": "secondary"}, headers=h).json()
    assert http.post("/api/renters", json={"propertyId": prop["id"], "name": "X", "email": "not-an-email"}, headers=h).status_code == 422
    assert http.post("/api/renters", json={"propertyId": prop["id"], "name": "X", "role": "boss"}, headers=h).status_code == 422

    r = http.put(f"/api/renters/{john['id']}", json={**john, "phone": "614-555-9999"}, headers=h)
    assert r.json()["phone"] == "614-555-9999"
    names = [x["name"] for x in http.get("/api/renters", params={"propertyId": prop["id"]}, headers=h).json()]
    assert names == ["Jane", "John"]  # primary first
    assert http.delete(f"/api/renters/{john['id']}", headers=h).status_code == 204
    assert len(http.get("/api/renters", headers=h).json()) == 1


# ---------- payments + dashboard ----------

def test_partial_payments_and_dashboard(http):
    _, h = new_user(http)
    maple = http.post("/api/properties", json=PROPERTY, headers=h).json()
    oak = http.post("/api/properties", json={**PROPERTY, "name": "Oak", "monthlyRent": 1500}, headers=h).json()
    http.post("/api/renters", json={"propertyId": maple["id"], "name": "Jane"}, headers=h)

    pay = {"propertyId": maple["id"], "month": MONTH, "date": str(date.today()), "method": "Check"}
    assert http.post("/api/payments", json={**pay, "amount": 0}, headers=h).status_code == 422
    assert http.post("/api/payments", json={**pay, "month": "2026-13", "amount": 5}, headers=h).status_code == 422

    first = http.post("/api/payments", json={**pay, "amount": 1000, "note": "check #1042"}, headers=h).json()
    d = http.get("/api/dashboard", params={"month": MONTH}, headers=h).json()
    rows = {r["property"]["id"]: r for r in d["properties"]}
    assert rows[maple["id"]]["status"] == "partial" and rows[maple["id"]]["balance"] == 800
    assert rows[maple["id"]]["primaryRenter"]["name"] == "Jane"
    assert rows[oak["id"]]["status"] == "vacant"
    assert d["totals"] == {"properties": 2, "occupied": 1, "paidInFull": 0, "due": 1800, "paid": 1000, "outstanding": 800}

    http.post("/api/payments", json={**pay, "amount": 800}, headers=h)
    d = http.get("/api/dashboard", params={"month": MONTH}, headers=h).json()
    assert d["totals"]["paidInFull"] == 1 and d["totals"]["outstanding"] == 0

    # editing a payment changes the status back
    http.put(f"/api/payments/{first['id']}", json={**first, "amount": 900}, headers=h)
    hist = http.get(f"/api/dashboard/properties/{maple['id']}/history", params={"months": 3}, headers=h).json()
    assert [m["status"] for m in hist["months"]] == ["partial", "unpaid", "unpaid"]
    assert hist["months"][0] == {"month": MONTH, "due": 1800, "paid": 1700, "balance": 100, "status": "partial"}

    assert len(http.get("/api/payments", params={"propertyId": maple["id"], "month": MONTH}, headers=h).json()) == 2


def test_delete_property_removes_renters_and_payments(http):
    _, h = new_user(http)
    prop = http.post("/api/properties", json=PROPERTY, headers=h).json()
    http.post("/api/renters", json={"propertyId": prop["id"], "name": "Jane"}, headers=h)
    http.post("/api/payments", json={"propertyId": prop["id"], "month": MONTH, "amount": 5, "date": str(date.today())}, headers=h)

    assert http.delete(f"/api/properties/{prop['id']}", headers=h).status_code == 204
    assert http.get(f"/api/properties/{prop['id']}", headers=h).status_code == 404
    assert http.get("/api/renters", headers=h).json() == []
    assert http.get("/api/payments", headers=h).json() == []
