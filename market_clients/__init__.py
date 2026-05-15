from __future__ import annotations

from typing import Protocol, Optional


class MarketClient(Protocol):
    async def aclose(self) -> None: ...
