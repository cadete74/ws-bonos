from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routers.config import router as config_router
from .routers.market import router as market_router

app = FastAPI(title="WS Bonos API", version="0.2.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# REST routes: ticks + orderbook
app.include_router(market_router)

# Config routes: /config/pairs (tab list for the frontend)
app.include_router(config_router)

# Static pages served at /static/*
app.mount("/static", StaticFiles(directory="static"), name="static")
