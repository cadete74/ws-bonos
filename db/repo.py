from __future__ import annotations
import os, sqlite3, datetime
from typing import List, Dict, Iterable, Tuple, Optional

DB_PATH = os.getenv("DB_PATH", "./data/wsbonos.sqlite3")

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def recent_ticks(symbol: str, limit: int = 10) -> List[Dict]:
    """
    Lee ticks normalizados desde la vista ticks_rows (no toca tablas).
    """
    q = """
    SELECT symbol, ts, last, turnover, source
    FROM ticks_rows
    WHERE symbol = ?
    ORDER BY ts DESC
    LIMIT ?
    """
    with _conn() as conn:
        rows = conn.execute(q, (symbol, limit)).fetchall()
    return [dict(r) for r in rows]

def save_orderbook(symbol: str, ts: str, side: str, levels: Iterable[Tuple[float, float]]) -> None:
    """
    UPSERT del libro (BID/ASK) en niveles 1..N.
    levels = [(price1, size1), (price2, size2), ...]
    """
    side = side.upper()
    assert side in ("BID", "ASK")
    sql = """
    INSERT INTO orderbooks(symbol, ts, side, level, price, size)
    VALUES(?,?,?,?,?,?)
    ON CONFLICT(symbol, ts, side, level)
    DO UPDATE SET price=excluded.price, size=excluded.size
    """
    with _conn() as conn:
        for i, (price, size) in enumerate(levels, start=1):
            conn.execute(sql, (symbol, ts, side, i, float(price), float(size)))

def _upsert_both_symbols(ts: str,
                         al30: float, gd30: float,
                         source: str = "TEST",
                         ratio: Optional[float] = None,
                         vol_al30: Optional[float] = None,
                         vol_gd30: Optional[float] = None,
                         turn_al30: Optional[float] = None,
                         turn_gd30: Optional[float] = None) -> None:
    """
    Helper *solo para pruebas*: la tabla ticks actual exige al30 y gd30 NOT NULL
    y UNIQUE(ts). Hacemos UPSERT con ambos símbolos en la misma fila.
    """
    sql = """
    INSERT INTO ticks(ts, al30, gd30, ratio, source, vol_al30, vol_gd30, turn_al30, turn_gd30)
    VALUES(?,?,?,?,?,?,?,?,?)
    ON CONFLICT(ts)
    DO UPDATE SET
      al30=excluded.al30,
      gd30=excluded.gd30,
      ratio=COALESCE(excluded.ratio, ratio),
      source=COALESCE(excluded.source, source),
      vol_al30=COALESCE(excluded.vol_al30, vol_al30),
      vol_gd30=COALESCE(excluded.vol_gd30, vol_gd30),
      turn_al30=COALESCE(excluded.turn_al30, turn_al30),
      turn_gd30=COALESCE(excluded.turn_gd30, turn_gd30)
    """
    with _conn() as conn:
        conn.execute(sql, (ts, al30, gd30, ratio, source, vol_al30, vol_gd30, turn_al30, turn_gd30))

def smoke_test() -> None:
    """
    Inserta una fila sintética (al30+gd30) y la borra antes de terminar.
    Verifica lectura desde la vista ticks_rows.
    """
    ts = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    # Datos de prueba
    al30, gd30 = 100.0, 150.0
    source = "SMOKE"

    with _conn() as conn:
        try:
            conn.execute("BEGIN")
            _upsert_both_symbols(ts, al30, gd30, source=source, ratio=None,
                                 vol_al30=10.0, vol_gd30=20.0, turn_al30=1000.0, turn_gd30=2000.0)

            # Lee dos filas normalizadas (AL30 y GD30) para el mismo ts
            rows = conn.execute(
                "SELECT symbol, ts, last, turnover, source FROM ticks_rows WHERE ts = ? ORDER BY symbol",
                (ts,)
            ).fetchall()
            print("rows_inserted:", [dict(r) for r in rows])

            # Limpieza: no dejamos datos de prueba
            conn.execute("DELETE FROM ticks WHERE ts = ?", (ts,))
            conn.commit()
            print("smoke_test: OK (insert-read-delete)")
        except Exception as e:
            conn.rollback()
            raise
