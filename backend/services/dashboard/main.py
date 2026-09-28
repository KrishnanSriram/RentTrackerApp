"""Dashboard service: read-only monthly summaries built from the properties, renters and payments
services. It has no table of its own."""
import asyncio
from collections import defaultdict
from datetime import date

from fastapi import Depends, Query

from common import MONTH, call, create_app, current_user, require_property

app = create_app("dashboard")


def add_months(month: str, n: int) -> str:
    y, m = map(int, month.split("-"))
    total = y * 12 + m - 1 + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def rent_status(monthly_rent, paid: float, occupied=True) -> dict:
    due, paid = round(float(monthly_rent), 2), round(paid, 2)
    if not occupied and paid == 0:
        return {"due": due, "paid": 0, "balance": 0, "status": "vacant"}
    status = "paid" if due > 0 and paid >= due else "partial" if paid > 0 else "unpaid"
    return {"due": due, "paid": paid, "balance": round(max(due - paid, 0), 2), "status": status}


@app.get("/api/dashboard")
async def dashboard(month: str | None = Query(None, pattern=MONTH), user: dict = Depends(current_user)):
    """Rent due, collected and outstanding for every property in one month (default: this month)."""
    month = month or date.today().strftime("%Y-%m")
    properties, renters, payments = await asyncio.gather(
        call("GET", "properties", "/api/properties", user),
        call("GET", "renters", "/api/renters", user),
        call("GET", "payments", "/api/payments", user, {"month": month}),
    )
    people, paid = defaultdict(list), defaultdict(float)
    for r in renters:
        people[r["propertyId"]].append(r)  # already sorted primary first
    for p in payments:
        paid[p["propertyId"]] += p["amount"]

    rows = []
    for prop in properties:
        who = people[prop["id"]]
        rows.append({
            "property": prop,
            "primaryRenter": who[0] if who else None,
            "renterCount": len(who),
            **rent_status(prop["monthlyRent"], paid[prop["id"]], occupied=bool(who)),
        })
    active = [r for r in rows if r["status"] != "vacant"]
    totals = {
        "properties": len(rows),
        "occupied": len(active),
        "paidInFull": sum(r["status"] == "paid" for r in active),
        "due": round(sum(r["due"] for r in active), 2),
        "paid": round(sum(r["paid"] for r in active), 2),
        "outstanding": round(sum(r["balance"] for r in active), 2),
    }
    return {"month": month, "totals": totals, "properties": rows}


@app.get("/api/dashboard/properties/{property_id}/history")
async def history(
    property_id: str,
    months: int = Query(12, ge=1, le=60),
    endMonth: str | None = Query(None, pattern=MONTH),
    user: dict = Depends(current_user),
):
    """Month-by-month status for one property, newest first."""
    end = endMonth or date.today().strftime("%Y-%m")
    prop, payments = await asyncio.gather(
        require_property(user, property_id),
        call("GET", "payments", "/api/payments", user,
             {"propertyId": property_id, "fromMonth": add_months(end, 1 - months), "toMonth": end}),
    )
    paid = defaultdict(float)
    for p in payments:
        paid[p["month"]] += p["amount"]
    return {
        "propertyId": property_id,
        "months": [{"month": m, **rent_status(prop["monthlyRent"], paid[m])}
                   for m in (add_months(end, -i) for i in range(months))],
    }
