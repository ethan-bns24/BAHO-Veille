from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    path: Path
    data: dict[str, Any]

    @property
    def app(self) -> dict[str, Any]: return self.data["app"]
    @property
    def scoring(self) -> dict[str, Any]: return self.data["scoring"]
    @property
    def notification(self) -> dict[str, Any]: return self.data["notification"]
    @property
    def hotels(self) -> list[dict[str, Any]]: return self.data.get("hotels", [])
    @property
    def sources(self) -> list[dict[str, Any]]: return self.data.get("sources", [])

    @property
    def recipients(self) -> list[str]:
        configured = os.getenv("ALERT_RECIPIENTS", "")
        return [x.strip() for x in configured.split(",") if x.strip()] or self.notification.get("recipients", [])

    @property
    def database_path(self) -> Path:
        configured = Path(self.app["database_path"])
        return configured if configured.is_absolute() else self.path.parent / configured


def load_settings(config_path: str | Path | None = None) -> Settings:
    path = Path(config_path or os.getenv("BAHO_CONFIG", "settings.toml")).resolve()
    _load_local_env(path.parent / ".env")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    required = {"app", "notification", "scoring"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Configuration incomplète: {', '.join(sorted(missing))}")
    return Settings(path, data)


def _load_local_env(path: Path) -> None:
    """Small dependency-free .env reader for local runs; Docker injects the same file."""
    if not path.exists(): return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
