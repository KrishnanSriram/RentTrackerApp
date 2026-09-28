import base64
import json
import os
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import boto3
from boto3.dynamodb.conditions import Attr, Key

TABLE_NAME = os.environ["TABLE_NAME"]  # fail fast if it isn't configured

table = boto3.resource("dynamodb").Table(TABLE_NAME)
# The resource's client converts Python values to DynamoDB types itself,
# so transactions below can pass plain dicts.
client = table.meta.client

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
MAX_AMOUNT = Decimal("1000000")
CENT = Decimal("0.01")


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


def parse_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw, parse_float=Decimal)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def now():
    return datetime.now(timezone.utc).isoformat()


def child_pk(user, prop_id):
    return f"USER#{user}#PROPERTY#{prop_id}"


def payment_sk(month, payment_id):
    return f"PAYMENT#{month}#{payment_id}"


def property_exists(user, prop_id):
    item = table.get_item(
        Key={"PK": f"USER#{user}", "SK": f"PROPERTY#{prop_id}"},
        ProjectionExpression="PK",
    ).get("Item")
    return item is not None


def get_renter_name(user, prop_id, renter_id):
    item = table.get_item(
        Key={"PK": child_pk(user, prop_id), "SK": f"RENTER#{renter_id}"},
        ProjectionExpression="#n",
        ExpressionAttributeNames={"#n": "name"},
    ).get("Item")
    return item["name"] if item else None


