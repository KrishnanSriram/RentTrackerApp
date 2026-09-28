"""Renters service: occupants and their contact details. Table keys: ownerId + id."""
import os

from fastapi import Depends

from common import (EMAIL, create_app, current_user, delete_owned, fail, get_owned, list_owned, new_id, now,
                    require_property, table, text)

app = create_app("renters")
renters = table(os.getenv("TABLE_NAME", "rent-renters"), "ownerId", "id")
P = "/api/renters"


def validate(body: dict) -> dict:
    role = text(body, "role") or "primary"
    if role not in ("primary", "secondary"):
        fail("role must be primary or secondary")
    return {
        "propertyId": text(body, "propertyId", required=True),
        "name": text(body, "name", required=True),
        "email": text(body, "email", max_len=320, pattern=EMAIL).lower(),
        "phone": text(body, "phone", max_len=40, pattern=r"[0-9+()\-.\s]+"),
        "role": role,
    }


@app.get(P)
def list_renters(propertyId: str | None = None, user: dict = Depends(current_user)):
    items = list_owned(renters, user["id"], propertyId=propertyId)
    return sorted(items, key=lambda r: (r["role"] != "primary", r["name"].lower()))  # primary contacts first


@app.post(P, status_code=201)
async def create_renter(body: dict, user: dict = Depends(current_user)):
    item = validate(body)
    await require_property(user, item["propertyId"])
    item.update(id=new_id(), ownerId=user["id"], createdAt=now())
    renters.put_item(Item=item)
    return item


@app.get(P + "/{renter_id}")
def get_renter(renter_id: str, user: dict = Depends(current_user)):
    return get_owned(renters, user["id"], renter_id, "Renter")


@app.put(P + "/{renter_id}")
async def update_renter(renter_id: str, body: dict, user: dict = Depends(current_user)):
    item = get_owned(renters, user["id"], renter_id, "Renter")
    changes = validate(body)
    if changes["propertyId"] != item["propertyId"]:
        await require_property(user, changes["propertyId"])
    item.update(changes)
    renters.put_item(Item=item)
    return item


@app.delete(P + "/{renter_id}", status_code=204)
def delete_renter(renter_id: str, user: dict = Depends(current_user)):
    get_owned(renters, user["id"], renter_id, "Renter")
    renters.delete_item(Key={"ownerId": user["id"], "id": renter_id})


@app.delete(P, status_code=204)
def delete_property_renters(propertyId: str, user: dict = Depends(current_user)):
    """Called by the properties service when a property is deleted."""
    delete_owned(renters, user["id"], propertyId=propertyId)
