from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


UTC8 = timezone.utc


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def isoformat(dt: datetime | None = None) -> str:
    target = dt or utc_now()
    return target.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class Signal:
    source_id: str
    source_name: str
    title: str
    summary: str
    url: str
    observed_at: str
    weight: int = 1
    tags: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        raw = "|".join([self.source_id, self.url, self.title, self.observed_at])
        return sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "observed_at": self.observed_at,
            "weight": self.weight,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, item: dict[str, Any]) -> "Signal":
        return cls(
            source_id=str(item.get("source_id", "")),
            source_name=str(item.get("source_name", "")),
            title=str(item.get("title", "")),
            summary=str(item.get("summary", "")),
            url=str(item.get("url", "")),
            observed_at=str(item.get("observed_at", isoformat())),
            weight=int(item.get("weight", 1)),
            tags=list(item.get("tags", [])),
        )


@dataclass(slots=True)
class RadarState:
    status: str
    probability_24h: int
    probability_48h: int
    reason: str
    checked_at: str
    signals: list[Signal]
    alert_level: str = "silent"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "probability_24h": self.probability_24h,
            "probability_48h": self.probability_48h,
            "reason": self.reason,
            "checked_at": self.checked_at,
            "alert_level": self.alert_level,
            "signals": [signal.to_dict() for signal in self.signals],
        }

    @classmethod
    def from_dict(cls, item: dict[str, Any]) -> "RadarState":
        return cls(
            status=str(item.get("status", "normal")),
            probability_24h=int(item.get("probability_24h", 0)),
            probability_48h=int(item.get("probability_48h", 0)),
            reason=str(item.get("reason", "")),
            checked_at=str(item.get("checked_at", isoformat())),
            alert_level=str(item.get("alert_level", "silent")),
            signals=[Signal.from_dict(signal) for signal in item.get("signals", [])],
        )

