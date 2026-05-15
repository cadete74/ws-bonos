from __future__ import annotations
import os, sqlite3, asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from .routers.market import router as market_router

app = FastAPI(title="WS Bonos API", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok"}

# Rutas REST (ticks + orderbook)
app.include_router(market_router)

# Páginas HTML servidas en /static/* (index.html, tabla.html)
app.mount("/static", StaticFiles(directory="static"), name="static")

# WebSocket: emite el último tick cuando hay uno nuevo en la DB
@app.websocket("/ws")
async def ws_ticks(ws: WebSocket):
    await ws.accept()
    db_path = os.getenv("DB_PATH", "./data/wsbonos.sqlite3")
    last_ts: str | None = None
    try:
        while True:
            try:
                con = sqlite3.connect(db_path)
                cur = con.cursor()
                cur.execute("SELECT ts, al30, gd30, source FROM ticks ORDER BY ts DESC LIMIT 1;")
                row = cur.fetchone()
            finally:
                try:
                    con.close()
                except Exception:
                    pass

            if row:
                ts, al30, gd30, source = row
                if ts != last_ts:
                    await ws.send_json({
                        "ts": ts,
                        "AL30": float(al30) if al30 is not None else None,
                        "GD30": float(gd30) if gd30 is not None else None,
                        "source": source,
                    })
                    last_ts = ts
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
