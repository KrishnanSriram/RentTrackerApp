import base64
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

TABLE_NAME = os.environ["TABLE_NAME"]  # fail fast if it isn't configured

table = boto3.resource("dynamodb").Table(TABLE_NAME)


# ---------- helpers ----------

# CORS is configured once on the API Gateway HTTP API (allowed origins are
# your site's exact URLs). API Gateway adds the CORS headers itself, so the
# function returns none.
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


def to_property(item):
    rent = item.get("monthlyRent")
    return {
        "id": item["id"],
        "address": item["address"],
        "monthlyRent": float(rent) if rent is not None else None,
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }


MAX_RENT = Decimal("1000000")
CENT = Decimal("0.01")


def validate_property(data):
    """Returns ((address, monthly_rent_or_None), error_message)."""
    if data is None:
        return None, "Request body must be a JSON object"
    address = str(data.get("address") or "").strip()
    if not address:
        return None, "address is required"
    if len(address) > 300:
        return None, "address must be 300 characters or fewer"

    raw_rent = data.get("monthlyRent")
    if raw_rent is None or (isinstance(raw_rent, str) and not raw_rent.strip()):
        return (address, None), None
    if isinstance(raw_rent, bool):
        return None, "monthlyRent must be a number"
    try:
        rent = Decimal(str(raw_rent).strip())
    except InvalidOperation:
        return None, "monthlyRent must be a number"
    if not rent.is_finite() or rent < 0:
        return None, "monthlyRent must be 0 or more"
    if rent > MAX_RENT:
        return None, "monthlyRent is too large"
    if rent != rent.quantize(CENT):
        return None, "monthlyRent can have at most 2 decimal places"
    return (address, rent.quantize(CENT)), None


# ---------- route handlers ----------

def list_properties(user):
    items = []
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"USER#{user}")
        & Key("SK").begins_with("PROPERTY#")
    }
    while True:
        page = table.query(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    props = sorted((to_property(i) for i in items), key=lambda p: p["address"].lower())
    return respond(200, props)


def create_property(user, event):
    fields, error = validate_property(parse_body(event))
    if error:
        return respond(400, {"message": error})
    address, rent = fields
    prop_id = str(uuid.uuid4())
    ts = now()
    item = {
        "PK": f"USER#{user}",
        "SK": f"PROPERTY#{prop_id}",
        "type": "property",
        "id": prop_id,
        "address": address,
        "createdAt": ts,
        "updatedAt": ts,
    }
    if rent is not None:
        item["monthlyRent"] = rent
    table.put_item(Item=item)
    return respond(201, to_property(item))


def get_property(user, prop_id):
    item = table.get_item(Key={"PK": f"USER#{user}", "SK": f"PROPERTY#{prop_id}"}).get("Item")
    if not item:
        return respond(404, {"message": "Property not found"})
    return respond(200, to_property(item))


def update_property(user, prop_id, event):
    fields, error = validate_property(parse_body(event))
    if error:
        return respond(400, {"message": error})
    address, rent = fields
    values = {":a": address, ":u": now()}
    if rent is None:
        update = "SET address = :a, updatedAt = :u REMOVE monthlyRent"
    else:
        update = "SET address = :a, monthlyRent = :r, updatedAt = :u"
        values[":r"] = rent
    try:
        result = table.update_item(
            Key={"PK": f"USER#{user}", "SK": f"PROPERTY#{prop_id}"},
            UpdateExpression=update,
            ConditionExpression="attribute_exists(PK)",
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return respond(404, {"message": "Property not found"})
        raise
    return respond(200, to_property(result["Attributes"]))


def delete_property(user, prop_id):
    key = {"PK": f"USER#{user}", "SK": f"PROPERTY#{prop_id}"}
    if "Item" not in table.get_item(Key=key):
        return respond(404, {"message": "Property not found"})

    # Remove the property's renters and payments (they share one partition).
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"USER#{user}#PROPERTY#{prop_id}"),
        "ProjectionExpression": "PK, SK",
    }
    with table.batch_writer() as batch:
        while True:
            page = table.query(**kwargs)
            for child in page["Items"]:
                batch.delete_item(Key={"PK": child["PK"], "SK": child["SK"]})
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    table.delete_item(Key=key)
    return respond(204)


# ---------- entry point ----------

def lambda_handler(event, context):
    user = get_user_id(event)
    if not user:
        return respond(401, {"message": "Unauthorized"})

    route = event.get("routeKey", "")
    prop_id = (event.get("pathParameters") or {}).get("id")

    try:
        if route == "GET /api/properties":
            return list_properties(user)
        if route == "POST /api/properties":
            return create_property(user, event)
        if route == "GET /api/properties/{id}":
            return get_property(user, prop_id)
        if route == "PUT /api/properties/{id}":
            return update_property(user, prop_id, event)
        if route == "DELETE /api/properties/{id}":
            return delete_property(user, prop_id)
        return respond(404, {"message": f"No route for {route}"})
    except Exception as e:  # log the detail, return a generic error
        print(f"ERROR handling {route}: {e!r}")
        return respond(500, {"message": "Internal server error"})