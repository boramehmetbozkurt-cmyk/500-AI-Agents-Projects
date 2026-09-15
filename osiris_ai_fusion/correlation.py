from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from schemas import CorrelationCandidate, MapMarker

LAT_KEYS = {"lat", "latitude"}
LON_KEYS = {"lon", "lng", "long", "longitude"}
TIME_KEYS = {"timestamp", "time", "datetime", "date", "updated", "created_at"}


def _timestamp(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        number = int(value)
        return number // 1000 if number > 10_000_000_000 else number
    if isinstance(value, str):
        candidate = value.strip().replace("Z", "+00:00")
        try:
            return int(datetime.fromisoformat(candidate).timestamp())
        except ValueError:
            return None
    return None


def _extract_objects(value: Any, *, limit: int = 4000) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(item: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(item, dict):
            lowered = {str(k).lower(): v for k, v in item.items()}
            lat = next((lowered[k] for k in LAT_KEYS if k in lowered), None)
            lon = next((lowered[k] for k in LON_KEYS if k in lowered), None)
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                ts = next((_timestamp(lowered[k]) for k in TIME_KEYS if k in lowered), None)
                label = str(
                    lowered.get("title")
                    or lowered.get("name")
                    or lowered.get("place")
                    or lowered.get("description")
                    or "OSIRIS event"
                )[:300]
                found.append({"lat": float(lat), "lon": float(lon), "ts": ts, "label": label})
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return found


def _haversine(a: dict[str, Any], b: dict[str, Any]) -> float:
    radius = 6371.0
    lat1 = math.radians(a["lat"])
    lat2 = math.radians(b["lat"])
    dlat = lat2 - lat1
    dlon = math.radians(b["lon"] - a["lon"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def correlate_evidence(
    evidence: dict[str, Any],
) -> tuple[list[CorrelationCandidate], list[MapMarker]]:
    by_tool: dict[str, list[dict[str, Any]]] = {}
    markers: list[MapMarker] = []
    for tool, record in evidence.items():
        if not record.get("ok"):
            continue
        objects = _extract_objects(record.get("data"))
        evidence_id = str(record.get("evidence_id", ""))
        by_tool[tool] = objects
        for obj in objects[:80]:
            markers.append(
                MapMarker(
                    lat=obj["lat"],
                    lon=obj["lon"],
                    label=obj["label"],
                    tool=tool,
                    evidence_id=evidence_id or None,
                    timestamp=obj.get("ts"),
                )
            )

    candidates: list[CorrelationCandidate] = []
    tools = sorted(by_tool)
    for index, tool_a in enumerate(tools):
        for tool_b in tools[index + 1 :]:
            for a in by_tool[tool_a][:40]:
                for b in by_tool[tool_b][:40]:
                    distance = _haversine(a, b)
                    if distance > 100:
                        continue
                    delta = None
                    if a.get("ts") is not None and b.get("ts") is not None:
                        delta = abs(int(a["ts"]) - int(b["ts"]))
                        if delta > 3 * 3600:
                            continue
                    candidates.append(
                        CorrelationCandidate(
                            tools=[tool_a, tool_b],
                            distance_km=round(distance, 1),
                            time_delta_seconds=delta,
                            summary=(
                                f"{tool_a} ve {tool_b} kaynaklarında yaklaşık {distance:.1f} km "
                                "yakınlıkta olaylar bulundu; bu yalnızca korelasyon adayıdır, "
                                "nedensellik değildir."
                            ),
                            evidence_ids=[
                                evidence[tool_a].get("evidence_id", ""),
                                evidence[tool_b].get("evidence_id", ""),
                            ],
                        )
                    )
                    if len(candidates) >= 30:
                        return candidates, markers[:200]
    return candidates, markers[:200]
