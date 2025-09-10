# app.py
from __future__ import annotations

import os
import json
import math
import sqlite3
from typing import Any, Dict, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import asyncio

# =========================
# Config & DB
# =========================

class Settings(BaseModel):
    db_path: str = Field(default=os.getenv("DB_PATH", "/app/data/wsbonos.sqlite3"))
    poll_interval_sec: float = 1.0  # WS: polling de DB

settings = Settings()

def _db_connect() -> sqlite3.Connection:
    con = sqlite3.connect(settings.db_path, isolation_level=None, check_same_thread=False)
    con.row_factory = sqlite3.Row
    # flags de performance razonables
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    return con

DB = _db_connect()

# =========================
# Esquema (tolerante)
# =========================

def ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Crea la tabla si no existe. No borra nada si ya está.
    Columnas de puntas/libros se consideran opcionales (pueden existir o no).
    """
    conn.execute("""
    CREATE TABLE IF NOT EXISTS ticks (
        id          INTEGER PRIMARY KEY,
        ts          TEXT NOT NULL,        -- TS tal cual llega del WS (string ISO/epoch string)
        al30        REAL NOT NULL,
        gd30        REAL NOT NULL,
        ratio       REAL,
        source      TEXT,
        vol_al30    REAL,
        vol_gd30    REAL,
        turn_al30   REAL,
        turn_gd30   REAL
        -- Opcionales (si existen en tu DB real, este archivo las devuelve):
        -- bi_al30 REAL, of_al30 REAL, bi_gd30 REAL, of_gd30 REAL,
        -- book_al30 TEXT, book_gd30 TEXT
    );""")
    # índice único por ts para UPSERT
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_ticks_ts ON ticks(ts);")

ensure_schema(DB)

# =========================
# Helpers
# =========================

def parse_price(v: Any) -> float:
    """Robusto para números y strings con ,/. y miles."""
    if v is None:
        return math.nan
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return math.nan
    try:
        # "12345.67"
        if s.replace(".", "", 1).isdigit():
            return float(s)
        # "12345,67"
        if s.replace(",", "", 1).isdigit():
            return float(s.replace(",", "."))
    except Exception:
        pass
    # mixtos "72.339,23" o "78,420.00": el último sep actúa de decimal
    last_dot, last_com = s.rfind("."), s.rfind(",")
    if max(last_dot, last_com) >= 0:
        dec = "." if last_dot > last_com else ","
        thou = "," if dec == "." else "."
        s2 = s.replace(thou, "")
        if dec == ",":
            s2 = s2.replace(",", ".")
        try:
            return float(s2)
        except Exception:
            return math.nan
    try:
        return float(s)
    except Exception:
        return math.nan

# =========================
# Ingesta (a ser llamada por tu feeder)
# =========================

UPSERT_SQL = """
INSERT INTO ticks (ts, al30, gd30, ratio, source, vol_al30, vol_gd30, turn_al30, turn_gd30)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(ts) DO UPDATE SET
  al30       = excluded.al30,
  gd30       = excluded.gd30,
  ratio      = excluded.ratio,
  source     = COALESCE(excluded.source, ticks.source),
  vol_al30   = COALESCE(ticks.vol_al30,0) + COALESCE(excluded.vol_al30,0),
  vol_gd30   = COALESCE(ticks.vol_gd30,0) + COALESCE(excluded.vol_gd30,0),
  turn_al30  = COALESCE(ticks.turn_al30,0) + COALESCE(excluded.turn_al30,0),
  turn_gd30  = COALESCE(ticks.turn_gd30,0) + COALESCE(excluded.turn_gd30,0);
"""

def save_tick(conn: sqlite3.Connection, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Guarda el tick tal cual llega del WS.
    Reglas:
      - NO se convierte ni ajusta la hora: se guarda ts EXACTO (string) que trae el WS.
      - NO se filtra por ventana horaria.
      - NO existe la regla 'gd30 >= al30'.
      - Mapeo directo: al30 <- tick['al30'], gd30 <- tick['gd30'].
      - Se descartan filas con al/gd <= 0 para no violar NOT NULL.
    """
    # 1) ts EXACTO del WS (string)
    ts_key = str(tick.get("ts") or "").strip()
    if not ts_key:
        return None

    # 2) precios sin cruces
    al = parse_price(tick.get("al30"))
    gd = parse_price(tick.get("gd30"))
    if not (al > 0 and gd > 0):
        return None

    # 3) ratio
    try:
        ratio = float(tick["ratio"]) if tick.get("ratio") is not None else (al / gd)
    except Exception:
        ratio = al / gd

    # 4) volúmenes/turnover (opcionales)
    def _f(x):
        try:
            return float(x) if x is not None else None
        except Exception:
            return None

    v_al = _f(tick.get("vol_al30"))
    v_gd = _f(tick.get("vol_gd30"))
    turn_al = (al * v_al) if (v_al is not None) else None
    turn_gd = (gd * v_gd) if (v_gd is not None) else None

    # 5) UPSERT
    conn.execute(
        UPSERT_SQL,
        (ts_key, al, gd, ratio, tick.get("source"), v_al, v_gd, turn_al, turn_gd)
    )

    return {
        "ts": ts_key,
        "al30": al,
        "gd30": gd,
        "ratio": ratio,
        "source": tick.get("source"),
        "vol_al30": v_al,
        "vol_gd30": v_gd,
        "turn_al30": turn_al,
        "turn_gd30": turn_gd,
    }

