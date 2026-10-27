from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Tender:
    source: str
    external_id: str
    title: str
    buyer: str = "Non renseigné"
    description: str = ""
    reference: str = ""
    cpvs: list[str] = field(default_factory=list)
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    location: str = "Non renseigné"
    department: str = ""
    estimate_eur: float | None = None
    rooms_or_nights: str = "Non renseigné"
    documents: list[str] = field(default_factory=list)
    source_url: str = ""
    # Champs du brief restitués dans l'alerte : nature du marché, procédure, profil
    # d'acheteur et durée. Chacun reste facultatif ; une absence n'exclut rien.
    procedure: str = ""
    notice_kind: str = ""
    contract_nature: str = ""
    duration: str = ""
    lots: list[str] = field(default_factory=list)
    buyer_profile: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def public(self) -> dict[str, Any]:
        result = asdict(self)
        result.pop("raw", None)
        for key in ("published_at", "deadline_at"):
            result[key] = result[key].isoformat() if result[key] else None
        return result


@dataclass(slots=True)
class ScoreLine:
    """Une ligne du détail de score, affichée telle quelle dans l'e-mail et le tableau de bord."""
    label: str
    points: int
    maximum: int
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "points": self.points, "maximum": self.maximum, "detail": self.detail}


@dataclass(slots=True)
class ScoredTender:
    tender: Tender
    score: int
    reasons: list[str]
    keyword_hits: list[str]
    commercial_match: bool
    breakdown: list[ScoreLine] = field(default_factory=list)


@dataclass(slots=True)
class UpsertResult:
    tender_id: int
    event: str  # created, updated, unchanged
    source_added: bool
