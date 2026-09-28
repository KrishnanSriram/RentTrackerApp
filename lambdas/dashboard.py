import json
import os
import re
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ["TABLE_NAME"]  # fail fast if it isn't configured

table = boto3.resource("dynamodb").Table(TABLE_NAME)

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
ZERO = Decimal("0")


# ---------- helpers ----------

# CORS is handled by API Gateway, so the function returns no CORS headers.
def respond(status, body=None):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": "" if body is None else json.dumps(body, default=str),
    }


def get_user_id(event):
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    except (KeyError, TypeError):
        return None


def current_month():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def previous_months(end_month, count):
    """[end_month, the month before, ...], count items, newest first."""
    year, month = (int(x) for x in end_month.split("-"))
    months = []
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return months


def money(value):
    return float(value) if value is not None else None


def query_all(**kwargs):
    items = []
    while True:
        page = table.query(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def list_properties(user):
    return query_all(
        KeyConditionExpression=Key("PK").eq(f"USER#{user}") & Key("SK").begins_with("PROPERTY#")
    )


def child_items(user, prop_id, sk_prefix):
    return query_all(
        KeyConditionExpression=Key("PK").eq(f"USER#{user}#PROPERTY#{prop_id}")
        & Key("SK").begins_with(sk_prefix)
    )


def status_for(rent, collected):
    if rent is None:
        return "no-rent-set"
    if collected <= ZERO:
        return "unpaid" if rent > ZERO else "paid"
    return "paid" if collected >= rent else "partial"


def month_summary(rent, collected):
    return {
        "expected": money(rent),
        "collected": money(collected),
        "outstanding": money(max(rent - collected, ZERO)) if rent is not None else None,
        "status": status_for(rent, collected),
    }


def primary_contact(renters):
    if not renters:
        return None
    renters = sorted(
        renters, key=lambda r: (r.get("contactType") != "primary", r.get("name", "").lower())
    )
    r = renters[0]
    return {"name": r.get("name", ""), "email": r.get("email", ""), "phone": r.get("phone", "")}


# ---------- route handlers ----------

def month_overview(user, event):
    month = ((event.get("queryStringParameters") or {}).get("month") or "").strip() or current_month()
    if not MONTH_RE.match(month):
        return respond(400, {"message": "month must be in the form YYYY-MM"})

    rows = []
    totals = {"expected": ZERO, "collected": ZERO, "outstanding": ZERO}
    counts = {"paid": 0, "partial": 0, "unpaid": 0, "no-rent-set": 0}

    for prop in list_properties(user):
        prop_id = prop["id"]
        rent = prop.get("monthlyRent")
        payments = child_items(user, prop_id, f"PAYMENT#{month}#")
        renters = child_items(user, prop_id, "RENTER#")
        collected = sum((p["amount"] for p in payments), ZERO)

        summary = month_summary(rent, collected)
        counts[summary["status"]] += 1
        totals["collected"] += collected
        if rent is not None:
            totals["expected"] += rent
            totals["outstanding"] += max(rent - collected, ZERO)

        rows.append({
            "propertyId": prop_id,
            "address": prop["address"],
            "monthlyRent": money(rent),
            **summary,
            "paymentCount": len(payments),
            "lastPaidOn": max((p["paidOn"] for p in payments), default=None),
            "primaryContact": primary_contact(renters),
        })

    # Most urgent first: unpaid, partial, no rent set, paid; then by address.
    order = {"unpaid": 0, "partial": 1, "no-rent-set": 2, "paid": 3}
    rows.sort(key=lambda r: (order[r["status"]], r["address"].lower()))

    return respond(200, {
        "month": month,
        "totals": {k: money(v) for k, v in totals.items()},
        "counts": {**counts, "properties": len(rows)},
        "properties": rows,
    })


def property_history(user, prop_id, event):
    prop = table.get_item(Key={"PK": f"USER#{user}", "SK": f"PROPERTY#{prop_id}"}).get("Item")
    if not prop:
        return respond(404, {"message": "Property not found"})

    raw = ((event.get("queryStringParameters") or {}).get("months") or "12").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 36:
        return respond(400, {"message": "months must be a whole number from 1 to 36"})
    months = previous_months(current_month(), int(raw))

    # One query for all of the property's payments, grouped by month in code.
    by_month = {}
    for p in child_items(user, prop_id, "PAYMENT#"):
        by_month.setdefault(p["month"], []).append(p)

    rent = prop.get("monthlyRent")
    history = []
    for m in months:
        payments = by_month.get(m, [])
        collected = sum((p["amount"] for p in payments), ZERO)
        history.append({"month": m, **month_summary(rent, collected), "paymentCount": len(payments)})

    return respond(200, {
        "propertyId": prop_id,
        "address": prop["address"],
        "monthlyRent": money(rent),
        "months": history,
    })


# ---------- entry point ----------

def lambda_handler(event, context):
    user = get_user_id(event)
    if not user:
        return respond(401, {"message": "Unauthorized"})

    route = event.get("routeKey", "")
    prop_id = (event.get("pathParameters") or {}).get("id")

    try:
        if route == "GET /api/dashboard":
            return month_overview(user, event)
        if route == "GET /api/dashboard/properties/{id}":
            return property_history(user, prop_id, event)
        return respond(404, {"message": f"No route for {route}"})
    except Exception as e:  # log the detail, return a generic error
        print(f"ERROR handling {route}: {e!r}")
        return respond(500, {"message": "Internal server error"})