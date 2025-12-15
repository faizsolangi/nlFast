import os
import sqlite3
import threading
from datetime import datetime

from fastapi import FastAPI
import uvicorn

# =========================
# CONFIG
# =========================
DB_PATH = "licenses.db"
PORT = int(os.environ.get("PORT", 10000))

# =========================
# DATABASE INIT
# =========================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # License master table (KILL SWITCH LIVES HERE)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            client_id TEXT,
            status TEXT,
            expires_at TEXT
        )
    """)

    # Usage / audit stream
    cur.execute("""
        CREATE TABLE IF NOT EXISTS license_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            license_key TEXT,
            client_id TEXT,
            workflow_id TEXT,
            whatsapp_number TEXT,
            allowed INTEGER,
            reason TEXT
        )
    """)

    # Seed dev license (safe default)
    cur.execute("""
        INSERT OR IGNORE INTO licenses
        (license_key, client_id, status, expires_at)
        VALUES (?, ?, ?, ?)
    """, ("LIC-dev", "internal", "active", "2099-01-01"))

    conn.commit()
    conn.close()

init_db()

# =========================
# FASTAPI — LICENSE API
# =========================
app = FastAPI()

@app.post("/license/verify")
def verify_license(payload: dict):
    license_key = payload.get("license_key")
    client_id = payload.get("client_id")
    workflow_id = payload.get("workflow_id")
    whatsapp = payload.get("whatsapp_number")

    allowed = True
    reason = None
    expires_at = None

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT status, expires_at
        FROM licenses
        WHERE license_key = ?
    """, (license_key,))
    row = cur.fetchone()

    if not row:
        allowed = False
        reason = "invalid_license"
    else:
        status, expires_at = row
        if status != "active":
            allowed = False
            reason = "suspended"
        elif datetime.utcnow() > datetime.fromisoformat(expires_at):
            allowed = False
            reason = "expired"

    # Log event (this is your stream)
    cur.execute("""
        INSERT INTO license_events
        (timestamp, license_key, client_id, workflow_id, whatsapp_number, allowed, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(),
        license_key,
        client_id,
        workflow_id,
        whatsapp,
        int(allowed),
        reason
    ))

    conn.commit()
    conn.close()

    return {
        "allowed": allowed,
        "reason": reason,
        "expires_at": expires_at
    }

# =========================
# STREAMLIT DASHBOARD
# =========================
def run_dashboard():
    import streamlit as st
    import pandas as pd

    st.set_page_config(page_title="License Control", layout="wide")
    st.title("🔐 License Control Dashboard")

    conn = sqlite3.connect(DB_PATH)

    # -------------------------
    # KILL SWITCH PANEL
    # -------------------------
    st.subheader("🛑 License Kill Switch")

    licenses_df = pd.read_sql("""
        SELECT license_key, client_id, status, expires_at
        FROM licenses
        ORDER BY client_id
    """, conn)

    for _, row in licenses_df.iterrows():
        c1, c2, c3, c4 = st.columns([3, 3, 2, 2])

        c1.write(row["license_key"])
        c2.write(row["client_id"])
        c3.write(row["expires_at"])

        toggle = c4.toggle(
            "Active",
            value=(row["status"] == "active"),
            key=row["license_key"]
        )

        new_status = "active" if toggle else "suspended"
        if new_status != row["status"]:
            cur = conn.cursor()
            cur.execute("""
                UPDATE licenses
                SET status = ?
                WHERE license_key = ?
            """, (new_status, row["license_key"]))
            conn.commit()
            st.toast(
                f"{row['license_key']} → {new_status.upper()}",
                icon="⚡"
            )

    st.divider()

    # -------------------------
    # USAGE STREAM
    # -------------------------
    st.subheader("📊 License Usage Stream (Live)")

    events_df = pd.read_sql("""
        SELECT
            timestamp,
            license_key,
            client_id,
            workflow_id,
            whatsapp_number,
            allowed,
            reason
        FROM license_events
        ORDER BY timestamp DESC
        LIMIT 200
    """, conn)

    conn.close()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Requests", len(events_df))
    col2.metric("Allowed", int(events_df["allowed"].sum()))
    col3.metric("Denied", int((events_df["allowed"] == 0).sum()))

    st.dataframe(events_df, use_container_width=True, hide_index=True)
    st.caption("Auto-refresh every 10 seconds")

    st.experimental_rerun()

# =========================
# STREAMLIT BOOTSTRAP
# =========================
def start_streamlit():
    from streamlit.web import bootstrap
    bootstrap.run(
        "main.py",
        command_line="",
        args=[],
        flag_options={}
    )

# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    threading.Thread(target=start_streamlit, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=PORT)
