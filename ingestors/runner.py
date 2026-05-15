from __future__ import annotations

import asyncio
import datetime
import logging
import os
import signal
import sys
from typing import Optional

from market_clients.xoms_ws import MdMessage, XomsWsClient
from db.repo import _upsert_both_symbols, save_orderbook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("ingestors.runner")

# Por símbolo base: (last, bid, ask, vol, turn) — None hasta que llegue el primer Md.
_Cache = dict[
    str,
    tuple[
        Optional[float], Optional[float], Optional[float],
        Optional[float], Optional[float],
    ],
]
_EMPTY = (None, None, None, None, None)


def _ms_to_iso(ts_ms: int) -> str:
    """Convierte epoch-ms a ISO 8601 UTC con precisión de segundos."""
    dt = datetime.datetime.utcfromtimestamp(ts_ms / 1000.0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


async def persist_md(msg: MdMessage, cache: _Cache) -> None:
    """
    Actualiza la cache por símbolo y persiste en ticks + orderbooks.

    Solo escribe en ticks cuando ambos símbolos (AL30 y GD30) tienen
    al menos un last conocido, para respetar la restricción NOT NULL del schema.
    """
    ts_iso = _ms_to_iso(msg.timestamp_ms)
    base = msg.base

    # Recuperar estado previo del cache (o defaults vacíos).
    prev_last, prev_bid_px, prev_ask_px, prev_vol, prev_turn = cache.get(base, _EMPTY)

    new_last = msg.last if msg.last is not None else prev_last
    new_bid_px = msg.bid[0] if msg.bid is not None else prev_bid_px
    new_ask_px = msg.ask[0] if msg.ask is not None else prev_ask_px
    new_vol = msg.volume if msg.volume is not None else prev_vol
    new_turn = msg.turnover if msg.turnover is not None else prev_turn

    cache[base] = (new_last, new_bid_px, new_ask_px, new_vol, new_turn)

    # UPSERT ticks: solo cuando ambas piernas tienen last conocido.
    al30_last, _, _, al30_vol, al30_turn = cache.get("AL30", _EMPTY)
    gd30_last, _, _, gd30_vol, gd30_turn = cache.get("GD30", _EMPTY)

    if al30_last is not None and gd30_last is not None:
        _upsert_both_symbols(
            ts_iso, al30_last, gd30_last, source="XOMS",
            vol_al30=al30_vol, vol_gd30=gd30_vol,
            turn_al30=al30_turn, turn_gd30=gd30_turn,
        )

    # Persistir orderbook si hay bid/ask en este mensaje.
    if msg.bid is not None:
        save_orderbook(base, ts_iso, "BID", [msg.bid])
    if msg.ask is not None:
        save_orderbook(base, ts_iso, "ASK", [msg.ask])


async def main() -> None:
    # Rechazar --once explícitamente (ya no tiene soporte).
    if "--once" in sys.argv:
        logger.error("--once ya no está soportado. El ingestor corre como proceso persistente.")
        sys.exit(1)

    os.environ.setdefault("DB_PATH", "./data/wsbonos.sqlite3")

    # Leer credenciales — fallo rápido si no están configuradas.
    base_url = os.getenv("XOMS_BASE_URL", "")
    ws_url = os.getenv("XOMS_WS_URL", "")
    user = os.getenv("XOMS_USER", "")
    password = os.getenv("XOMS_PASS", "")

    missing = [k for k, v in {
        "XOMS_BASE_URL": base_url,
        "XOMS_WS_URL": ws_url,
        "XOMS_USER": user,
        "XOMS_PASS": password,
    }.items() if not v]

    if missing:
        logger.critical("Variables de entorno faltantes: %s", ", ".join(missing))
        sys.exit(1)

    client = XomsWsClient(
        base_url=base_url,
        ws_url=ws_url,
        user=user,
        password=password,
    )

    # Cache de últimos valores por símbolo base.
    cache: _Cache = {}

    # Tarea de streaming — se cancela en shutdown.
    stream_task: asyncio.Task | None = None

    def _shutdown(signame: str) -> None:
        logger.info("Señal %s recibida — cerrando...", signame)
        if stream_task is not None and not stream_task.done():
            stream_task.cancel()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, lambda: _shutdown("SIGTERM"))
    loop.add_signal_handler(signal.SIGINT, lambda: _shutdown("SIGINT"))

    async def _on_md(msg: MdMessage) -> None:
        await persist_md(msg, cache)

    stream_task = asyncio.create_task(client.stream(_on_md))

    try:
        await stream_task
    except asyncio.CancelledError:
        logger.info("Stream cancelado — cerrando WebSocket limpiamente...")
    finally:
        await client.aclose()
        logger.info("Runner finalizado con éxito.")


if __name__ == "__main__":
    asyncio.run(main())
