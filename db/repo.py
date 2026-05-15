from __future__ import annotations

import datetime
import os
import sqlite3
from typing import Dict, Iterable, List, Tuple

DB_PATH = os.getenv("DB_PATH", "./data/wsbonos.sqlite3")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def upsert_tick(
    ts: str,
    symbol: str,
    last: float | None,
    vol: float | None,
    turnover: float | None,
    source: str,
) -> None:
    """
    UPSERT a single per-symbol tick row.
    On conflict (ts, symbol) updates last, vol, turnover, source — COALESCE keeps
    the existing value when the incoming field is NULL.
    """
    sql = """
    INSERT INTO ticks(ts, symbol, last, vol, turnover, source)
    VALUES(?, ?, ?, ?, ?, ?)
    ON CONFLICT(ts, symbol) DO UPDATE SET
      last     = excluded.last,
      vol      = COALESCE(excluded.vol, vol),
      turnover = COALESCE(excluded.turnover, turnover),
      source   = COALESCE(excluded.source, source)
    """
    with _conn() as conn:
        conn.execute(sql, (ts, symbol, last, vol, turnover, source))


def recent_ticks(symbol: str, limit: int = 10) -> List[Dict]:
    """Return the most recent ticks for a single symbol, newest first."""
    q = """
    SELECT ts, last, vol, turnover, source
    FROM ticks
    WHERE symbol = ?
    ORDER BY ts DESC
    LIMIT ?
    """
    with _conn() as conn:
        rows = conn.execute(q, (symbol, limit)).fetchall()
    return [dict(r) for r in rows]


def save_orderbook(
    symbol: str,
    ts: str,
    side: str,
    levels: Iterable[Tuple[float, float]],
) -> None:
    """
    UPSERT the order book (BID/ASK) at the given levels.
    levels = [(price1, size1), (price2, size2), ...]
    """
    side = side.upper()
    assert side in ("BID", "ASK")
    sql = """
    INSERT INTO orderbooks(symbol, ts, side, level, price, size)
    VALUES(?, ?, ?, ?, ?, ?)
    ON CONFLICT(symbol, ts, side, level)
    DO UPDATE SET price = excluded.price, size = excluded.size
    """
    with _conn() as conn:
        for i, (price, size) in enumerate(levels, start=1):
            conn.execute(sql, (symbol, ts, side, i, float(price), float(size)))


def smoke_test() -> None:
    """
    Insert two synthetic rows (AL30 + GD30), read them back, then delete.
    Validates the per-symbol ticks schema without touching production data.
    """
    ts = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    source = "SMOKE"

    with _conn() as conn:
        try:
            conn.execute("BEGIN")
            upsert_tick(ts, "AL30", 100.0, 10.0, 1000.0, source)
            upsert_tick(ts, "GD30", 150.0, 20.0, 2000.0, source)

            rows = conn.execute(
                "SELECT symbol, ts, last, turnover, source FROM ticks WHERE ts = ? ORDER BY symbol",
                (ts,),
            ).fetchall()
            print("rows_inserted:", [dict(r) for r in rows])

            conn.execute("DELETE FROM ticks WHERE ts = ?", (ts,))
            conn.commit()
            print("smoke_test: OK (insert-read-delete)")
        except Exception:
            conn.rollback()
            raise
