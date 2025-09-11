from __future__ import annotations
import os, json, time, random
import urllib.request, urllib.parse, urllib.error
import http.cookiejar
from typing import Optional, Dict, Any, Tuple

class VetaClient:
    """
    Cliente Veta (stdlib) robusto:
      - Lee VETA_BASE_URL/VETA_URL y credenciales desde entorno.
      - Login por formulario y headers; usa cookie y/o X-Auth-Token.
      - Fuerza 'X-Requested-With: XMLHttpRequest' en GET JSON (evita HTML de login).
      - Reintentos con backoff para 429; re-login automático en 401/403 o si devuelve HTML.
      - Helpers: instruments/details, resolver símbolo '... - 24hs', fetch LA/BI/OF.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        user_agent: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        env_base = os.getenv("VETA_BASE_URL") or os.getenv("VETA_URL") or ""
        self.base_url = (base_url or env_base).rstrip("/")
        self.user = user or os.getenv("VETA_USER", "")
        self.password = password or os.getenv("VETA_PASS", "")
        self.user_agent = user_agent or os.getenv("VETA_USER_AGENT", "ws-bonos/ingestor")
        self.timeout = float(timeout or os.getenv("VETA_TIMEOUT", "10"))
        self.default_market_id = os.getenv("VETA_MARKET_ID_DEFAULT", "ROFX")

        if not self.base_url:
            raise ValueError("VETA_BASE_URL/VETA_URL no configurada")
        if not self.user or not self.password:
            raise ValueError("VETA_USER / VETA_PASS no configurados")

        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.auth_token: Optional[str] = None

    # ----------------- HTTP -----------------

    def _req(self, url: str, method: str = "GET",
             headers: Optional[Dict[str, str]] = None,
             data: Optional[bytes] = None):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("User-Agent", self.user_agent)
        if self.auth_token:
            req.add_header("X-Auth-Token", self.auth_token)
        if headers:
            h = dict(headers)
            # Si pedimos JSON, agregamos AJAX para evitar login.html
            if h.get("Accept") == "application/json" and "X-Requested-With" not in h:
                h["X-Requested-With"] = "XMLHttpRequest"
            for k, v in h.items():
                req.add_header(k, v)
        return self.opener.open(req, timeout=self.timeout)

    def _get_json_raw(self, url: str, params: Optional[Dict[str, str]] = None) -> Any:
        if params:
            qs = urllib.parse.urlencode(params, doseq=True)
            url = f"{url}&{qs}" if "?" in url else f"{url}?{qs}"
        resp = self._req(url, method="GET",
                         headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})
        text = resp.read().decode("utf-8", errors="replace")
        ct = (resp.headers.get("Content-Type") or "").lower()
        if "json" not in ct:
            # devolvió HTML (p.ej. login.html)
            raise RuntimeError(f"NOT_JSON:{ct}:{text[:120]!r}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"JSON inválido: {e}; sample={text[:120]!r}") from e

    def _get_json_auth(self, url: str, params: Optional[Dict[str, str]] = None,
                       max_retries: int = 3) -> Any:
        """
        GET JSON con manejo de:
          - 429: backoff + retry
          - 401/403: re-login y retry
          - HTML (login): re-login y retry
        """
        attempt = 0
        last_err: Optional[BaseException] = None
        while attempt < max_retries:
            try:
                return self._get_json_raw(url, params)
            except urllib.error.HTTPError as e:
                # Manejo de códigos
                if e.code in (401, 403):
                    self.login()
                    last_err = e
                elif e.code == 429:
                    # Exponential backoff con jitter
                    sleep_s = min(2 ** attempt, 8) + random.uniform(0, 0.5)
                    time.sleep(sleep_s)
                    last_err = e
                elif e.code in (301, 302, 303, 307, 308):
                    # Posible redirect a login → forzar re-login
                    self.login()
                    last_err = e
                else:
                    raise
            except RuntimeError as e:
                # Si no es JSON (login.html), re-login y reintentar
                if str(e).startswith("NOT_JSON"):
                    self.login()
                    last_err = e
                else:
                    raise
            attempt += 1
        # Si agotamos reintentos, lanzamos último error
        if last_err:
            raise last_err
        raise RuntimeError("Falló _get_json_auth sin excepción previa")

    # ----------------- Login -----------------

    def _try_header_login(self, path: str) -> bool:
        url = f"{self.base_url}{path}"
        headers = {
            "X-Username": self.user,
            "X-Password": self.password,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            r = self._req(url, method="POST", headers=headers, data=b"")
            _ = r.read()
            token = r.headers.get("X-Auth-Token")
            if token:
                self.auth_token = token
        except urllib.error.HTTPError as e:
            token = e.headers.get("X-Auth-Token") if hasattr(e, "headers") else None
            if token:
                self.auth_token = token
            if e.code not in (301, 302, 303, 307, 308):
                raise
        return bool(self.auth_token or len(self.cj) > 0)

    def _try_form_login(self) -> bool:
        url = f"{self.base_url}/j_spring_security_check"
        data = urllib.parse.urlencode({"j_username": self.user, "j_password": self.password}).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            r = self._req(url, method="POST", headers=headers, data=data)
            _ = r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (301, 302, 303, 307, 308):
                raise
        return len(self.cj) > 0

    def _have_session(self) -> bool:
        return bool(self.auth_token) or len(self.cj) > 0

    def login(self) -> None:
        # Priorizar form login (fue el más confiable en tu tenant)
        ok = self._try_form_login()
        ok = ok or self._try_header_login("/rest/login")
        ok = ok or self._try_header_login("/login")
        if not ok:
            raise RuntimeError("Login Veta: no se estableció sesión (token/cookie)")

    def ensure_session(self) -> None:
        if not self._have_session():
            self.login()

    # ----------------- API helpers -----------------

    def instruments_details(self) -> Any:
        self.ensure_session()
        return self._get_json_auth(f"{self.base_url}/rest/instruments/details")

    @staticmethod
    def _upper(s: Optional[str]) -> str:
        return (s or "").strip().upper()

    
    def resolve_symbol_24hs(self, base: str) -> Tuple[str, str]:
        """
        Devuelve (symbol, marketId) para el '... - 24hs' del base (AL30/GD30).
        Preferencias (en orden):
          1) Contenga '24hs'
          2) Coincidencia exacta del token base (AL30/GD30), NO la variante con 'D'
          3) Menor longitud del símbolo (más “limpio”)
        Si no hay 24hs, usa el primer match del base. Último recurso: (BASE, ROFX).
        """
        import re
        base_u = self._upper(base)
        data = self.instruments_details()
        rows = data.get("instruments", data if isinstance(data, list) else [])
        cands = []
        if isinstance(rows, list):
            for r in rows:
                sym = (r.get("symbol") or (r.get("instrumentId") or {}).get("symbol") or "").strip()
                mid = (
                    (r.get("segment") or {}).get("marketId")
                    or (r.get("segment") or {}).get("marketSegmentId")
                    or (r.get("instrumentId") or {}).get("marketId")
                    or ""
                )
                su = self._upper(sym)
                if base_u in su:
                    tokens = [t for t in re.split(r'[^A-Z0-9]+', su) if t]
                    is_24 = ("24HS" in tokens) or ("24HS" in su)
                    exact = (base_u in tokens)                # AL30 / GD30
                    is_d  = ((base_u + "D") in tokens)        # AL30D / GD30D
                    # score: mayor es mejor
                    score = (
                        1 if is_24 else 0,
                        1 if exact else 0,
                        0 if not is_d else -1,               # penalizar variante 'D'
                        -len(sym),                            # preferir más corto
                    )
                    cands.append((score, sym, mid or self.default_market_id))
        if cands:
            cands.sort(reverse=True, key=lambda x: x[0])
            best = cands[0]
            return best[1], best[2]
        return (base_u, self.default_market_id)
    def fetch_la_bi_of(self, symbol: str, market_id: Optional[str] = None, entries: str = "LA,BI,OF") -> Dict[str, Any]:
        """
        Llama /rest/marketdata/get y devuelve {'last': float|None, 'bid': (p,sz)|None, 'ask': (p,sz)|None, 'raw': payload}
        """
        self.ensure_session()
        params = {"symbol": symbol, "marketId": market_id or self.default_market_id, "entries": entries}
        payload = self._get_json_auth(f"{self.base_url}/rest/marketdata/get", params=params)
        md = payload.get("marketData") if isinstance(payload, dict) else {}
        def num(x): return float(x) if isinstance(x, (int, float)) else None
        last = num(md.get("LA", {}).get("price")) if isinstance(md.get("LA"), dict) else None
        def top(arr):
            if isinstance(arr, list) and arr:
                p = num(arr[0].get("price")); s = num(arr[0].get("size"))
                if p is not None and s is not None: return (p, s)
            return None
        bid = top(md.get("BI") or [])
        ask = top(md.get("OF") or [])
        return {"last": last, "bid": bid, "ask": ask, "raw": payload}

    def fetch_last(self, base_symbol: str) -> Optional[float]:
        sym, mid = self.resolve_symbol_24hs(base_symbol)
        data = self.fetch_la_bi_of(sym, mid)
        return data.get("last")

if __name__ == "__main__":
    vc = VetaClient()
    vc.login()
    print("login: OK (cookie/token listo)")
    sym, mid = vc.resolve_symbol_24hs("AL30")
    q = vc.fetch_la_bi_of(sym, mid)
    print("AL30 24hs →", sym, mid, "| last/bid/ask:", q["last"], q["bid"], q["ask"])
