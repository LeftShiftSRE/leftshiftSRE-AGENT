from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import time
import uuid
import httpx

app = FastAPI(title="gateway")

class OrderRequest(BaseModel):
    user_id: str
    items: list[dict]
    payment_token: str

class OrderResponse(BaseModel):
    order_id: str
    status: str
    total: float

@app.post("/order", response_model=OrderResponse)
async def create_order(req: OrderRequest):
    start = time.time()
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            payment_response = await client.post(
                "http://order_service:8001/create",
                json={
                    "order_id": order_id,
                    "user_id": req.user_id,
                    "items": req.items,
                    "payment_token": req.payment_token,
                },
            )
            payment_response.raise_for_status()
            result = payment_response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Order creation timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Downstream error: {e.response.text}")

    elapsed = (time.time() - start) * 1000
    return OrderResponse(
        order_id=order_id,
        status="confirmed",
        total=sum(item.get("price", 0) for item in req.items),
    )

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "gateway"}

@app.get("/")
async def root():
    return {"service": "gateway", "version": "1.0.0"}