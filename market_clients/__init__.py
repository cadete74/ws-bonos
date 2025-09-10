from typing import Protocol, Optional, Any

class MarketClient(Protocol):
    async def login(self) -> bool: ...
    async def get_quotes_al30_gd30(self) -> Optional[dict]: ...
    async def aclose(self) -> None: ...

def make_client(name: str, settings: Any) -> MarketClient:
    name = (name or "").strip().lower()
    if name == "veta":
        from .veta import VetaClient
        return VetaClient(settings)
    raise ValueError(f"Cliente de mercado desconocido: {name}")
