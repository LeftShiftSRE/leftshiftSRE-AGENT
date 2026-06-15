from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
import random

app = FastAPI(title="inventory_service")

class ReserveRequest(BaseModel):
    order_id: str
    items: list

class ReserveResponse(BaseModel):
    order_id: str
    status: str
    reserved_count: int

@app.post("/reserve", response_model=ReserveResponse)
async def reserve(req: ReserveRequest):
    await asyncio_sleep(random.uniform(0.01, 0.05))
    return ReserveResponse(
        order_id=req.order_id,
        status="reserved",
        reserved_count=len(req.items) if req.items else random.randint(1, 5),
    )

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "inventory_service"}

@app.get("/")
async def root():
    return {"service": "inventory_service", "version": "1.0.0"}