# =========================
# API
# =========================

app = FastAPI(title="WS Bonos", version="1.1")

# CORS (ajustá orígenes si hace falta)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}

def _columns_present(conn: sqlite3.Connection) -> Set[str]:
    cur = conn.execute("PRAGMA table_info(ticks);")
    return {r["name"] for r in cur.fetchall()}

def _row_to_api(row: sqlite3.Row, present_cols: Set[str]) -> Dict[str, Any]:
    # Campos base
    out = {
        "ts": row["ts"],
        "al30": row["al30"],
        "gd30": row["gd30"],
        "ratio": row["ratio"],
        "source": row["source"],
    }
    # Volúmenes/turnover (si existen)
    for c in ("vol_al30", "vol_gd30", "turn_al30", "turn_gd30"):
        out[c] = row[c] if c in present_cols else None
    # Puntas/libros opcionales (si existen en la DB)
    for c in ("bi_al30", "of_al30", "bi_gd30", "of_gd30"):
        out[c] = row[c] if c in present_cols else None
    for c in ("book_al30", "book_gd30"):
        if c in present_cols:
            try:
                out[c] = json.loads(row[c]) if row[c] is not None else None
            except Exception:
                out[c] = None
        else:
            out[c] = None
    return out

@app.get("/ticks/recent")
def ticks_recent(limit: int = Query(100000, ge=1, le=1_000_000)) -> JSONResponse:
    """
    Devuelve los últimos N ticks.
    SQL: ORDER BY ts DESC LIMIT :limit (más nuevos primero),
    luego se invierte para entregar ASC (antiguo→reciente) por compatibilidad.
    """
    cols = _columns_present(DB)

    # Selección dinámica (incluye opcionales si existen)
    select_cols = ["ts", "al30", "gd30", "ratio", "source"]
    for c in ("vol_al30", "vol_gd30", "turn_al30", "turn_gd30",
              "bi_al30", "of_al30", "bi_gd30", "of_gd30",
              "book_al30", "book_gd30"):
        if c in cols:
            select_cols.append(c)

    sql = f"SELECT {', '.join(select_cols)} FROM ticks ORDER BY ts DESC LIMIT ?;"
    rows = DB.execute(sql, (limit,)).fetchall()
    # invertimos para ASC (inicio→fin)
    rows = list(reversed(rows))
    data = [_row_to_api(r, cols) for r in rows]

    resp = JSONResponse(content=data)
    resp.headers["Cache-Control"] = "no-store"
    return resp

# =========================
# WebSocket (stream "realtime" por polling DB)
# =========================

async def stream_new_ticks(ws: WebSocket, poll_interval: float | None = None) -> None:
    """
    Polea la DB y envía nuevos registros (ts > último enviado).
    """
    await ws.accept()
    poll = poll_interval or settings.poll_interval_sec

    cols = _columns_present(DB)
    last_ts: Optional[str] = None

    try:
        while True:
            if last_ts is None:
                last = DB.execute("SELECT ts FROM ticks ORDER BY ts DESC LIMIT 1;").fetchone()
                last_ts = last["ts"] if last else None

            await asyncio.sleep(poll)

            if last_ts is None:
                continue

            new_rows = DB.execute(
                "SELECT * FROM ticks WHERE ts > ? ORDER BY ts ASC LIMIT 500;",
                (last_ts,)
            ).fetchall()

            if not new_rows:
                continue

            for r in new_rows:
                payload = _row_to_api(r, cols)
                await ws.send_json(payload)
                last_ts = r["ts"]

    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await ws.close(code=1011)
        except Exception:
            pass

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await stream_new_ticks(ws)

# =========================
# (Opcional) ejecutar: uvicorn app:app --host 0.0.0.0 --port 8000
# =========================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
