from __future__ import annotations

import asyncio
import datetime
import logging
import os
import signal
import sys

from market_clients.xoms_ws import MdMessage, XomsWsClient
from db.repo import upsert_tick, save_orderbook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("ingestors.runner")


def _ms_to_iso(ts_ms: int) -> str:
    """Convierte epoch-ms a ISO 8601 UTC con precisión de segundos."""
    dt = datetime.datetime.utcfromtimestamp(ts_ms / 1000.0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


async def persist_md(msg: MdMessage) -> None:
    """
    Persist a single Md message as an independent per-symbol row.
    Each symbol writes immediately — no partner-symbol guard.
    """
    ts_iso = _ms_to_iso(msg.timestamp_ms)
    upsert_tick(ts_iso, msg.base, msg.last, msg.volume, msg.turnover, "XOMS")

    if msg.bid is not None:
        save_orderbook(msg.base, ts_iso, "BID", [msg.bid])
    if msg.ask is not None:
        save_orderbook(msg.base, ts_iso, "ASK", [msg.ask])


async def main() -> None:
    if "--once" in sys.argv:
        logger.error("--once ya no está soportado. El ingestor corre como proceso persistente.")
        sys.exit(1)

    os.environ.setdefault("DB_PATH", "./data/wsbonos.sqlite3")

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

    stream_task: asyncio.Task | None = None

    def _shutdown(signame: str) -> None:
        logger.info("Señal %s recibida — cerrando...", signame)
        if stream_task is not None and not stream_task.done():
            stream_task.cancel()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, lambda: _shutdown("SIGTERM"))
    loop.add_signal_handler(signal.SIGINT, lambda: _shutdown("SIGINT"))

    async def _on_md(msg: MdMessage) -> None:
        await persist_md(msg)

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
