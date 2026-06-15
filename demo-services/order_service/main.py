from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import time

app = FastAPI(title="order_service")

class CreateOrderRequest(BaseModel):
    order_id: str
    user_id: str
    items: list
    payment_token: str

class OrderResult(BaseModel):
    order_id: str
    status: str
    inventory_reserved: bool
    payment_confirmed: bool

@app.post("/create", response_model=OrderResult)
async def create_order(req: CreateOrderRequest):
    inventory_reserved = False
    payment_confirmed = False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            inv_response = await client.post(
                "http://inventory_service:8003/reserve",
                json={"order_id": req.order_id, "items": req.items},
            )
            inv_response.raise_for_status()
            inventory_reserved = True
    except httpx.HTTPError:
        pass

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            pay_response = await client.post(
                "http://payment_service:8002/charge",
                json={"order_id": req.order_id, "payment_token": req.payment_token},
            )
            pay_response.raise_for_status()
            payment_confirmed = True
    except httpx.HTTPError:
        pass

    return OrderResult(
        order_id=req.order_id,
        status="completed" if (inventory_reserved and payment_confirmed) else "partial",
        inventory_reserved=inventory_reserved,
        payment_confirmed=payment_confirmed,
    )

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "order_service"}

@app.get("/")
async def root():
    return {"service": "order_service", "version": "1.0.0"}