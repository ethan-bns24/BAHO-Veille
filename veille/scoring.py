from __future__ import annotations

import re
from datetime import datetime, timezone

from . import keywords as defaults
from .models import ScoredTender, ScoreLine, Tender
from .text import normalized

# « 120 chambres », « 4 500 nuitées », « 80 personnes » : le volume est un filtre du brief.
VOLUME_PATTERN = re.compile(
    r"(\d[\d\s\u00a0.,]{0,12})\s*(chambres?|nuit[ée]es?|lits?|personnes?|participants?|couverts?|stagiaires?)\b",
    re.IGNORECASE,
)


def default_targeting() -> dict[str, list[str]]:
    return {
        "hotel_keywords": list(defaults.HOTEL_KEYWORDS),
        "service_keywords": list(defaults.SERVICE_KEYWORDS),
        "broad_terms": list(defaults.BROAD_TERMS),
        "exclusions": list(defaults.EXCLUSIONS),
        "decisive_services": list(defaults.DECISIVE_SERVICES),
        "primary_cpvs": list(defaults.PRIMARY_CPVS),
        "secondary_cpvs": list(defaults.SECONDARY_CPVS),
    }


def score(tender: Tender, settings: dict, hotels: list[dict], targeting: dict | None = None) -> ScoredTender:
    """Score explicable sur 100. Aucun champ manquant n'exclut une annonce."""
    rules = {**default_targeting(), **(targeting or {})}
    text = normalized(" ".join([tender.title, tender.description, " ".join(tender.lots), " ".join(tender.cpvs)]))
    lines: list[ScoreLine] = []

    hits = _hits(text, rules["hotel_keywords"])
    service_hits = _hits(text, rules["service_keywords"])
    primary_cpv = _matching_cpvs(tender.cpvs, rules["primary_cpvs"])
    secondary_cpv = _matching_cpvs(tender.cpvs, rules["secondary_cpvs"])
    broad = {normalized(term) for term in rules["broad_terms"]}
    specific = [hit for hit in hits if normalized(hit) not in broad]
    institutional = _institutional(text, rules["exclusions"])

    commercial_match = bool(primary_cpv) or bool(specific) or (
        bool(hits) and not institutional
    ) or _service_combo(service_hits, text, rules["decisive_services"])

    # 1. Mots-clés et codes CPV
    maximum = int(settings["keyword_weight"])
    if primary_cpv:
        factor, proof = 1.0, f"CPV prioritaire {', '.join(primary_cpv)}"
    elif specific and len(specific) > 1:
        factor, proof = 1.0, ", ".join(specific[:3])
    elif specific:
        factor, proof = 0.75, specific[0]
    elif secondary_cpv:
        factor, proof = 0.5, f"CPV secondaire {', '.join(secondary_cpv)}"
    elif hits:
        factor, proof = 0.4, f"terme générique : {hits[0]}"
    else:
        factor, proof = 0.0, "aucune correspondance"
    if factor:
        lines.append(ScoreLine("Mots-clés et CPV", round(maximum * factor), maximum, proof))

    # 2. Géographie — seulement si l'annonce est bien une opportunité hôtelière :
    # une rénovation d'hôtel de ville en zone BAHO ne vaut aucun point commercial.
    maximum = int(settings["geography_weight"])
    match = _geography_match(tender, hotels) if commercial_match else None
    if match:
        lines.append(ScoreLine("Zone BAHO", maximum, maximum, match))
    else:
        lines.append(ScoreLine("Zone BAHO", 0, maximum, _geography_detail(tender, commercial_match)))

    # 3. Montant estimé
    maximum = int(settings["amount_weight"])
    threshold = float(settings["interesting_amount_eur"])
    if tender.estimate_eur is None:
        lines.append(ScoreLine("Montant estimé", 0, maximum, "Non renseigné — aucune exclusion"))
    elif commercial_match and tender.estimate_eur >= threshold:
        lines.append(ScoreLine("Montant estimé", maximum, maximum, f"{_euro(tender.estimate_eur)} ≥ seuil {_euro(threshold)}"))
    else:
        lines.append(ScoreLine("Montant estimé", 0, maximum, f"{_euro(tender.estimate_eur)} < seuil {_euro(threshold)}"))

    # 4. Délai de réponse
    maximum = int(settings["deadline_weight"])
    minimum_days = float(settings["minimum_response_days"])
    if not tender.deadline_at:
        lines.append(ScoreLine("Délai de réponse", 0, maximum, "Échéance non publiée"))
    else:
        days = (tender.deadline_at - datetime.now(timezone.utc)).total_seconds() / 86400
        if commercial_match and days >= minimum_days:
            lines.append(ScoreLine("Délai de réponse", maximum, maximum, f"{days:.0f} jours restants"))
        elif days >= 0:
            lines.append(ScoreLine("Délai de réponse", 0, maximum, f"Délai court : {days:.0f} jour(s)"))
        else:
            lines.append(ScoreLine("Délai de réponse", 0, maximum, "Échéance dépassée — conservée à l'historique"))

    # 5. Complétude du dossier
    maximum = int(settings["information_weight"])
    known = sum(bool(x) for x in (tender.buyer != "Non renseigné", tender.description, tender.deadline_at, tender.source_url))
    ratio = min(1.0, (known + min(len(tender.documents), 1)) / 5) if commercial_match else 0.0
    lines.append(ScoreLine("Informations disponibles", round(maximum * ratio), maximum,
                           f"{known}/4 champs clés · {len(tender.documents)} document(s)"))

    # 6. Prestations associées
    maximum = int(settings["service_weight"])
    if service_hits and commercial_match:
        ratio = min(1.0, len(service_hits) / 2)
        lines.append(ScoreLine("Prestations associées", round(maximum * ratio), maximum, ", ".join(service_hits[:4])))
    else:
        lines.append(ScoreLine("Prestations associées", 0, maximum, "Aucune prestation complémentaire identifiée"))

    # Lorsque la détection ne repose que sur un terme générique (« hôtel » seul, sans
    # code CPV ni expression spécifique), les autres critères ne doivent pas porter
    # l'annonce au-dessus du seuil à eux seuls : l'annonce reste visible, moins haut.
    generic_only = commercial_match and not primary_cpv and not specific and not secondary_cpv
    if generic_only:
        for line in lines[1:]:
            if line.points: line.points = round(line.points / 2)
        lines.append(ScoreLine("Confiance du ciblage", 0, 0,
                               "Correspondance générique uniquement — critères annexes comptés à 50 %"))
    total = min(100, sum(line.points for line in lines))
    reasons = [f"{line.points}/{line.maximum} {line.label}: {line.detail}" for line in lines if line.points]
    if institutional and not primary_cpv:
        reasons.append("Mention institutionnelle détectée (« hôtel de ville ») — non retenue comme opportunité")
    if not reasons:
        reasons = ["À qualifier — aucune correspondance forte détectée"]
    return ScoredTender(tender=tender, score=total, reasons=reasons,
                        keyword_hits=hits + service_hits, commercial_match=commercial_match, breakdown=lines)


