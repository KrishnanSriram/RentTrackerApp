"""Payments service: rent received. A month can have any number of (partial) payments.
Table keys: ownerId + id."""
import os
from datetime import date

from fastapi import Depends, Query

from common import (MONTH, create_app, current_user, delete_owned, fail, get_owned, list_owned, new_id, now, number,
                    require_property, table, text, to_item)

app = create_app("payments")
payments = table(os.getenv("TABLE_NAME", "rent-payments"), "ownerId", "id")
P = "/api/payments"


def validate(body: dict) -> dict:
    item = {
        "propertyId": text(body, "propertyId", required=True),
        "month": text(body, "month", required=True, pattern=MONTH),  # rent month it applies to
        "amount": number(body, "amount", positive=True),
        "date": text(body, "date", required=True),  # date received, YYYY-MM-DD
        "method": text(body, "method", max_len=40),
        "note": text(body, "note", max_len=500),
    }
    try:
        date.fromisoformat(item["date"])
    except ValueError:
        fail("date must be YYYY-MM-DD")
    return item


@app.get(P)
def list_payments(
    propertyId: str | None = None,
    month: str | None = Query(None, pattern=MONTH),
    fromMonth: str | None = Query(None, pattern=MONTH),
    toMonth: str | None = Query(None, pattern=MONTH),
    user: dict = Depends(current_user),
):
    items = list_owned(payments, user["id"], propertyId=propertyId, month=month)
    # 'YYYY-MM' strings sort in date order, so plain string comparison works for ranges
    items = [p for p in items if (not fromMonth or p["month"] >= fromMonth) and (not toMonth or p["month"] <= toMonth)]
    return sorted(items, key=lambda p: (p["month"], p["date"], p["createdAt"]))


@app.post(P, status_code=201)
async def create_payment(body: dict, user: dict = Depends(current_user)):
    item = validate(body)
    await require_property(user, item["propertyId"])
    item.update(id=new_id(), ownerId=user["id"], createdAt=now())
    payments.put_item(Item=to_item(item))
    return item


@app.get(P + "/{payment_id}")
def get_payment(payment_id: str, user: dict = Depends(current_user)):
    return get_owned(payments, user["id"], payment_id, "Payment")


@app.put(P + "/{payment_id}")
async def update_payment(payment_id: str, body: dict, user: dict = Depends(current_user)):
    item = get_owned(payments, user["id"], payment_id, "Payment")
    changes = validate(body)
    if changes["propertyId"] != item["propertyId"]:
        await require_property(user, changes["propertyId"])
    item.update(changes)
    payments.put_item(Item=to_item(item))
    return item


@app.delete(P + "/{payment_id}", status_code=204)
def delete_payment(payment_id: str, user: dict = Depends(current_user)):
    get_owned(payments, user["id"], payment_id, "Payment")
    payments.delete_item(Key={"ownerId": user["id"], "id": payment_id})


@app.delete(P, status_code=204)
def delete_property_payments(propertyId: str, user: dict = Depends(current_user)):
    """Called by the properties service when a property is deleted."""
    delete_owned(payments, user["id"], propertyId=propertyId)
