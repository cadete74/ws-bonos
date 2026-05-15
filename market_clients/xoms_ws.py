from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Callable, Awaitable

import httpx
import websockets
import websockets.exceptions

logger = logging.getLogger(__name__)

# Símbolos XOMS completos que se suscriben al iniciar la sesión WS.
WS_SYMBOLS: list[str] = [
    "MERV - XMEV - AL30 - 24hs",
    "MERV - XMEV - GD30 - 24hs",
]

MARKET_ID = "ROFX"

# Delays de reconexión en segundos: 1, 2, 4, 8, 16, luego cap en 30.
_BACKOFF_DELAYS: list[int] = [1, 2, 4, 8, 16, 30]

# Máximo de fallos consecutivos antes de salir con código no-cero.
_MAX_CONSECUTIVE_FAILURES = 5


@dataclass(frozen=True)
class MdMessage:
    timestamp_ms: int
    symbol: str                       # forma completa XOMS
    base: str                         # "AL30" | "GD30"
    last: float | None
    bid: tuple[float, float] | None   # (precio, tamaño)
    ask: tuple[float, float] | None   # (precio, tamaño)
    volume: float | None              # NV: nominales operados acumulados del día
    turnover: float | None            # EV: monto operado acumulado ($)


def _extract_base_symbol(sym: str) -> str | None:
    """
    Extrae 'AL30' o 'GD30' de la forma completa XOMS, por ejemplo:
    'MERV - XMEV - AL30 - 24hs' -> 'AL30'.
    Escrito inline porque el regex de veta.py no manejaba variantes como AL30D.
    """
    u = sym.strip().upper()
    if u in ("AL30", "GD30"):
        return u
    parts = re.split(r"\s*-\s*", u)
    for p in parts:
        p = p.strip()
        if p in ("AL30", "GD30"):
            return p
        for base in ("AL30", "GD30"):
            if p.startswith(base):
                return base
    m = re.search(r"\b(AL30|GD30)", u)
    if m:
        return m.group(1)
    return None


def _parse_md_message(raw: dict) -> MdMessage | None:
    """
    Convierte un mensaje JSON de tipo 'Md' a MdMessage.
    Devuelve None si el mensaje no es de tipo 'Md' o carece de campos mínimos.
    Loguea WARNING en campos opcionales ausentes.
    """
    if raw.get("type") != "Md":
        return None

    ts_ms: int | None = raw.get("timestamp")
    instrument_id = raw.get("instrumentId") or {}
    symbol: str = instrument_id.get("symbol") or ""
    base = _extract_base_symbol(symbol)

    if ts_ms is None or not symbol or not base:
        logger.warning("Md message con campos mínimos ausentes: %s", raw)
        return None

    md = raw.get("marketData") or {}

    # LA: last trade — opcional
    la = md.get("LA")
    last: float | None = None
    if isinstance(la, dict):
        v = la.get("price")
        if isinstance(v, (int, float)):
            last = float(v)
    elif la is not None:
        logger.warning("Campo LA con formato inesperado en Md: %s", la)

    if last is None:
        logger.warning("Campo LA ausente en Md para %s (ts=%s)", symbol, ts_ms)

    # BI: bids — opcional
    bid: tuple[float, float] | None = None
    bi = md.get("BI")
    if isinstance(bi, list) and bi:
        entry = bi[0]
        p = entry.get("price")
        s = entry.get("size")
        if isinstance(p, (int, float)) and isinstance(s, (int, float)):
            bid = (float(p), float(s))

    # OF: offers — opcional
    ask: tuple[float, float] | None = None
    of = md.get("OF")
    if isinstance(of, list) and of:
        entry = of[0]
        p = entry.get("price")
        s = entry.get("size")
        if isinstance(p, (int, float)) and isinstance(s, (int, float)):
            ask = (float(p), float(s))

    # NV: volumen nominal operado acumulado del día — número directo.
    # (En Eco, TV viene siempre null; NV es la fuente válida de volumen.)
    volume: float | None = None
    nv = md.get("NV")
    if isinstance(nv, (int, float)):
        volume = float(nv)

    # EV: monto efectivo operado acumulado ($) — número directo.
    turnover: float | None = None
    ev = md.get("EV")
    if isinstance(ev, (int, float)):
        turnover = float(ev)

    return MdMessage(
        timestamp_ms=int(ts_ms),
        symbol=symbol,
        base=base,
        last=last,
        bid=bid,
        ask=ask,
        volume=volume,
        turnover=turnover,
    )


