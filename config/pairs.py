from __future__ import annotations

import json
import os
from typing import TypedDict


class PairLeg(TypedDict):
    base: str
    xoms_symbol: str


class Pair(TypedDict):
    id: str
    label: str
    leg_a: PairLeg
    leg_b: PairLeg


# All XOMS symbol strings confirmed via live probe against Eco:
# AL30/GD30 on 2026-05-14, the other four pairs on 2026-05-15 (24hs variant).
# To add a new pair, run `make probe-symbols` during market hours first.
_DEFAULT_PAIRS: list[Pair] = [
    {
        "id": "AL30_GD30",
        "label": "AL30 / GD30",
        "leg_a": {
            "base": "AL30",
            "xoms_symbol": "MERV - XMEV - AL30 - 24hs",  # confirmed 2026-05-14
        },
        "leg_b": {
            "base": "GD30",
            "xoms_symbol": "MERV - XMEV - GD30 - 24hs",  # confirmed 2026-05-14
        },
    },
    {
        "id": "AL35_GD35",
        "label": "AL35 / GD35",
        "leg_a": {
            "base": "AL35",
            "xoms_symbol": "MERV - XMEV - AL35 - 24hs",  # confirmed 2026-05-15
        },
        "leg_b": {
            "base": "GD35",
            "xoms_symbol": "MERV - XMEV - GD35 - 24hs",  # confirmed 2026-05-15
        },
    },
    {
        "id": "AE38_GD38",
        "label": "AE38 / GD38",
        "leg_a": {
            "base": "AE38",
            "xoms_symbol": "MERV - XMEV - AE38 - 24hs",  # confirmed 2026-05-15
        },
        "leg_b": {
            "base": "GD38",
            "xoms_symbol": "MERV - XMEV - GD38 - 24hs",  # confirmed 2026-05-15
        },
    },
    {
        "id": "AL41_GD41",
        "label": "AL41 / GD41",
        "leg_a": {
            "base": "AL41",
            "xoms_symbol": "MERV - XMEV - AL41 - 24hs",  # confirmed 2026-05-15
        },
        "leg_b": {
            "base": "GD41",
            "xoms_symbol": "MERV - XMEV - GD41 - 24hs",  # confirmed 2026-05-15
        },
    },
    {
        "id": "AL29_GD29",
        "label": "AL29 / GD29",
        "leg_a": {
            "base": "AL29",
            "xoms_symbol": "MERV - XMEV - AL29 - 24hs",  # confirmed 2026-05-15
        },
        "leg_b": {
            "base": "GD29",
            "xoms_symbol": "MERV - XMEV - GD29 - 24hs",  # confirmed 2026-05-15
        },
    },
]

_REQUIRED_FIELDS = ("id", "label", "leg_a", "leg_b")
_REQUIRED_LEG_FIELDS = ("base", "xoms_symbol")


def _validate(pair_list: list[Pair]) -> None:
    if not pair_list:
        raise ValueError("PAIRS list is empty — at least one pair must be configured")
    for p in pair_list:
        for f in _REQUIRED_FIELDS:
            if f not in p:
                raise ValueError(f"Pair missing required field '{f}': {p}")
        for side in ("leg_a", "leg_b"):
            leg = p[side]
            for f in _REQUIRED_LEG_FIELDS:
                if f not in leg:
                    raise ValueError(
                        f"Pair '{p.get('id', '?')}' {side} missing required field '{f}'"
                    )


def _load() -> list[Pair]:
    """Load pairs from PAIRS_JSON env override or fall back to module defaults."""
    raw = os.getenv("PAIRS_JSON", "")
    if raw.strip():
        try:
            loaded: list[Pair] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"PAIRS_JSON is not valid JSON: {exc}") from exc
        _validate(loaded)
        return loaded
    _validate(_DEFAULT_PAIRS)
    return _DEFAULT_PAIRS


# Load once at import time — fail loud on startup if config is wrong.
_PAIRS: list[Pair] = _load()


def pairs() -> list[Pair]:
    """Return the full configured pair list."""
    return _PAIRS


def all_legs() -> list[PairLeg]:
    """Return a flat list of all configured legs across all pairs."""
    result: list[PairLeg] = []
    for p in _PAIRS:
        result.append(p["leg_a"])
        result.append(p["leg_b"])
    return result


def valid_bases() -> set[str]:
    """Return the set of all configured base tickers (e.g. {'AL30', 'GD30', ...})."""
    return {leg["base"] for leg in all_legs()}


def pair_by_id(pid: str) -> Pair | None:
    """Return the pair with the given id, or None if not found."""
    for p in _PAIRS:
        if p["id"] == pid:
            return p
    return None


def ws_symbols() -> list[str]:
    """Return all XOMS symbol strings for subscription (one per leg, all pairs)."""
    return [leg["xoms_symbol"] for leg in all_legs()]
