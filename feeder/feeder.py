import os
import json
import time
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ------------------------------
# Config por ENV (no tocar código)
# ------------------------------
DB_PATH            = os.getenv("DB_PATH", "/app/data/wsbonos.sqlite3")
FEED_URL           = os.getenv("FEED_URL", "").strip()                 # <-- PONÉ TU URL AQUÍ (por ENV)
FEED_METHOD        = os.getenv("FEED_METHOD", "GET").upper()
FEED_HEADERS_JSON  = os.getenv("FEED_HEADERS", "").strip()            # ej: {"Authorization":"Bearer XYZ"}
FEEDER_SLEEP_SEC   = float(os.getenv("FEEDER_SLEEP_SEC", "5.0"))
FEED_TIMEOUT_SEC   = float(os.getenv("FEED_TIMEOUT_SEC", "5.0"))
FEED_SOURCE        = os.getenv("FEED_SOURCE", "real")

# Mapeo de claves del JSON (acepta rutas con puntos, p.ej. "data.last.al30")
PATH_AL30     = os.getenv("FEED_AL30", "al30")
PATH_GD30     = os.getenv("FEED_GD30", "gd30")
PATH_TS       = os.getenv("FEED_TS", "ts")                 # opcional; si falta, se usa now UTC
PATH_VOL_AL30 = os.getenv("FEED_VOL_AL30", "vol_al30")     # opcional
PATH_VOL_GD30 = os.getenv("FEED_VOL_GD30", "vol_gd30")     # opcional

# ------------------------------
# Utilidades
# ------------------------------
def iso_utc(ts_any=None) -> str:
    """Normaliza un timestamp a ISO UTC (+00:00). Acepta ISO, epoch s/ms, datetime."""
    if ts_any is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    if isinstance(ts_any, (int, float)):
        x = float(ts_any)
        if x >= 1e12:
            x /= 1000.0
        return datetime.fromtimestamp(x, tz=timezone.utc).replace(microsecond=0).isoformat()

    if isinstance(ts_any, datetime):
        dt = ts_any.astimezone(timezone.utc) if ts_any.tzinfo else ts_any.replace(tzinfo=timezone.utc)
        return dt.replace(microsecond=0).isoformat()

    s = str(ts_any).strip()
    if not s:
        return iso_utc()
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        return dt.replace(microsecond=0).isoformat()
    except Exception:
        # si vino "1694275200" o "1694275200123" como string
        try:
            f = float(s)
            return iso_utc(f)
        except Exception:
            return iso_utc()

def parse_float(v):
    """Convierte a float tolerante (strings con ,/.) o devuelve None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s == "":
        return None
    # intentos rápidos
    try:
        if s.replace(".", "", 1).isdigit():
            return float(s)
        if s.replace(",", "", 1).isdigit():
            return float(s.replace(",", "."))
    except Exception:
        pass
    # mezcla miles/decimales
    last_dot, last_com = s.rfind("."), s.rfind(",")
    if max(last_dot, last_com) >= 0:
        dec = "." if last_dot > last_com else ","
        thou = "," if dec == "." else "."
        t = s.replace(thou, "")
        if dec == ",":
            t = t.replace(",", ".")
        try:
            return float(t)
        except Exception:
            return None
    try:
        return float(s)
    except Exception:
        return None

def get_in(obj, dotted_path, default=None):
    """Obtiene obj['a']['b']['c'] dado 'a.b.c' sin explotar si falta."""
    if not dotted_path:
        return default
    cur = obj
    for part in dotted_path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur

def fetch_json(url, headers=None, method="GET", timeout=5.0):
    req = urllib.request.Request(url=url, method=method)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # intenta parsear como JSON
        return json.loads(resp.read().decode("utf-8", errors="replace"))

# ------------------------------
# Persistencia en SQLite
# ------------------------------
UPSERT_SQL = """
INSERT OR REPLACE INTO ticks
 (ts, al30, gd30, ratio, source, vol_al30, vol_gd30, turn_al30, turn_gd30)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

def save_tick_sqlite(tick: dict) -> None:
    ts = iso_utc(tick.get("ts"))
    al = parse_float(tick.get("al30"))
    gd = parse_float(tick.get("gd30"))
    if not (al and gd) or al <= 0 or gd <= 0:
        return
    ratio = tick.get("ratio")
    r = parse_float(ratio) if ratio is not None else (al / gd)

    v_al = parse_float(tick.get("vol_al30"))
    v_gd = parse_float(tick.get("vol_gd30"))
    t_al = parse_float(tick.get("turn_al30")) if tick.get("turn_al30") is not None else (al * v_al if isinstance(v_al, (int, float, float)) and v_al is not None else None)
    t_gd = parse_float(tick.get("turn_gd30")) if tick.get("turn_gd30") is not None else (gd * v_gd if isinstance(v_gd, (int, float, float)) and v_gd is not None else None)

    source = str(tick.get("source") or FEED_SOURCE)

    with sqlite3.connect(DB_PATH) as con:
        con.execute(UPSERT_SQL, (ts, al, gd, r, source, v_al, v_gd, t_al, t_gd))
        con.commit()

# ------------------------------
# Loop: leer feed y grabar
# ------------------------------
def main():
    print(f"[feeder] DB: {DB_PATH}", flush=True)
    if not FEED_URL:
        print("[feeder][ERROR] FEED_URL vacío (definilo por ENV). No se insertará nada.", flush=True)

    # headers opcionales
    headers = None
    if FEED_HEADERS_JSON:
        try:
            headers = json.loads(FEED_HEADERS_JSON)
        except Exception as e:
            print(f"[feeder][WARN] FEED_HEADERS inválido ({e}). Ignorando headers.", flush=True)

    while True:
        try:
            if FEED_URL:
                payload = fetch_json(FEED_URL, headers=headers, method=FEED_METHOD, timeout=FEED_TIMEOUT_SEC)

                al = parse_float(get_in(payload, PATH_AL30, get_in(payload, PATH_AL30.lower(), None)))
                gd = parse_float(get_in(payload, PATH_GD30, get_in(payload, PATH_GD30.lower(), None)))
                ts_raw = get_in(payload, PATH_TS, None)
                vol_al = parse_float(get_in(payload, PATH_VOL_AL30, None))
                vol_gd = parse_float(get_in(payload, PATH_VOL_GD30, None))

                tick = {
                    "ts": iso_utc(ts_raw) if ts_raw is not None else iso_utc(),
                    "al30": al,
                    "gd30": gd,
                    "vol_al30": vol_al,
                    "vol_gd30": vol_gd,
                    "source": FEED_SOURCE,
                }
                save_tick_sqlite(tick)
                if al and gd:
                    print(f"[feeder] {tick['ts']} al30={al} gd30={gd} volAL={vol_al} volGD={vol_gd}", flush=True)
                else:
                    print(f"[feeder][WARN] Tick ignorado (al30/gd30 inválidos). Payload parcial: {str(payload)[:200]}", flush=True)

            else:
                # Sin FEED_URL: no hacer nada, solo avisar cada cierto tiempo
                print("[feeder] FEED_URL no configurado. Esperando...", flush=True)

        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            print(f"[feeder][HTTP] {e}", flush=True)
        except Exception as e:
            print(f"[feeder][ERROR] {e}", flush=True)

        time.sleep(FEEDER_SLEEP_SEC)

if __name__ == "__main__":
    main()
