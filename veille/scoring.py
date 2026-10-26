from __future__ import annotations

from datetime import datetime, timezone

from .keywords import CPVS, HOTEL_KEYWORDS, SERVICE_KEYWORDS
from .models import ScoredTender, Tender
from .text import normalized


def score(tender: Tender, settings: dict, hotels: list[dict]) -> ScoredTender:
    """Return an explainable 0-100 score; no missing field excludes a tender."""
    text = normalized(" ".join([tender.title, tender.description, " ".join(tender.cpvs)]))
    reasons: list[str] = []
    hits = _hits(text, HOTEL_KEYWORDS)
    service_hits = _hits(text, SERVICE_KEYWORDS)
    cpv_match = _has_priority_cpv(tender.cpvs)
    # A lone, ambiguous word such as “hôtel de ville” must never trigger an alert.
    broad_terms = {"hôtel", "hôtels", "hôtellerie"}
    commercial_match = cpv_match or bool([hit for hit in hits if hit not in broad_terms]) or (
        bool(hits) and not _institutional_hotel(text)
    ) or _service_combo(service_hits, text)
    total = 0.0
    if hits or cpv_match:
        factor = 1 if cpv_match or len(hits) > 1 else 0.5
        points = settings["keyword_weight"] * factor
        total += points
        proof = ", ".join(hits[:3]) if hits else "code CPV hôtelier"
        reasons.append(f"{points:.0f}/{settings['keyword_weight']} mots-clés: {proof}")

    geography = _geography_match(tender, hotels)
    if geography:
        points = settings["geography_weight"]
        total += points
        reasons.append(f"{points:.0f}/{settings['geography_weight']} zone BAHO: {geography}")

    if commercial_match and tender.estimate_eur is not None and tender.estimate_eur >= settings["interesting_amount_eur"]:
        points = settings["amount_weight"]
        total += points
        reasons.append(f"{points:.0f}/{settings['amount_weight']} montant estimé intéressant")

    if commercial_match and tender.deadline_at:
        days = (tender.deadline_at - datetime.now(timezone.utc)).total_seconds() / 86400
        if days >= settings["minimum_response_days"]:
            points = settings["deadline_weight"]
            total += points
            reasons.append(f"{points:.0f}/{settings['deadline_weight']} délai de réponse: {days:.0f} jours")
        elif days >= 0:
            reasons.append("Délai de réponse court")
        else:
            reasons.append("Échéance dépassée — conservée dans l'historique")

    if commercial_match:
        known = sum(bool(x) for x in (tender.buyer != "Non renseigné", tender.description, tender.deadline_at, tender.source_url))
        documents = len(tender.documents)
        ratio = min(1, (known + min(documents, 1)) / 5)
        if ratio:
            points = settings["information_weight"] * ratio
            total += points
            reasons.append(f"{points:.0f}/{settings['information_weight']} informations disponibles")

    if service_hits and commercial_match:
        points = settings["service_weight"] * min(1, len(service_hits) / 2)
        total += points
        reasons.append(f"{points:.0f}/{settings['service_weight']} prestations: {', '.join(service_hits[:3])}")

    return ScoredTender(tender=tender, score=min(100, round(total)), reasons=reasons or ["À qualifier — aucune correspondance forte détectée"], keyword_hits=hits + service_hits, commercial_match=commercial_match)


def _hits(text: str, terms: tuple[str, ...]) -> list[str]:
    found, seen = [], set()
    for term in terms:
        canonical = normalized(term)
        if f" {canonical} " in f" {text} " and canonical not in seen:
            found.append(term)
            seen.add(canonical)
    return found


def _has_priority_cpv(cpvs: list[str]) -> bool:
    return any("".join(c for c in code if c.isdigit())[:8] in CPVS for code in cpvs)


def _geography_match(tender: Tender, hotels: list[dict]) -> str | None:
    target = normalized(f"{tender.location} {tender.department}")
    if not target or target == "non renseigne": return None
    for hotel in hotels:
        if not hotel.get("city") and not hotel.get("department"): continue
        for item in (hotel.get("city", ""), hotel.get("department", "")):
            item = normalized(str(item))
            if item and item in target: return str(hotel.get("name", "implantation BAHO"))
    return None


def _service_combo(hits: list[str], text: str) -> bool:
    # A stand-alone catering or conference procurement is not a hotel opportunity.
    decisive = {"séminaire résidentiel", "congressiste", "forfait hébergement", "hébergement et restauration", "demi-pension", "pension complète"}
    return bool(set(hits) & decisive) or (bool(hits) and ("groupe" in text or "nuitee" in text))


def _institutional_hotel(text: str) -> bool:
    return any(phrase in text for phrase in (
        "hotel de ville", "hotel de la ville", "hotel de police", "hotel de region", "hotel du departement",
        "hotel de la marine", "hotel de la guerre", "hotel des impots", "hotel communautaire", "ecole hoteliere",
    ))
