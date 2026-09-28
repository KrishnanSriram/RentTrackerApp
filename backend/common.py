"""Shared helpers for every Rent Tracker service: DynamoDB, validation, JWT auth, service calls.
Records are plain dicts with camelCase keys, stored in DynamoDB exactly as the API returns them."""
import json
import math
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
import httpx
import jwt
from boto3.dynamodb.conditions import Key
from botocore.exceptions import EndpointConnectionError
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me-dev-only-change-me")
DYNAMODB_ENDPOINT = os.getenv("DYNAMODB_ENDPOINT")  # set locally (DynamoDB Local); leave unset on AWS
EMAIL = r"[^@\s]+@[^@\s]+\.[^@\s]+"
MONTH = r"\d{4}-(0[1-9]|1[0-2])"


def create_app(name: str) -> FastAPI:
    """Every service lives under /api/<name>, so a gateway or ALB can route by path."""
    app = FastAPI(title=f"Rent Tracker: {name}", docs_url=f"/api/{name}/docs", openapi_url=f"/api/{name}/openapi.json")
    origins = [o for o in os.getenv("CORS_ORIGINS", "").split(",") if o]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
    app.get(f"/api/{name}/health")(lambda: {"status": "ok", "service": name})
    return app


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- DynamoDB ----------

def table(name: str, pk: str, sk: str | None = None):
    """Returns a DynamoDB table. Locally the table is created on first run;
    on AWS, create tables with the same keys ahead of time (console, CLI or IaC)."""
    db = boto3.resource("dynamodb", endpoint_url=DYNAMODB_ENDPOINT, region_name=os.getenv("AWS_REGION", "us-east-1"))
    if DYNAMODB_ENDPOINT:
        keys = [(pk, "HASH")] + ([(sk, "RANGE")] if sk else [])
        for _ in range(30):  # DynamoDB Local may still be starting
            try:
                db.create_table(
                    TableName=name,
                    BillingMode="PAY_PER_REQUEST",
                    KeySchema=[{"AttributeName": k, "KeyType": kind} for k, kind in keys],
                    AttributeDefinitions=[{"AttributeName": k, "AttributeType": "S"} for k, _ in keys],
                )
                break
            except db.meta.client.exceptions.ResourceInUseException:
                break  # already exists
            except EndpointConnectionError:
                time.sleep(1)
    return db.Table(name)


def to_item(d: dict) -> dict:
    """DynamoDB needs Decimal instead of float."""
    return json.loads(json.dumps(d, default=float), parse_float=Decimal)


def get_owned(t, owner_id: str, item_id: str, label: str) -> dict:
    """Items are keyed by (ownerId, id), so another user's item simply isn't found."""
    item = t.get_item(Key={"ownerId": owner_id, "id": item_id}).get("Item")
    if not item:
        raise HTTPException(404, f"{label} not found")
    return item


def list_owned(t, owner_id: str, **match) -> list[dict]:
    """All of a user's items, optionally only those whose fields equal the given values (None = any)."""
    items, args = [], {"KeyConditionExpression": Key("ownerId").eq(owner_id)}
    while True:
        page = t.query(**args)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            break
        args["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return [i for i in items if all(v is None or i.get(k) == v for k, v in match.items())]


def delete_owned(t, owner_id: str, **match) -> None:
    with t.batch_writer() as batch:
        for item in list_owned(t, owner_id, **match):
            batch.delete_item(Key={"ownerId": owner_id, "id": item["id"]})


# ---------- Validation (raises 422 with a readable message) ----------

def fail(message: str):
    raise HTTPException(422, message)


def text(body: dict, key: str, required=False, max_len=200, pattern: str | None = None) -> str:
    value = str(body.get(key) or "").strip()
    if required and not value:
        fail(f"{key} is required")
    if len(value) > max_len:
        fail(f"{key} must be at most {max_len} characters")
    if value and pattern and not re.fullmatch(pattern, value):
        fail(f"{key} is not valid")
    return value


def number(body: dict, key: str, positive=False) -> float:
    try:
        value = round(float(body.get(key)), 2)
    except (TypeError, ValueError):
        fail(f"{key} must be a number")
    if not math.isfinite(value) or value < 0 or value > 10_000_000 or (positive and value == 0):
        fail(f"{key} must be {'greater than 0' if positive else '0 or more'}")
    return value


# ---------- Auth ----------

def make_token(user: dict) -> dict:
    expires = datetime.now(timezone.utc) + timedelta(minutes=int(os.getenv("JWT_TTL_MINUTES", "720")))
    claims = {"sub": user["id"], "email": user["email"], "name": user["name"], "exp": expires}
    return {
        "token": jwt.encode(claims, JWT_SECRET, algorithm="HS256"),
        "expiresAt": expires.isoformat(),
        "user": {"id": user["id"], "email": user["email"], "name": user["name"]},
    }


def current_user(authorization: str = Header(default="")) -> dict:
    """FastAPI dependency: the signed-in user from the Bearer token, or a 401."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Not signed in")
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired, please sign in again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    return {"id": claims["sub"], "email": claims["email"], "name": claims["name"], "token": token}


# ---------- Calling other services (the user's token is passed along) ----------

async def call(method: str, service: str, path: str, user: dict, params: dict | None = None):
    """Returns the JSON response, or None for a 404."""
    base = os.getenv(f"{service.upper()}_URL", f"http://{service}:8000")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.request(method, base + path, params=params, headers={"Authorization": f"Bearer {user['token']}"})
    except httpx.HTTPError:
        raise HTTPException(503, f"The {service} service is unavailable")
    if r.status_code == 404:
        return None
    if r.status_code >= 400:
        raise HTTPException(502, f"The {service} service returned an error ({r.status_code})")
    return r.json() if r.content else None


async def require_property(user: dict, property_id: str) -> dict:
    prop = await call("GET", "properties", f"/api/properties/{property_id}", user)
    if prop is None:
        raise HTTPException(404, "Property not found")
    return prop
