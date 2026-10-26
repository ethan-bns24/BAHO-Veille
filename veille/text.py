from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


def plain(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def fingerprint(values: list[str]) -> str:
    return hashlib.sha256("\u241f".join(values).encode()).hexdigest()


def parse_datetime(value: Any) -> datetime | None:
    text = plain(value)
    if not text: return None
    text = text.replace("Z", "+00:00")
    for candidate in (text, text[:19]):
        try:
            stamp = datetime.fromisoformat(candidate)
            return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    for pattern in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d"):
        try: return datetime.strptime(text, pattern).replace(tzinfo=timezone.utc)
        except ValueError: pass
    return None


def iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None
