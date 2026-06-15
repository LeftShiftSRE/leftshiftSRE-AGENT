from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time
import random
import sqlite3

app = FastAPI(title="payment_service")

DB_PATH = "/tmp/payment.db"

class ChargeRequest(BaseModel):
    order_id: str
    payment_token: str
    amount: float = 100.0

class ChargeResponse(BaseModel):
    charge_id: str
    status: str
    amount: float
    processing_time_ms: float

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS charges (charge_id TEXT, order_id TEXT, amount REAL, status TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS card_tokens (token TEXT PRIMARY KEY, last4 TEXT, brand TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS order_items (order_id TEXT, item_id TEXT, sku TEXT, price REAL)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO card_tokens VALUES ('tok_visa_4242', '4242', 'visa')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO card_tokens VALUES ('tok_master_5555', '5555', 'mastercard')"
    )
    for i in range(10):
        conn.execute(
            f"INSERT OR IGNORE INTO order_items VALUES ('ORD-12345', 'ITEM-{i:03d}', 'SKU-{i:03d}', {random.uniform(10, 100):.2f})"
        )
    conn.commit()
    conn.close()

init_db()

@app.post("/charge", response_model=ChargeResponse)
async def charge(req: ChargeRequest):
    start = time.time()
    charge_id = f"chg_{int(time.time() * 1000)}"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM card_tokens WHERE token = ?", (req.payment_token,))
    card = cursor.fetchone()

    if not card:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid payment token")

    cursor.execute("SELECT * FROM charges WHERE order_id = ?", (req.order_id,))
    existing = cursor.fetchone()

    cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (req.order_id,))
    items = cursor.fetchall()

    total_amount = sum(float(row["price"]) for row in items)

    time.sleep(random.uniform(0.05, 0.15))

    cursor.execute(
        "INSERT INTO charges (charge_id, order_id, amount, status, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (charge_id, req.order_id, total_amount, "succeeded"),
    )
    conn.commit()
    conn.close()

    processing_time = (time.time() - start) * 1000
    return ChargeResponse(
        charge_id=charge_id,
        status="succeeded",
        amount=total_amount,
        processing_time_ms=round(processing_time, 2),
    )

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "payment_service"}

@app.get("/")
async def root():
    return {"service": "payment_service", "version": "1.0.0"}