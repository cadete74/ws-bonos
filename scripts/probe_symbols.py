from __future__ import annotations

"""
probe_symbols.py — Verify XOMS symbol strings against live Eco Valores.

Usage:
  python3 scripts/probe_symbols.py "MERV - XMEV - AL35 - 24hs" "MERV - XMEV - GD35 - 24hs"

  Or via Makefile:
  make probe-symbols SYMBOLS="MERV - XMEV - AL35 - 24hs MERV - XMEV - GD35 - 24hs"

PASS: received at least 1 Md message within timeout.
FAIL: subscribe ERROR response or timeout.

Exit code is non-zero if any symbol FAILs.

Requires env vars: XOMS_BASE_URL, XOMS_WS_URL, XOMS_USER, XOMS_PASS
"""

import asyncio
import json
import os
import sys

import httpx
import websockets

BASE_URL: str = os.getenv("XOMS_BASE_URL", "").rstrip("/")
WS_URL: str = os.getenv("XOMS_WS_URL", "").rstrip("/")
USER: str = os.getenv("XOMS_USER", "")
PASS: str = os.getenv("XOMS_PASS", "")

MARKET_ID = "ROFX"
MD_TIMEOUT_S = 10.0  # seconds to wait for at least one Md per symbol


async def _login() -> str:
    """Login to XOMS and return the auth token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/auth/getToken",
            headers={"X-Username": USER, "X-Password": PASS},
        )
    token = resp.headers.get("X-Auth-Token")
    if not token:
        print(f"LOGIN FAIL — status={resp.status_code} body={resp.text[:300]}")
        sys.exit(1)
    print("Login OK")
    return token


async def _probe_one(ws: websockets.ClientConnection, symbol: str) -> tuple[str, bool, str]:
    """
    Subscribe to a single symbol and wait up to MD_TIMEOUT_S for an Md message.
    Returns (symbol, passed, detail).
    """
    # LA alone is fragile for illiquid bonds (no trades = no Md even if the
    # symbol is valid). BI/OF confirm the symbol exists whenever it quotes.
    sub = {
        "type": "smd",
        "level": 1,
        "entries": ["LA", "BI", "OF"],
        "products": [{"symbol": symbol, "marketId": MARKET_ID}],
    }
    await ws.send(json.dumps(sub))

    try:
        deadline = asyncio.get_event_loop().time() + MD_TIMEOUT_S
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return symbol, False, "TIMEOUT — no Md received within 10s"
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                return symbol, False, "TIMEOUT — no Md received within 10s"

            data = json.loads(raw)
            if data.get("status") == "ERROR":
                desc = data.get("description") or data.get("message") or str(data)
                return symbol, False, f"ERROR — {desc}"
            if data.get("type") == "Md":
                md = data.get("marketData") or {}
                la = md.get("LA")
                price = None
                if isinstance(la, dict):
                    price = la.get("price")
                return symbol, True, f"PASS — first Md price={price}"
    except Exception as exc:
        return symbol, False, f"EXCEPTION — {exc}"


async def main(symbols: list[str]) -> None:
    if not symbols:
        print("Usage: probe_symbols.py <symbol1> [symbol2] ...")
        print('  e.g.: probe_symbols.py "MERV - XMEV - AL35 - 24hs" "MERV - XMEV - GD35 - 24hs"')
        sys.exit(1)

    missing = [k for k, v in {
        "XOMS_BASE_URL": BASE_URL, "XOMS_WS_URL": WS_URL,
        "XOMS_USER": USER, "XOMS_PASS": PASS,
    }.items() if not v]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    token = await _login()

    results: list[tuple[str, bool, str]] = []

    # Probe each symbol sequentially on a single WS connection.
    # Sequential approach ensures each subscribe/response pair is unambiguous.
    async with websockets.connect(WS_URL, additional_headers={"X-Auth-Token": token}) as ws:
        for sym in symbols:
            print(f"  Probing: {sym!r}")
            result = await _probe_one(ws, sym)
            results.append(result)
            status = "PASS" if result[1] else "FAIL"
            print(f"    {status}: {result[2]}")

    print()
    print("=== Probe Summary ===")
    all_passed = True
    for sym, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {sym!r}")
        print(f"         {detail}")
        if not passed:
            all_passed = False

    if not all_passed:
        failed = [sym for sym, passed, _ in results if not passed]
        print(f"\nFAILED symbols ({len(failed)}):")
        for s in failed:
            print(f"  - {s!r}")
        sys.exit(1)

    print("\nAll symbols PASSED.")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
