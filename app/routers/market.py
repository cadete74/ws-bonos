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
    # Subquery: precio del último libro (level 1) en o antes del ts del tick.
    def _ob(sym: str, side: str) -> str:
        return (
            f"(SELECT price FROM orderbooks o WHERE o.symbol='{sym}' "
            f"AND o.side='{side}' AND o.level=1 AND o.ts <= t.ts "
            f"ORDER BY o.ts DESC LIMIT 1)"
        )

    q_all = f"""
        SELECT t.ts, t.al30, t.gd30, t.source,
               t.vol_al30, t.vol_gd30, t.turn_al30, t.turn_gd30,
               {_ob('AL30','BID')} AS bi_al30,
               {_ob('AL30','ASK')} AS of_al30,
               {_ob('GD30','BID')} AS bi_gd30,
               {_ob('GD30','ASK')} AS of_gd30
        FROM ticks t ORDER BY t.ts DESC LIMIT ?
    """
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
        for (ts, al30, gd30, source,
             vol_al30, vol_gd30, turn_al30, turn_gd30,
             bi_al30, of_al30, bi_gd30, of_gd30) in cur.fetchall():
            out.append({
                "ts": ts,
                "AL30": float(al30) if al30 is not None else None,
                "GD30": float(gd30) if gd30 is not None else None,
                "source": source,
                "vol_al30": float(vol_al30) if vol_al30 is not None else None,
                "vol_gd30": float(vol_gd30) if vol_gd30 is not None else None,
                "turn_al30": float(turn_al30) if turn_al30 is not None else None,
                "turn_gd30": float(turn_gd30) if turn_gd30 is not None else None,
                "bi_al30": float(bi_al30) if bi_al30 is not None else None,
                "of_al30": float(of_al30) if of_al30 is not None else None,
                "bi_gd30": float(bi_gd30) if bi_gd30 is not None else None,
                "of_gd30": float(of_gd30) if of_gd30 is not None else None,
            })
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