def detect_volume(text: str) -> str:
    """Extrait « 120 chambres », « 4 500 nuitées »… pour le filtre Volume du brief."""
    found: list[str] = []
    for quantity, unit in VOLUME_PATTERN.findall(text or ""):
        digits = re.sub(r"[^\d]", "", quantity)
        if not digits or len(digits) > 7: continue
        label = f"{int(digits):,}".replace(",", " ") + f" {unit.lower()}"
        if label not in found: found.append(label)
    return " · ".join(found[:4]) or "Non renseigné"


def detect_buyer_profile(buyer: str) -> str:
    """Type d'acheteur (hôpital, université, collectivité…) — filtre du brief."""
    target = normalized(buyer)
    for label, markers in defaults.BUYER_PROFILES.items():
        if any(marker in target for marker in markers): return label
    return "Acheteur public"


def _hits(text: str, terms) -> list[str]:
    found, seen = [], set()
    padded = f" {text} "
    for term in terms:
        canonical = normalized(str(term))
        if canonical and f" {canonical} " in padded and canonical not in seen:
            found.append(str(term))
            seen.add(canonical)
    return found


def _matching_cpvs(cpvs: list[str], reference) -> list[str]:
    wanted = {"".join(c for c in str(code) if c.isdigit())[:8] for code in reference}
    found = []
    for code in cpvs:
        digits = "".join(c for c in str(code) if c.isdigit())[:8]
        if digits in wanted and digits not in found: found.append(digits)
    return found


def _geography_match(tender: Tender, hotels: list[dict]) -> str | None:
    target = normalized(f"{tender.location} {tender.department}")
    departments = {part.strip().upper() for part in tender.department.split(",") if part.strip()}
    if not target or target == "non renseigne": return None
    for hotel in hotels:
        city, department = str(hotel.get("city", "")), str(hotel.get("department", ""))
        if department and department.upper() in departments:
            return f"{hotel.get('name', 'implantation BAHO')} ({department})"
        normalized_city = normalized(city)
        if normalized_city and f" {normalized_city} " in f" {target} ":
            return f"{hotel.get('name', 'implantation BAHO')} — {city}"
    return None


def _geography_detail(tender: Tender, commercial_match: bool = True) -> str:
    if not commercial_match: return "Non applicable — annonce non hôtelière"
    if tender.department: return f"Département {tender.department} — hors implantations BAHO"
    if tender.location and tender.location != "Non renseigné": return f"{tender.location} — hors implantations BAHO"
    return "Lieu d'exécution non publié"


def _service_combo(hits: list[str], text: str, decisive) -> bool:
    # Une consultation de restauration ou de salles isolée n'est pas une opportunité hôtelière.
    marks = {normalized(str(x)) for x in decisive}
    if {normalized(h) for h in hits} & marks: return True
    return bool(hits) and ("groupe" in text or "nuitee" in text or "residentiel" in text)


def _institutional(text: str, exclusions) -> bool:
    return any(normalized(str(phrase)) in text for phrase in exclusions)


def _euro(amount: float | None) -> str:
    if amount is None: return "Non renseigné"
    return f"{amount:,.0f} €".replace(",", " ")
