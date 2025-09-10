from typing import Optional, Any, Tuple, List, Dict
import httpx
import asyncio
import re


class VetaClient:
    """
    Cliente Veta / Trading API.

    Requiere en `settings`:
      - veta_base_url  (host raíz, SIN '/rest', ej: https://api.veta.xoms.com.ar)
      - veta_user, veta_pass
      - veta_timeout, veta_user_agent
    """

    # ------------- INIT / CLOSE -------------

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=self.settings.veta_base_url,  # raíz, sin /rest
            timeout=self.settings.veta_timeout,
            follow_redirects=True,
            headers={
                "User-Agent": self.settings.veta_user_agent,
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
            verify=True,
        )
        self.auth_token: Optional[str] = None
        self._logged_root: bool = False
        self._logged_rest: bool = False

        # cache de instrumentos (para obtener marketId/símbolos exactos)
        self._instrument_cache_loaded: bool = False
        self._symbols_index: Dict[str, List[Dict[str, str]]] = {}

    async def aclose(self) -> None:
        await self.client.aclose()

    # ------------- LOGIN HELPERS -------------

    def _have_root_cookie(self) -> bool:
        try:
            jar = self.client.cookies.jar
        except Exception:
            return False
        for c in jar:
            path = getattr(c, "path", None) or ""
            name = getattr(c, "name", "")
            if path == "/" and name:
                return True
        return False

    async def _login_headers(self, path: str) -> bool:
        headers = {
            "X-Username": self.settings.veta_user or "",
            "X-Password": self.settings.veta_pass or "",
            "Content-Type": "application/json",
        }
        try:
            r = await self.client.post(path, headers=headers, content=b"")
        except httpx.HTTPError:
            return False

        token = r.headers.get("X-Auth-Token")
        if token:
            self.auth_token = token
            self.client.headers["X-Auth-Token"] = token

        ok_status = r.status_code in (200, 204, 302)
        has_cookie = bool(self.client.cookies)
        has_token = self.auth_token is not None
        return ok_status and (has_cookie or has_token)

    async def _login_form_root(self) -> bool:
        user = self.settings.veta_user or ""
        pwd = self.settings.veta_pass or ""

        candidates = [
            {"j_username": user, "j_password": pwd},
            {"username": user, "password": pwd},
        ]
        for data in candidates:
            try:
                r = await self.client.post(
                    "/j_spring_security_check",
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if r.status_code in (200, 302) and self._have_root_cookie():
                    return True
            except httpx.HTTPError:
                continue
        return self._have_root_cookie()

    async def login(self) -> bool:
        self._logged_root = await self._login_headers("/login")
        self._logged_rest = await self._login_headers("/rest/login")
        form_ok = await self._login_form_root()
        self._logged_root = self._logged_root or form_ok
        return self._logged_root or self._logged_rest

    # ------------- HTTP UTILS -------------

    async def _get_json(self, path: str, params: Optional[Dict[str, str]] = None) -> Tuple[Optional[object], int]:
        try:
            r = await self.client.get(path, params=params)
            if r.status_code in (401, 403):
                if await self.login():
                    r = await self.client.get(path, params=params)
            data = None
            try:
                data = r.json()
            except Exception:
                data = None
            return data, r.status_code
        except httpx.HTTPError:
            return None, 0

    # ------------- INSTRUMENTS CACHE -------------

    @staticmethod
    def _upper(s: Optional[str]) -> str:
        return (s or "").strip().upper()

    @staticmethod
    def _extract_base_symbol(sym: str) -> Optional[str]:
        """
        Extrae 'AL30' o 'GD30' de variantes como 'MERV - XMEV - AL30 - 24hs'
        o devuelve el propio si ya es AL30/GD30.
        """
        u = sym.strip().upper()
        for target in ("AL30", "GD30"):
            if target == u:
                return target
        parts = [p.strip() for p in u.split("-")]
        for p in parts:
            t = re.sub(r"\s+", "", p)
            if t in ("AL30", "GD30"):
                return t
        m = re.search(r"\b(AL30|GD30)\b", u)
        if m:
            return m.group(1)
        return None

    def _index_add(self, base: str, market_id: Optional[str], symbol: Optional[str]) -> None:
        if not base:
            return
        lst = self._symbols_index.setdefault(base, [])
        entry = {
            "marketId": self._upper(market_id),
            "symbol": (symbol or "").strip(),
            "symbolU": self._upper(symbol),
        }
        if entry not in lst:
            lst.append(entry)

    def _parse_instruments_payload(self, payload: object) -> None:
        """
        Alimenta _symbols_index con candidates para AL30/GD30.
        Acepta estructuras de /rest/instruments/all y /rest/instruments/details.
        """
        if isinstance(payload, dict) and "instruments" in payload and isinstance(payload["instruments"], list):
            rows = payload["instruments"]
        elif isinstance(payload, list):
            rows = payload
        else:
            return

        for row in rows:
            if not isinstance(row, dict):
                continue

            iid = row.get("instrumentId")
            if isinstance(iid, dict):
                base = self._extract_base_symbol(str(iid.get("symbol") or ""))
                if base:
                    self._index_add(base, iid.get("marketId"), iid.get("symbol"))

            if "symbol" in row and isinstance(row["symbol"], (str, type(None))):
                sym = row["symbol"] or ""
                base = self._extract_base_symbol(sym)
                seg = row.get("segment") or {}
                marketId = None
                if isinstance(seg, dict):
                    marketId = seg.get("marketId") or seg.get("marketSegmentId")
                if base:
                    self._index_add(base, marketId, sym)

    async def _ensure_instruments_cache(self) -> None:
        if self._instrument_cache_loaded:
            return
        for path in ("/rest/instruments/details", "/rest/instruments/all"):
            payload, status = await self._get_json(path)
            if status == 200 and payload is not None:
                self._parse_instruments_payload(payload)
        self._instrument_cache_loaded = True

    def _candidates_for(self, base: str) -> List[Dict[str, str]]:
        """
        Devuelve candidates [{marketId, symbol, symbolU}] para AL30/GD30.
        Orden: preferimos símbolo EXACTO 'AL30'/'GD30' si existe.
        """
        lst = self._symbols_index.get(base, [])
        exact = [x for x in lst if x["symbolU"] == base]
        others = [x for x in lst if x["symbolU"] != base]
        return exact + others if (exact or others) else [{"marketId": "", "symbol": base, "symbolU": base}]

    # ------------- EXTRACTOR DE PRECIOS -------------

    @staticmethod
    def _get_nested(d: dict, path: str):
        cur = d
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur

    @classmethod
    def _try_get_number(cls, item: dict, keys: List[str]) -> Optional[float]:
        for k in keys:
            val = cls._get_nested(item, k) if "." in k else (item.get(k) if isinstance(item, dict) else None)
            if isinstance(val, (int, float)):
                return float(val)
        return None

    def _extract_price_from_payload(self, payload: object, base_symbol: str) -> Optional[float]:
        """
        Extrae un precio numérico desde estructuras comunes.
        Caso confirmado en tu tenant: {"marketData":{"LA":{"price": ...}}}
        """
        PRICE_KEYS = [
            "last", "price", "ultimo", "close", "p",
            "lastPrice", "trade.price",
            "LA", "LA.price", "LA.p", "ltp", "lastTradedPrice",
            "marketData.LA.price", "marketData.LA.p", "marketData.last.price"
        ]

        # 1) dict directo: probamos rutas conocidas (incluye marketData.LA.price)
        if isinstance(payload, dict):
            v = self._try_get_number(payload, PRICE_KEYS)
            if v is not None:
                return v

            # 1.b) manejo explícito para marketData → LA
            md = payload.get("marketData")
            if isinstance(md, dict):
                la = md.get("LA") or md.get("Last") or md.get("LTP")
                if isinstance(la, dict):
                    for k in ("price", "p", "last", "lastPrice"):
                        val = la.get(k)
                        if isinstance(val, (int, float)):
                            return float(val)

            # 2) dict con listas típicas
            for key in ("data", "results", "quotes", "rows", "items", "instruments"):
                if key in payload and isinstance(payload[key], list):
                    for row in payload[key]:
                        if isinstance(row, dict):
                            sym = (row.get("symbol") or row.get("ticker") or row.get("code") or "")
                            if self._upper(sym) in ("", base_symbol):
                                v = self._try_get_number(row, PRICE_KEYS)
                                if v is not None:
                                    return v

        # 3) lista de dicts
        if isinstance(payload, list):
            for row in payload:
                if isinstance(row, dict):
                    sym = (row.get("symbol") or row.get("ticker") or row.get("code") or "")
                    if self._upper(sym) in ("", base_symbol):
                        v = self._try_get_number(row, PRICE_KEYS)
                        if v is not None:
                            return v
        return None

    # ------------- MARKETDATA -------------

    async def _marketdata_get(self, params: Dict[str, str]) -> Tuple[Optional[object], int]:
        """
        GET /rest/marketdata/get con manejo de 429 (un retry con backoff).
        """
        payload, status = await self._get_json("/rest/marketdata/get", params=params)
        if status == 429:
            await asyncio.sleep(1.25)  # backoff corto
            payload, status = await self._get_json("/rest/marketdata/get", params=params)
        return payload, status

    async def _fetch_single_symbol(self, base: str) -> Optional[float]:
        """
        Intenta obtener precio para AL30 o GD30.
        1) carga/usa instrumentos para conocer marketId/símbolos exactos
        2) prueba varias combinaciones de parámetros (con entries=LA cuando hay marketId)
        """
        await self._ensure_instruments_cache()
        candidates = self._candidates_for(base)

        # primero, prueba simple (algunos tenants aceptan sin marketId)
        trials: List[Dict[str, str]] = [{"symbol": base}]

        # luego, con marketId/símbolo exacto + entries=LA (lo que tu API pidió)
        for c in candidates:
            symbol_exact = c["symbol"] or base
            market_id = c["marketId"] or ""
            if market_id:
                trials.append({"symbol": symbol_exact, "marketId": market_id, "entries": "LA"})
                # algunas instalaciones aceptan la forma instrumentId.*, la dejamos por si aplica
                trials.append({"instrumentId.symbol": symbol_exact, "instrumentId.marketId": market_id})

        # Ejecutar trials en orden
        for params in trials:
            payload, status = await self._marketdata_get(params)
            if status != 200 or payload is None:
                continue
            price = self._extract_price_from_payload(payload, base)
            if isinstance(price, (int, float)):
                return float(price)
        return None

    async def get_quotes_al30_gd30(self) -> Optional[dict]:
        """
        Obtiene AL30 y GD30 usando /rest/marketdata/get (con lookup de instrumentos y retries).
        """
        if not (self._logged_root or self._logged_rest):
            await self.login()

        al30 = await self._fetch_single_symbol("AL30")
        gd30 = await self._fetch_single_symbol("GD30")
        if al30 is not None and gd30 is not None:
            return {"al30": al30, "gd30": gd30}
        return None

    # ------------- DIAG (breve, evitar 429) -------------

    async def diagnose_quotes_endpoints(self) -> list[dict]:
        """
        Versión mínima (evitar rate-limit). Solo probamos las rutas que usamos.
        """
        await self._ensure_instruments_cache()
        cands = [
            ("/rest/marketdata/get", {"symbol": "AL30"}),
            ("/rest/marketdata/get", {"symbol": "GD30"}),
        ]
        for base in ("AL30", "GD30"):
            for c in self._candidates_for(base):
                if c["marketId"]:
                    cands.append((
                        "/rest/marketdata/get",
                        {"symbol": c["symbol"] or base, "marketId": c["marketId"], "entries": "LA"},
                    ))
                    break

        results: list[dict] = []
        for path, params in cands:
            try:
                r = await self.client.get(path, params=params)
                body = r.text or ""
                sample = body[:400].replace("\n", " ")
                json_ok = False
                keys_detected: list[str] = []
                try:
                    data = r.json()
                    json_ok = True

                    def sniff(obj):
                        if isinstance(obj, dict):
                            for k in ("AL30", "GD30", "symbol", "ticker", "last", "price", "ultimo", "LA", "status"):
                                if k in obj and k not in keys_detected:
                                    keys_detected.append(k)
                        if isinstance(obj, list) and obj:
                            sniff(obj[0])

                    sniff(data)
                except Exception:
                    pass

                results.append({
                    "path": f"{path}?{'&'.join([f'{k}={v}' for k, v in params.items()])}",
                    "status": r.status_code,
                    "json_ok": json_ok,
                    "keys_detected": keys_detected[:8],
                    "sample": sample
                })
            except Exception as e:
                results.append({
                    "path": f"{path}?{'&'.join([f'{k}={v}' for k, v in params.items()])}",
                    "status": 0,
                    "json_ok": False,
                    "keys_detected": [],
                    "sample": f"ERR: {type(e).__name__}"
                })
        return results
