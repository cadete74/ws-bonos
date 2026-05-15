from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from config.pairs import pair_by_id, valid_bases

router = APIRouter()


def _db_path() -> str:
    return os.getenv("DB_PATH", "./data/wsbonos.sqlite3")


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(_db_path(), check_same_thread=False)


def _ob(sym: str, side: str) -> str:
    """Correlated subquery: most recent order-book price for sym/side at or before t.ts."""
    return (
        f"(SELECT price FROM orderbooks o WHERE o.symbol='{sym}' "
        f"AND o.side='{side}' AND o.level=1 AND o.ts <= t.ts "
        f"ORDER BY o.ts DESC LIMIT 1)"
    )


@router.get("/ticks/recent")
def ticks_recent(
    pair: str = Query(...),
    limit: int = Query(50, ge=1, le=1000),
) -> List[Dict[str, Any]]:
    """
    Devuelve los N ticks más recientes pre-joined para el par indicado.

    Anchor en leg_a (ORDER BY ts DESC LIMIT N); subquery correlacionada
    para el último precio de leg_b en o antes del mismo ts; igual patrón
    para bid/ask de cada pierna desde orderbooks.

    Respuesta: [{ts, leg_a, leg_b, ratio, last_a, vol_a, turnover_a,
                 last_b, vol_b, turnover_b, bid_a, ask_a, bid_b, ask_b, source}]

    Desconocido pair → 422.
    """
    p = pair_by_id(pair)
    if p is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown pair id '{pair}'. Call /config/pairs for valid ids.",
        )

    leg_a = p["leg_a"]["base"]
    leg_b = p["leg_b"]["base"]

    # Correlated subquery: most recent last price for leg_b at or before each leg_a ts.
    sub_last_b = (
        f"(SELECT last FROM ticks b WHERE b.symbol='{leg_b}' "
        f"AND b.ts <= t.ts ORDER BY b.ts DESC LIMIT 1)"
    )
    sub_vol_b = (
        f"(SELECT vol FROM ticks b WHERE b.symbol='{leg_b}' "
        f"AND b.ts <= t.ts ORDER BY b.ts DESC LIMIT 1)"
    )
    sub_turn_b = (
        f"(SELECT turnover FROM ticks b WHERE b.symbol='{leg_b}' "
        f"AND b.ts <= t.ts ORDER BY b.ts DESC LIMIT 1)"
    )

    sql = f"""
        SELECT
            t.ts,
            t.last     AS last_a,
            t.vol      AS vol_a,
            t.turnover AS turnover_a,
            t.source,
            {sub_last_b}  AS last_b,
            {sub_vol_b}   AS vol_b,
            {sub_turn_b}  AS turnover_b,
            {_ob(leg_a, 'BID')} AS bid_a,
            {_ob(leg_a, 'ASK')} AS ask_a,
            {_ob(leg_b, 'BID')} AS bid_b,
            {_ob(leg_b, 'ASK')} AS ask_b
        FROM ticks t
        WHERE t.symbol = ?
        ORDER BY t.ts DESC
        LIMIT ?
    """

    with _conn() as con:
        cur = con.cursor()
        cur.execute(sql, (leg_a, limit))
        rows = cur.fetchall()

    out: List[Dict[str, Any]] = []
    for (ts, last_a, vol_a, turn_a, source,
         last_b, vol_b, turn_b,
         bid_a, ask_a, bid_b, ask_b) in rows:

        la = float(last_a) if last_a is not None else None
        lb = float(last_b) if last_b is not None else None
        ratio: Optional[float] = (la / lb) if (la is not None and lb is not None and lb != 0) else None

        out.append({
            "ts": ts,
            "leg_a": leg_a,
            "leg_b": leg_b,
            "last_a": la,
            "vol_a": float(vol_a) if vol_a is not None else None,
            "turnover_a": float(turn_a) if turn_a is not None else None,
            "last_b": lb,
            "vol_b": float(vol_b) if vol_b is not None else None,
            "turnover_b": float(turn_b) if turn_b is not None else None,
            "ratio": ratio,
            "bid_a": float(bid_a) if bid_a is not None else None,
            "ask_a": float(ask_a) if ask_a is not None else None,
            "bid_b": float(bid_b) if bid_b is not None else None,
            "ask_b": float(ask_b) if ask_b is not None else None,
            "source": source,
        })

    # Return ascending by ts (consistent with how the frontend renders the table).
    return list(reversed(out))


@router.get("/orderbook/recent")
def orderbook_recent(
    symbol: str = Query(...),
    depth: int = Query(5, ge=1, le=50),
) -> Dict[str, Any]:
    """
    Devuelve el top-N del libro más reciente para `symbol`.
    symbol debe ser una pierna configurada en config/pairs.py.
    Símbolo desconocido → 422.
    """
    if symbol not in valid_bases():
        raise HTTPException(
            status_code=422,
            detail=f"Unknown symbol '{symbol}'. Must be one of: {sorted(valid_bases())}",
        )

    with _conn() as con:
        cur = con.cursor()
        cur.execute("SELECT MAX(ts) FROM orderbooks WHERE symbol=?", (symbol,))
        row = cur.fetchone()
        if not row or not row[0]:
            raise HTTPException(status_code=404, detail=f"Sin orderbook para {symbol}")
        ts = row[0]
        cur.execute(
            """
            SELECT side, level, price, size
            FROM orderbooks
            WHERE symbol=? AND ts=?
            ORDER BY level ASC
            """,
            (symbol, ts),
        )
        bids, asks = [], []
        for side, level, price, size in cur.fetchall():
            item = {
                "level": int(level),
                "price": float(price) if price is not None else None,
                "size": float(size) if size is not None else None,
            }
            if side == "BID" and len(bids) < depth:
                bids.append(item)
            elif side == "ASK" and len(asks) < depth:
                asks.append(item)
            if len(bids) >= depth and len(asks) >= depth:
                break
    return {"symbol": symbol, "ts": ts, "bids": bids, "asks": asks}
