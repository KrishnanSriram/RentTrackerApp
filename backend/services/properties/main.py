"""Properties service. Table keys: ownerId + id."""
import os

from fastapi import Depends

from common import call, create_app, current_user, get_owned, list_owned, new_id, now, table, text, number, to_item

app = create_app("properties")
props = table(os.getenv("TABLE_NAME", "rent-properties"), "ownerId", "id")
P = "/api/properties"


def validate(body: dict) -> dict:
    return {
        "name": text(body, "name"),
        "street": text(body, "street", required=True, max_len=300),
        "unit": text(body, "unit", max_len=50),
        "city": text(body, "city", required=True, max_len=120),
        "state": text(body, "state", required=True, pattern=r"[A-Za-z]{2}").upper(),
        "zip": text(body, "zip", required=True, pattern=r"\d{5}(-\d{4})?"),
        "monthlyRent": number(body, "monthlyRent"),
    }


@app.get(P)
def list_properties(user: dict = Depends(current_user)):
    return sorted(list_owned(props, user["id"]), key=lambda p: p["createdAt"])


@app.post(P, status_code=201)
def create_property(body: dict, user: dict = Depends(current_user)):
    item = {**validate(body), "id": new_id(), "ownerId": user["id"], "createdAt": now()}
    props.put_item(Item=to_item(item))
    return item


@app.get(P + "/{property_id}")
def get_property(property_id: str, user: dict = Depends(current_user)):
    return get_owned(props, user["id"], property_id, "Property")


@app.put(P + "/{property_id}")
def update_property(property_id: str, body: dict, user: dict = Depends(current_user)):
    item = {**get_owned(props, user["id"], property_id, "Property"), **validate(body)}
    props.put_item(Item=to_item(item))
    return item


@app.delete(P + "/{property_id}", status_code=204)
async def delete_property(property_id: str, user: dict = Depends(current_user)):
    get_owned(props, user["id"], property_id, "Property")
    # Renters and payments live in other services; remove them first so nothing is left behind
    await call("DELETE", "renters", "/api/renters", user, {"propertyId": property_id})
    await call("DELETE", "payments", "/api/payments", user, {"propertyId": property_id})
    props.delete_item(Key={"ownerId": user["id"], "id": property_id})
