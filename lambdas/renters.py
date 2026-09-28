import base64
import json
import os
import re
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

TABLE_NAME = os.environ["TABLE_NAME"]  # fail fast if it isn't configured

table = boto3.resource("dynamodb").Table(TABLE_NAME)

CONTACT_TYPES = ("primary", "secondary")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+()\-.\s]{7,25}$")


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
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def now():
    return datetime.now(timezone.utc).isoformat()


def renter_pk(user, prop_id):
    return f"USER#{user}#PROPERTY#{prop_id}"


def property_exists(user, prop_id):
    item = table.get_item(
        Key={"PK": f"USER#{user}", "SK": f"PROPERTY#{prop_id}"},
        ProjectionExpression="PK",
    ).get("Item")
    return item is not None


def to_renter(item):
    return {
        "id": item["id"],
        "propertyId": item["propertyId"],
        "name": item["name"],
        "email": item.get("email", ""),
        "phone": item.get("phone", ""),
        "contactType": item.get("contactType", "primary"),
        "createdAt": item.get("createdAt"),
        "updatedAt": item.get("updatedAt"),
    }


def validate_renter(data):
    """Returns (clean_fields, error_message)."""
    if data is None:
        return None, "Request body must be a JSON object"

    name = str(data.get("name") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    phone = str(data.get("phone") or "").strip()
    contact_type = str(data.get("contactType") or "primary").strip().lower()

    if not name:
        return None, "name is required"
    if len(name) > 120:
        return None, "name must be 120 characters or fewer"
    if email and (len(email) > 254 or not EMAIL_RE.match(email)):
        return None, "email is not a valid email address"
    if phone and not PHONE_RE.match(phone):
        return None, "phone may contain only digits, spaces and + ( ) - ."
    if contact_type not in CONTACT_TYPES:
        return None, "contactType must be 'primary' or 'secondary'"

    return {"name": name, "email": email, "phone": phone, "contactType": contact_type}, None


# ---------- route handlers ----------

def list_renters(user, prop_id):
    if not property_exists(user, prop_id):
        return respond(404, {"message": "Property not found"})
    items = []
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(renter_pk(user, prop_id))
        & Key("SK").begins_with("RENTER#")
    }
    while True:
        page = table.query(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    renters = [to_renter(i) for i in items]
    # Primary contacts first, then alphabetical by name.
    renters.sort(key=lambda r: (r["contactType"] != "primary", r["name"].lower()))
    return respond(200, renters)


def create_renter(user, prop_id, event):
    fields, error = validate_renter(parse_body(event))
    if error:
        return respond(400, {"message": error})
    if not property_exists(user, prop_id):
        return respond(404, {"message": "Property not found"})

    renter_id = str(uuid.uuid4())
    ts = now()
    item = {
        "PK": renter_pk(user, prop_id),
        "SK": f"RENTER#{renter_id}",
        "type": "renter",
        "id": renter_id,
        "propertyId": prop_id,
        **fields,
        "createdAt": ts,
        "updatedAt": ts,
    }
    table.put_item(Item=item)
    return respond(201, to_renter(item))


def get_renter(user, prop_id, renter_id):
    item = table.get_item(
        Key={"PK": renter_pk(user, prop_id), "SK": f"RENTER#{renter_id}"}
    ).get("Item")
    if not item:
        return respond(404, {"message": "Renter not found"})
    return respond(200, to_renter(item))


def update_renter(user, prop_id, renter_id, event):
    fields, error = validate_renter(parse_body(event))
    if error:
        return respond(400, {"message": error})
    try:
        result = table.update_item(
            Key={"PK": renter_pk(user, prop_id), "SK": f"RENTER#{renter_id}"},
            UpdateExpression=(
                "SET #n = :n, email = :e, phone = :p, contactType = :c, updatedAt = :u"
            ),
            ConditionExpression="attribute_exists(PK)",
            ExpressionAttributeNames={"#n": "name"},  # "name" is a DynamoDB reserved word
            ExpressionAttributeValues={
                ":n": fields["name"],
                ":e": fields["email"],
                ":p": fields["phone"],
                ":c": fields["contactType"],
                ":u": now(),
            },
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return respond(404, {"message": "Renter not found"})
        raise
    return respond(200, to_renter(result["Attributes"]))


def delete_renter(user, prop_id, renter_id):
    try:
        table.delete_item(
            Key={"PK": renter_pk(user, prop_id), "SK": f"RENTER#{renter_id}"},
            ConditionExpression="attribute_exists(PK)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return respond(404, {"message": "Renter not found"})
        raise
    return respond(204)


# ---------- entry point ----------

def lambda_handler(event, context):
    user = get_user_id(event)
    if not user:
        return respond(401, {"message": "Unauthorized"})

    route = event.get("routeKey", "")
    params = event.get("pathParameters") or {}
    prop_id = params.get("id")
    renter_id = params.get("renterId")

    try:
        if route == "GET /api/properties/{id}/renters":
            return list_renters(user, prop_id)
        if route == "POST /api/properties/{id}/renters":
            return create_renter(user, prop_id, event)
        if route == "GET /api/properties/{id}/renters/{renterId}":
            return get_renter(user, prop_id, renter_id)
        if route == "PUT /api/properties/{id}/renters/{renterId}":
            return update_renter(user, prop_id, renter_id, event)
        if route == "DELETE /api/properties/{id}/renters/{renterId}":
            return delete_renter(user, prop_id, renter_id)
        return respond(404, {"message": f"No route for {route}"})
    except Exception as e:  # log the detail, return a generic error
        print(f"ERROR handling {route}: {e!r}")
        return respond(500, {"message": "Internal server error"})