class XomsWsClient:
    """
    Cliente WebSocket XOMS para Eco Valores.

    Encapsula login REST, handshake WS con X-Auth-Token en header,
    suscripción y reconexión con backoff exponencial.
    """

    def __init__(
        self,
        base_url: str,
        ws_url: str,
        user: str,
        password: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._ws_url = ws_url.rstrip("/")
        self._user = user
        self._password = password
        self._ws_conn: websockets.ClientConnection | None = None
        self._closed = False

    async def _login(self) -> str:
        """
        POST /auth/getToken con X-Username / X-Password.
        Devuelve el token del header X-Auth-Token.
        Lanza RuntimeError (el caller debe salir con código no-cero) si el header está ausente.
        """
        url = f"{self._base_url}/auth/getToken"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "X-Username": self._user,
                    "X-Password": self._password,
                },
            )

        token = resp.headers.get("X-Auth-Token")
        if not token:
            body = resp.text[:500]
            logger.critical(
                "Login fallido: X-Auth-Token ausente en respuesta. "
                "status=%s body=%s",
                resp.status_code,
                body,
            )
            raise RuntimeError(f"Login XOMS fallido — no X-Auth-Token (status={resp.status_code})")

        logger.info("Login XOMS OK (token obtenido)")
        return token

    async def stream(
        self,
        on_md: Callable[[MdMessage], Awaitable[None]],
    ) -> None:
        """
        Bucle principal: login → connect WS → subscribe → procesar mensajes.
        Reconecta con backoff exponencial ante cualquier desconexión.
        Sale con sys.exit(1) tras _MAX_CONSECUTIVE_FAILURES fallos consecutivos.
        """
        import sys

        consecutive_failures = 0
        consecutive_subscribe_errors = 0

        while not self._closed:
            if consecutive_failures > 0:
                delay = _BACKOFF_DELAYS[min(consecutive_failures - 1, len(_BACKOFF_DELAYS) - 1)]
                logger.info(
                    "Reconexión #%d — esperando %ds antes de reintentar...",
                    consecutive_failures,
                    delay,
                )
                await asyncio.sleep(delay)

            # Re-login en cada intento de reconexión (el token puede haber expirado).
            try:
                token = await self._login()
            except RuntimeError:
                consecutive_failures += 1
                logger.error(
                    "Fallo de login (#%d/%d consecutivos)",
                    consecutive_failures,
                    _MAX_CONSECUTIVE_FAILURES,
                )
                if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    logger.critical(
                        "Alcanzado el máximo de fallos consecutivos (%d). Saliendo.",
                        _MAX_CONSECUTIVE_FAILURES,
                    )
                    sys.exit(1)
                continue

            # Handshake WS: token en header, NUNCA en query string.
            try:
                async with websockets.connect(
                    self._ws_url,
                    additional_headers={"X-Auth-Token": token},
                ) as ws:
                    self._ws_conn = ws
                    logger.info("WebSocket conectado a %s", self._ws_url)

                    # Suscripción inmediata al conectar.
                    subscribe_msg = {
                        "type": "smd",
                        "level": 1,
                        "entries": ["BI", "OF", "LA", "NV", "EV"],
                        "products": [
                            {"symbol": sym, "marketId": MARKET_ID}
                            for sym in WS_SYMBOLS
                        ],
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info("Suscripción enviada para %s", WS_SYMBOLS)

                    # Verificar que el servidor no rechazó la suscripción.
                    # El primer mensaje de vuelta puede ser un error o un Md.
                    first_raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    first = json.loads(first_raw)
                    if first.get("status") == "ERROR":
                        consecutive_failures += 1
                        consecutive_subscribe_errors += 1
                        logger.critical(
                            "Error de suscripción del servidor (#%d subscribe / #%d total): %s",
                            consecutive_subscribe_errors,
                            consecutive_failures,
                            first,
                        )
                        if consecutive_subscribe_errors >= 3:
                            logger.critical(
                                "3 errores de suscripción consecutivos — símbolo inválido o acceso denegado. Saliendo.",
                            )
                            sys.exit(1)
                        if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                            logger.critical(
                                "Máximo de fallos consecutivos (%d). Saliendo.",
                                _MAX_CONSECUTIVE_FAILURES,
                            )
                            sys.exit(1)
                        continue

                    # El primer mensaje no fue error; procesarlo si es Md.
                    msg = _parse_md_message(first)
                    if msg is not None:
                        await on_md(msg)

                    # Suscripción exitosa — resetear ambos contadores.
                    consecutive_failures = 0
                    consecutive_subscribe_errors = 0
                    logger.info("Suscripción confirmada. Procesando mensajes...")

                    # Bucle principal de mensajes.
                    async for raw_str in ws:
                        if self._closed:
                            break
                        try:
                            data = json.loads(raw_str)
                        except json.JSONDecodeError as exc:
                            logger.warning("JSON inválido recibido: %s — %s", exc, raw_str[:200])
                            continue

                        msg = _parse_md_message(data)
                        if msg is not None:
                            await on_md(msg)

            except websockets.exceptions.ConnectionClosed as exc:
                consecutive_failures += 1
                logger.warning(
                    "WS cerrado (#%d/%d consecutivos): %s",
                    consecutive_failures,
                    _MAX_CONSECUTIVE_FAILURES,
                    exc,
                )
            except (OSError, asyncio.TimeoutError) as exc:
                consecutive_failures += 1
                logger.warning(
                    "Error de red/timeout (#%d/%d consecutivos): %s",
                    consecutive_failures,
                    _MAX_CONSECUTIVE_FAILURES,
                    exc,
                )
            finally:
                self._ws_conn = None

            if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                logger.critical(
                    "Alcanzado el máximo de fallos consecutivos (%d). Saliendo.",
                    _MAX_CONSECUTIVE_FAILURES,
                )
                sys.exit(1)

    async def aclose(self) -> None:
        """
        Cierra el WebSocket limpiamente (envía close frame).
        Llamado por el runner en SIGTERM/SIGINT.
        """
        self._closed = True
        if self._ws_conn is not None:
            try:
                await self._ws_conn.close()
            except Exception:
                pass
            self._ws_conn = None