def query_all(**kwargs):
    items = []
    while True:
        page = table.query(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def find_payment(user, prop_id, payment_id):
    """The month is part of the sort key, so look the payment up by its id."""
    items = query_all(
        KeyConditionExpression=Key("PK").eq(child_pk(user, prop_id))
        & Key("SK").begins_with("PAYMENT#"),
        FilterExpression=Attr("id").eq(payment_id),
    )
    return items[0] if items else None


def to_payment(item):
    return {
        "id": item["id"],
        "propertyId": item["propertyId"],
        "amount": float(item["amount"]),
        "month": item["month"],
        "paidOn": item["paidOn"],
        "method": item.get("method", ""),
        "renterId": item.get("renterId", ""),
        "renterName": item.get("renterName", ""),
        "note": item.get("note", ""),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }


def validate_payment(data):
    """Returns (clean_fields, error_message)."""
    if data is None:
        return None, "Request body must be a JSON object"

    raw_amount = data.get("amount")
    if raw_amount is None or isinstance(raw_amount, bool):
        return None, "amount is required"
    try:
        amount = Decimal(str(raw_amount).strip())
    except InvalidOperation:
        return None, "amount must be a number"
    if not amount.is_finite() or amount <= 0:
        return None, "amount must be greater than 0"
    if amount > MAX_AMOUNT:
        return None, "amount is too large"
    if amount != amount.quantize(CENT):
        return None, "amount can have at most 2 decimal places"
    amount = amount.quantize(CENT)

    month = str(data.get("month") or "").strip()
    if not MONTH_RE.match(month):
        return None, "month is required, in the form YYYY-MM"

    paid_on = str(data.get("paidOn") or "").strip() or date.today().isoformat()
    try:
        datetime.strptime(paid_on, "%Y-%m-%d")
    except ValueError:
        return None, "paidOn must be a date in the form YYYY-MM-DD"

    method = str(data.get("method") or "").strip()
    if len(method) > 40:
        return None, "method must be 40 characters or fewer"
    note = str(data.get("note") or "").strip()
    if len(note) > 500:
        return None, "note must be 500 characters or fewer"
    renter_id = str(data.get("renterId") or "").strip()

    return {
        "amount": amount,
        "month": month,
        "paidOn": paid_on,
        "method": method,
        "note": note,
        "renterId": renter_id,
    }, None


def build_item(user, prop_id, payment_id, fields, renter_name, created_at):
    item = {
        "PK": child_pk(user, prop_id),
        "SK": payment_sk(fields["month"], payment_id),
        "type": "payment",
        "id": payment_id,
        "propertyId": prop_id,
        "amount": fields["amount"],
        "month": fields["month"],
        "paidOn": fields["paidOn"],
        "createdAt": created_at,
        "updatedAt": now(),
    }
    # DynamoDB doesn't need empty optional attributes; leave them off.
    for key in ("method", "note", "renterId"):
        if fields[key]:
            item[key] = fields[key]
    if renter_name:
        item["renterName"] = renter_name
    return item


def resolve_renter(user, prop_id, fields):
    """Returns (renter_name, error_response)."""
    if not fields["renterId"]:
        return None, None
    name = get_renter_name(user, prop_id, fields["renterId"])
    if name is None:
        return None, respond(400, {"message": "renterId is not a renter of this property"})
    return name, None


# ---------- route handlers ----------

def list_payments(user, prop_id, event):
    if not property_exists(user, prop_id):
        return respond(404, {"message": "Property not found"})

    month = ((event.get("queryStringParameters") or {}).get("month") or "").strip()
    if month and not MONTH_RE.match(month):
        return respond(400, {"message": "month must be in the form YYYY-MM"})
    prefix = f"PAYMENT#{month}#" if month else "PAYMENT#"

    items = query_all(
        KeyConditionExpression=Key("PK").eq(child_pk(user, prop_id))
        & Key("SK").begins_with(prefix)
    )
    payments = [to_payment(i) for i in items]
    # Newest rent month first, then most recent payment date first.
    payments.sort(key=lambda p: (p["month"], p["paidOn"], p["createdAt"] or ""), reverse=True)
    return respond(200, payments)


def create_payment(user, prop_id, event):
    fields, error = validate_payment(parse_body(event))
    if error:
        return respond(400, {"message": error})
    if not property_exists(user, prop_id):
        return respond(404, {"message": "Property not found"})
    renter_name, err = resolve_renter(user, prop_id, fields)
    if err:
        return err

    item = build_item(user, prop_id, str(uuid.uuid4()), fields, renter_name, now())
    table.put_item(Item=item)
    return respond(201, to_payment(item))


def get_payment(user, prop_id, payment_id):
    item = find_payment(user, prop_id, payment_id)
    if not item:
        return respond(404, {"message": "Payment not found"})
    return respond(200, to_payment(item))


def update_payment(user, prop_id, payment_id, event):
    fields, error = validate_payment(parse_body(event))
    if error:
        return respond(400, {"message": error})
    existing = find_payment(user, prop_id, payment_id)
    if not existing:
        return respond(404, {"message": "Payment not found"})
    renter_name, err = resolve_renter(user, prop_id, fields)
    if err:
        return err

    item = build_item(user, prop_id, payment_id, fields, renter_name, existing.get("createdAt"))

    if item["SK"] == existing["SK"]:
        table.put_item(Item=item)  # same month: replace in place
    else:
        # The month is part of the key, so moving a payment to another month
        # means writing the new item and deleting the old one, atomically.
        client.transact_write_items(TransactItems=[
            {"Put": {
                "TableName": TABLE_NAME,
                "Item": item,
            }},
            {"Delete": {
                "TableName": TABLE_NAME,
                "Key": {"PK": existing["PK"], "SK": existing["SK"]},
            }},
        ])
    return respond(200, to_payment(item))


def delete_payment(user, prop_id, payment_id):
    existing = find_payment(user, prop_id, payment_id)
    if not existing:
        return respond(404, {"message": "Payment not found"})
    table.delete_item(Key={"PK": existing["PK"], "SK": existing["SK"]})
    return respond(204)


# ---------- entry point ----------

def lambda_handler(event, context):
    user = get_user_id(event)
    if not user:
        return respond(401, {"message": "Unauthorized"})

    route = event.get("routeKey", "")
    params = event.get("pathParameters") or {}
    prop_id = params.get("id")
    payment_id = params.get("paymentId")

    try:
        if route == "GET /api/properties/{id}/payments":
            return list_payments(user, prop_id, event)
        if route == "POST /api/properties/{id}/payments":
            return create_payment(user, prop_id, event)
        if route == "GET /api/properties/{id}/payments/{paymentId}":
            return get_payment(user, prop_id, payment_id)
        if route == "PUT /api/properties/{id}/payments/{paymentId}":
            return update_payment(user, prop_id, payment_id, event)
        if route == "DELETE /api/properties/{id}/payments/{paymentId}":
            return delete_payment(user, prop_id, payment_id)
        return respond(404, {"message": f"No route for {route}"})
    except Exception as e:  # log the detail, return a generic error
        print(f"ERROR handling {route}: {e!r}")
        return respond(500, {"message": "Internal server error"})