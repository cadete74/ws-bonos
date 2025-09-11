from __future__ import annotations
import os, sqlite3
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query, HTTPException

router = APIRouter()

def _db_path() -> str:
    return os.getenv("DB_PATH", "./data/wsbonos.sqlite3")

def _conn() -> sqlite3.Connection:
    return sqlite3.connect(_db_path(), check_same_thread=False)

@router.get("/ticks/recent")
def ticks_recent(
    symbol: Optional[str] = Query(None, pattern="^(AL30|GD30)$"),
    limit: int = Query(50, ge=1, le=1000),
) -> List[Dict[str, Any]]:
    """
    Devuelve ticks recientes. Si `symbol` es AL30 o GD30, devuelve `last` de esa pierna.
    Con el esquema actual (fila combinada), se mapea:
      - AL30 → SELECT ts, al30 AS last, source FROM ticks
      - GD30 → SELECT ts, gd30 AS last, source FROM ticks
    Si `symbol` es None, devuelve ambas piernas por fila.
    """
    q_all = "SELECT ts, al30, gd30, source FROM ticks ORDER BY ts DESC LIMIT ?"
    q_sym = {
        "AL30": "SELECT ts, al30 AS last, source FROM ticks ORDER BY ts DESC LIMIT ?",
        "GD30": "SELECT ts, gd30 AS last, source FROM ticks ORDER BY ts DESC LIMIT ?",
    }
    with _conn() as con:
        cur = con.cursor()
        if symbol in ("AL30", "GD30"):
            cur.execute(q_sym[symbol], (limit,))
            rows = [{"ts": ts, "symbol": symbol, "last": float(last), "source": source} for ts, last, source in cur.fetchall()]
            return list(reversed(rows))  # ascendente como pedía el API viejo
        cur.execute(q_all, (limit,))
        out = []
        for ts, al30, gd30, source in cur.fetchall():
            out.append({"ts": ts, "AL30": float(al30) if al30 is not None else None,
                        "GD30": float(gd30) if gd30 is not None else None, "source": source})
        return list(reversed(out))

@router.get("/orderbook/recent")
def orderbook_recent(
    symbol: str = Query(..., pattern="^(AL30|GD30)$"),
    depth: int = Query(5, ge=1, le=50),
) -> Dict[str, Any]:
    """
    Devuelve el top-N del libro más reciente para `symbol`.
    Estructura: {symbol, ts, bids:[{level,price,size}], asks:[...]}
    """
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
            item = {"level": int(level), "price": float(price) if price is not None else None,
                    "size": float(size) if size is not None else None}
            if side == "BID" and len(bids) < depth:
                bids.append(item)
            elif side == "ASK" and len(asks) < depth:
                asks.append(item)
            # paramos si ya tenemos ambos
            if len(bids) >= depth and len(asks) >= depth:
                break
        return {"symbol": symbol, "ts": ts, "bids": bids, "asks": asks}
