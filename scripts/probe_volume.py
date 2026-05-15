from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx
import websockets

BASE = os.environ["XOMS_BASE_URL"].rstrip("/")
WS = os.environ["XOMS_WS_URL"].rstrip("/")
USER = os.environ["XOMS_USER"]
PASS = os.environ["XOMS_PASS"]

SYMBOLS = ["MERV - XMEV - AL30 - 24hs", "MERV - XMEV - GD30 - 24hs"]
# Entries candidatas de volumen + algunas de contexto para ver qué responde Eco.
ENTRIES = ["LA", "TV", "EV", "NV", "OP", "CL", "HI", "LO"]


async def main() -> None:
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{BASE}/auth/getToken",
            headers={"X-Username": USER, "X-Password": PASS},
        )
    token = r.headers.get("X-Auth-Token")
    if not token:
        print(f"LOGIN FAIL status={r.status_code} body={r.text[:300]}")
        sys.exit(1)
    print("login OK")

    async with websockets.connect(
        WS, additional_headers={"X-Auth-Token": token}
    ) as ws:
        sub = {
            "type": "smd",
            "level": 1,
            "entries": ENTRIES,
            "products": [{"symbol": s, "marketId": "ROFX"} for s in SYMBOLS],
        }
        await ws.send(json.dumps(sub))
        print(f"subscribed entries={ENTRIES}")
        seen = 0
        while seen < 12:
            raw = await asyncio.wait_for(ws.recv(), timeout=20.0)
            data = json.loads(raw)
            if data.get("status") == "ERROR":
                print("SUBSCRIBE ERROR:", data)
                return
            if data.get("type") != "Md":
                print("non-Md:", data)
                continue
            sym = (data.get("instrumentId") or {}).get("symbol")
            md = data.get("marketData") or {}
            print(f"--- Md #{seen} {sym} keys={sorted(md.keys())} ---")
            print(json.dumps(md, indent=2, ensure_ascii=False))
            seen += 1


if __name__ == "__main__":
    asyncio.run(main())
