from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter

from config.pairs import pairs

router = APIRouter()


@router.get("/config/pairs")
def config_pairs() -> List[Dict[str, Any]]:
    """
    Devuelve la lista de pares configurados para el frontend.
    Solo expone id, label y los base tickers de cada pierna.
    Los xoms_symbol strings NO se exponen — son un detalle interno de ingesta.
    """
    return [
        {
            "id": p["id"],
            "label": p["label"],
            "leg_a": {"base": p["leg_a"]["base"]},
            "leg_b": {"base": p["leg_b"]["base"]},
        }
        for p in pairs()
    ]
