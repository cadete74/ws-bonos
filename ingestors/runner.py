from __future__ import annotations
import os
import argparse
import datetime
from typing import Dict, Tuple, Optional

from ingestors.veta_client import VetaClient
from db.repo import _upsert_both_symbols, save_orderbook

BASES = ("AL30", "GD30")

def main() -> int:
    parser = argparse.ArgumentParser(description="WS Bonos ingestor runner (one-shot)")
    parser.add_argument("--once", action="store_true", help="ejecuta una pasada y sale (default)")
    args = parser.parse_args()

    # DB por defecto en local si no viene por env
    os.environ.setdefault("DB_PATH", "./data/wsbonos.sqlite3")

    vc = VetaClient()
    vc.login()  # establece cookie/token

    # Resolver símbolos 24hs + marketId vía API (evita usar _get_json directo)
    mapping: Dict[str, Tuple[str, str]] = {}
    for base in BASES:
        sym, mid = vc.resolve_symbol_24hs(base)
        mapping[base] = (sym, mid)

    # Obtener LA/BI/OF para cada base
    al30_sym, al30_mid = mapping["AL30"]
    gd30_sym,  gd30_mid = mapping["GD30"]

    al30 = vc.fetch_la_bi_of(al30_sym, al30_mid)  # {'last': float|None, 'bid':(p,sz)|None, 'ask':(p,sz)|None}
    gd30  = vc.fetch_la_bi_of(gd30_sym,  gd30_mid)

    if al30.get("last") is None or gd30.get("last") is None:
        raise SystemExit("No se obtuvo LA para AL30/GD30 (revisar horario/mercado o entries).")

    # TS (por ahora: reloj local en UTC; más adelante usaremos ts del proveedor cuando esté disponible)
    ts = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    # Guardar tick combinado (schema legacy: al30 + gd30 en misma fila por ts)
    _upsert_both_symbols(ts, float(al30["last"]), float(gd30["last"]), source="VETA")

    # Guardar top-of-book (nivel 1) si viene
    if al30.get("bid"): save_orderbook("AL30", ts, "BID", [al30["bid"]])  # type: ignore[arg-type]
    if al30.get("ask"): save_orderbook("AL30", ts, "ASK", [al30["ask"]])  # type: ignore[arg-type]
    if gd30.get("bid"): save_orderbook("GD30", ts, "BID", [gd30["bid"]])  # type: ignore[arg-type]
    if gd30.get("ask"): save_orderbook("GD30", ts, "ASK", [gd30["ask"]])  # type: ignore[arg-type]

    print(f"runner: inserted tick+orderbook at {ts} | "
          f"AL30 last={al30['last']} ({al30_sym}/{al30_mid}), "
          f"GD30 last={gd30['last']} ({gd30_sym}/{gd30_mid})")

    # one-shot por defecto
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
