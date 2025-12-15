from fastapi import FastAPI, HTTPException
from datetime import datetime
import os

app = FastAPI()

# TEMP: replace with DB later
LICENSES = {
    "LIC-abc123": {
        "client_id": "padel-club-01",
        "status": "active",
        "expires_at": "2025-09-01"
    }
}

@app.post("/license/verify")
def verify_license(payload: dict):
    key = payload.get("license_key")
    license = LICENSES.get(key)

    if not license:
        return {"allowed": False, "reason": "invalid_license"}

    if license["status"] != "active":
        return {"allowed": False, "reason": "suspended"}

    if datetime.utcnow() > datetime.fromisoformat(license["expires_at"]):
        return {"allowed": False, "reason": "expired"}

    return {
        "allowed": True,
        "expires_at": license["expires_at"]
    }
