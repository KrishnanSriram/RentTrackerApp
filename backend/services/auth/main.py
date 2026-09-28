"""Login service: register, sign in, current user. Table key: email."""
import os

import bcrypt
from fastapi import Depends, HTTPException

from common import EMAIL, create_app, current_user, fail, make_token, new_id, now, table, text

app = create_app("auth")
users = table(os.getenv("TABLE_NAME", "rent-users"), "email")
DUMMY_HASH = bcrypt.hashpw(b"unused", bcrypt.gensalt())  # keeps login timing the same for unknown emails


@app.post("/api/auth/register", status_code=201)
def register(body: dict):
    password = str(body.get("password") or "")
    if not 8 <= len(password.encode()) <= 72:
        fail("password must be 8 to 72 characters")
    user = {
        "id": new_id(),
        "email": text(body, "email", required=True, max_len=320, pattern=EMAIL).lower(),
        "name": text(body, "name", required=True),
        "passwordHash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
        "createdAt": now(),
    }
    try:
        users.put_item(Item=user, ConditionExpression="attribute_not_exists(email)")
    except users.meta.client.exceptions.ConditionalCheckFailedException:
        raise HTTPException(409, "An account with this email already exists.")
    return make_token(user)


@app.post("/api/auth/login")
def login(body: dict):
    email = str(body.get("email") or "").strip().lower()
    password = str(body.get("password") or "").encode()[:72]
    user = users.get_item(Key={"email": email}).get("Item") if email else None
    stored = user["passwordHash"].encode() if user else DUMMY_HASH
    if not bcrypt.checkpw(password, stored) or not user:
        raise HTTPException(401, "Invalid email or password.")
    return make_token(user)


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    if "Item" not in users.get_item(Key={"email": user["email"]}):
        raise HTTPException(401, "Account no longer exists")
    return {"id": user["id"], "email": user["email"], "name": user["name"]}
