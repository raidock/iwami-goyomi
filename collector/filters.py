"""山陰フィルタと、浜田を起点にしたアクセス距離帯の判定。"""
from __future__ import annotations

from typing import Iterable

from .models import Event


# 浜田（石見）からの体感アクセス。config.yaml から上書き可能。
# キーは県名、値はその県内の市町名→距離帯。'*' はデフォルト。
DEFAULT_TIERS: dict[str, dict[str, str]] = {
    "島根県": {
        "津和野": "daytrip_easy", "益田": "daytrip_easy", "浜田": "daytrip_easy",
        "江津": "daytrip_easy", "大田": "daytrip",
        "出雲": "daytrip", "松江": "daytrip", "安来": "daytrip_far",
        "*": "daytrip",
    },
    "鳥取県": {
        "米子": "daytrip_far", "境港": "daytrip_far",
        "倉吉": "excursion", "鳥取": "excursion",
        "*": "excursion",
    },
}

TIER_LABEL = {
    "daytrip_easy": "日帰り◎",
    "daytrip": "日帰り○",
    "daytrip_far": "日帰り（早発）",
    "excursion": "小遠征",
    "far": "遠征",
}


def _match_tier(event: Event, tiers: dict) -> str:
    table = tiers.get(event.prefecture)
    if not table:
        return "far"
    haystack = " ".join(filter(None, [event.city, event.venue, event.title]))
    for city, tier in table.items():
        if city != "*" and city in haystack:
            return tier
    return table.get("*", "far")


def filter_and_score(
    events: Iterable[Event],
    target_prefectures: list[str],
    tiers: dict | None = None,
) -> list[Event]:
    """対象県だけ残し、距離帯を付与して開始日順に並べる。"""
    tiers = tiers or DEFAULT_TIERS
    kept: list[Event] = []
    for ev in events:
        if ev.prefecture not in target_prefectures:
            continue
        ev.distance_tier = _match_tier(ev, tiers)
        kept.append(ev)
    kept.sort(key=lambda e: (e.date_start or __import__("datetime").date.max, e.prefecture or ""))
    return kept
