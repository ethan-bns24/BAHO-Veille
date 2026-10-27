from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import keywords as defaults

# Clés modifiables en direct depuis le tableau de bord. Les valeurs vivent dans
# `overrides.json`, à côté de la base : `settings.toml` reste la référence versionnée
# et n'est jamais réécrit, donc ses commentaires et sa structure survivent.
NUMERIC_KEYS: dict[str, tuple[str, float, float]] = {
    "app.poll_interval_minutes": ("Fréquence de collecte (minutes)", 1, 1440),
    "app.lookback_days": ("Profondeur de collecte (jours)", 1, 90),
    "notification.minimum_score": ("Seuil d'alerte (/100)", 0, 100),
    "notification.send_interval_seconds": ("Délai entre deux alertes (secondes)", 0, 3600),
    "notification.max_alerts_per_cycle": ("Alertes maximum par cycle", 1, 200),
    "scoring.keyword_weight": ("Poids mots-clés", 0, 100),
    "scoring.geography_weight": ("Poids géographie", 0, 100),
    "scoring.amount_weight": ("Poids montant", 0, 100),
    "scoring.deadline_weight": ("Poids délai", 0, 100),
    "scoring.information_weight": ("Poids complétude", 0, 100),
    "scoring.service_weight": ("Poids prestations", 0, 100),
    "scoring.minimum_response_days": ("Délai de réponse minimal (jours)", 0, 180),
    "scoring.interesting_amount_eur": ("Montant jugé intéressant (€)", 0, 100_000_000),
}

LIST_KEYS: dict[str, str] = {
    "notification.recipients": "Destinataires des alertes",
    "targeting.hotel_keywords": "Mots-clés hébergement",
    "targeting.service_keywords": "Mots-clés prestations associées",
    "targeting.broad_terms": "Termes génériques (non décisifs seuls)",
    "targeting.exclusions": "Exclusions (« hôtel de ville »…)",
    "targeting.decisive_services": "Prestations décisives",
    "targeting.primary_cpvs": "Codes CPV prioritaires",
    "targeting.secondary_cpvs": "Codes CPV secondaires",
    "targeting.search_terms": "Termes interrogés côté serveur",
}

# Termes envoyés aux API pour ratisser large ; le scoring tranche ensuite.
DEFAULT_SEARCH_TERMS: tuple[str, ...] = (
    "hôtel", "hôtellerie", "hébergement", "nuitée", "nuitées", "chambres", "séminaire",
    "congrès", "convention", "colloque", "restauration", "réservation", "séjour",
    "mise à l'abri", "demi-pension", "pension complète", "traiteur", "petit-déjeuner",
)


@dataclass
class Settings:
    path: Path
    data: dict[str, Any]
    overrides: dict[str, Any] = field(default_factory=dict)

    # Valeurs de repli pour une configuration antérieure à ces réglages.
    SEND_DEFAULTS = {"send_interval_seconds": 120, "max_alerts_per_cycle": 12}

    @property
    def app(self) -> dict[str, Any]: return self._section("app")
    @property
    def scoring(self) -> dict[str, Any]: return self._section("scoring")
    @property
    def notification(self) -> dict[str, Any]: return {**self.SEND_DEFAULTS, **self._section("notification")}

    @property
    def targeting(self) -> dict[str, Any]:
        base = {
            "hotel_keywords": list(defaults.HOTEL_KEYWORDS),
            "service_keywords": list(defaults.SERVICE_KEYWORDS),
            "broad_terms": list(defaults.BROAD_TERMS),
            "exclusions": list(defaults.EXCLUSIONS),
            "decisive_services": list(defaults.DECISIVE_SERVICES),
            "primary_cpvs": list(defaults.PRIMARY_CPVS),
            "secondary_cpvs": list(defaults.SECONDARY_CPVS),
            "search_terms": list(DEFAULT_SEARCH_TERMS),
        }
        base.update(self.data.get("targeting", {}))
        base.update(self.overrides.get("targeting", {}))
        return base

    @property
    def hotels(self) -> list[dict[str, Any]]:
        return self.overrides.get("hotels") or self.data.get("hotels", [])

    @property
    def sources(self) -> list[dict[str, Any]]:
        patches = self.overrides.get("sources", {})
        merged = []
        for source in self.data.get("sources", []):
            item = dict(source)
            item.update(patches.get(item.get("name", ""), {}))
            merged.append(item)
        known = {item.get("name") for item in merged}
        for name, patch in patches.items():
            if name not in known and patch.get("kind"):
                merged.append({"name": name, **patch})
        return merged

    @property
    def recipients(self) -> list[str]:
        override = self.overrides.get("notification", {}).get("recipients")
        if override: return [str(x).strip() for x in override if str(x).strip()]
        configured = os.getenv("ALERT_RECIPIENTS", "")
        return [x.strip() for x in configured.split(",") if x.strip()] or self.notification.get("recipients", [])

    @property
    def database_path(self) -> Path:
        configured = Path(self.app["database_path"])
        return configured if configured.is_absolute() else self.path.parent / configured

    @property
    def overrides_path(self) -> Path:
        return self.database_path.parent / "overrides.json"

    def _section(self, name: str) -> dict[str, Any]:
        merged = dict(self.data.get(name, {}))
        merged.update(self.overrides.get(name, {}))
        return merged

    def editable(self) -> dict[str, Any]:
        """Instantané des réglages exposés au tableau de bord."""
        values: dict[str, Any] = {}
        for key in NUMERIC_KEYS:
            section, name = key.split(".")
            values[key] = getattr(self, section).get(name)
        for key in LIST_KEYS:
            section, name = key.split(".")
            values[key] = self.recipients if key == "notification.recipients" else self.targeting.get(name, [])
        return values

    def apply(self, patch: dict[str, Any]) -> "Settings":
        """Fusionne un patch dans overrides.json puis relit la configuration."""
        current = _read_overrides(self.overrides_path)
        for key, value in patch.items():
            if key in ("sources", "hotels"):
                if key == "hotels": current["hotels"] = value
                else: current.setdefault("sources", {}).update(value)
                continue
            section, name = key.split(".", 1)
            current.setdefault(section, {})[name] = value
        self.overrides_path.parent.mkdir(parents=True, exist_ok=True)
        self.overrides_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        return load_settings(self.path)

    def reset(self) -> "Settings":
        self.overrides_path.unlink(missing_ok=True)
        return load_settings(self.path)


def load_settings(config_path: str | Path | None = None) -> Settings:
    path = Path(config_path or os.getenv("BAHO_CONFIG", "settings.toml")).resolve()
    _load_local_env(path.parent / ".env")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    required = {"app", "notification", "scoring"}
    missing = required - data.keys()
    if missing:
        raise ValueError(f"Configuration incomplète: {', '.join(sorted(missing))}")
    settings = Settings(path, data)
    return Settings(path, data, _read_overrides(settings.overrides_path))


def _read_overrides(path: Path) -> dict[str, Any]:
    if not path.exists(): return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _load_local_env(path: Path) -> None:
    """Small dependency-free .env reader for local runs; Docker injects the same file."""
    if not path.exists(): return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
