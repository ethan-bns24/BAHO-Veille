from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlencode

from ..geo import department_from_postcode
from ..http import HttpError, fetch_json
from ..models import Tender
from ..scoring import detect_buyer_profile, detect_volume
from ..text import parse_datetime, plain
from .base import Connector, ConnectorError

# Natures d'avis correspondant à une opportunité ouverte ou à venir. Les attributions
# et les annulations sont volontairement exclues : il n'y a plus rien à y gagner.
OPEN_NATURES = ("APPEL_OFFRE", "RECTIFICATIF", "MODIFICATION", "PRE-INFORMATION", "INTENTION_CONCLURE")

# Champs interrogés côté serveur. `donnees` porte le XML complet de l'avis : y chercher
# les codes CPV rattrape les annonces dont l'objet ne contient aucun mot-clé hôtelier.
SEARCH_FIELDS = ("objet", "descripteur_libelle")


class BoampConnector(Connector):
    """Connecteur de l'API open data officielle du BOAMP (DILA / OpenDataSoft)."""

    endpoint = "https://www.boamp.fr/api/explore/v2.1/catalog/datasets/boamp/records"

    def fetch(self, since: datetime) -> list[Tender]:
        # Le filtrage côté serveur évite de perdre une annonce pertinente lorsqu'une
        # journée de publication chargée dépasse la taille d'une page d'API.
        limit, offset, rows = int(self.source.get("limit", 500)), 0, []
        where = self._where(since)
        while offset < limit:
            query = urlencode({"limit": min(100, limit - offset), "offset": offset,
                               "order_by": "dateparution desc", "where": where})
            try:
                payload = fetch_json(f"{self.endpoint}?{query}", timeout=40)
            except HttpError as exc:
                raise ConnectorError(f"BOAMP indisponible: {exc}") from exc
            if not isinstance(payload, dict):
                raise ConnectorError("BOAMP: réponse inattendue")
            page = payload.get("results", [])
            rows.extend(page)
            if len(page) < 100 or offset + len(page) >= payload.get("total_count", 0): break
            offset += len(page)
        return [self._to_tender(row) for row in rows]

    def _where(self, since: datetime) -> str:
        terms = self.source.get("terms") or ("hôtel", "hébergement", "nuitée", "séminaire", "restauration")
        cpvs = self.source.get("cpvs") or ()
        natures = self.source.get("natures") or OPEN_NATURES
        conditions = [f"search({field}, {_quote(term)})" for term in terms for field in SEARCH_FIELDS]
        conditions += [f"search(donnees, {_quote(str(code))})" for code in cpvs]
        nature_list = ", ".join(_quote(nature) for nature in natures)
        subject = " OR ".join(conditions) or "search(objet, 'hébergement')"
        return f"nature IN ({nature_list}) AND dateparution >= date'{since.date().isoformat()}' AND ({subject})"

    def _to_tender(self, row: dict) -> Tender:
        raw = row.get("donnees") or row.get("DONNEES") or ""
        try: details = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError: details = {}
        description = plain(row.get("objet"))
        reference = plain(row.get("contractfolderid") or row.get("idweb") or row.get("id"))
        url = plain(row.get("url_avis"))
        if url.startswith("/"): url = f"https://www.boamp.fr{url}"
        department = _flat_text(row.get("code_departement_prestation") or row.get("code_departement"))
        buyer = plain(row.get("nomacheteur")) or "Non renseigné"
        postcode = _postcode(details)
        lots = _lot_titles(details)
        return Tender(
            source=self.name,
            external_id=plain(row.get("idweb") or row.get("id") or reference),
            reference=reference,
            title=description or "Intitulé non renseigné",
            description=description,
            buyer=buyer,
            buyer_profile=detect_buyer_profile(buyer),
            cpvs=_cpv_codes(details),
            published_at=parse_datetime(row.get("dateparution")),
            deadline_at=parse_datetime(row.get("datelimitereponse")),
            department=department or department_from_postcode(postcode),
            location=_location(details) or department or "Non renseigné",
            source_url=url,
            estimate_eur=_estimated_amount(details),
            rooms_or_nights=detect_volume(f"{description} {' '.join(lots)}"),
            documents=_document_urls(details),
            procedure=plain(row.get("procedure_libelle") or row.get("type_procedure")),
            notice_kind=plain(row.get("nature_libelle") or row.get("nature")),
            contract_nature=plain(row.get("type_marche") or row.get("famille_libelle")),
            duration=_duration(details),
            lots=lots,
            raw=details if isinstance(details, dict) else {},
        )


def _quote(value: str) -> str:
    return "'" + str(value).replace("\\", "").replace("'", "") + "'"


def _walk(value: object):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value: yield from _walk(child)


def _text_value(value: object) -> str:
    if isinstance(value, dict): return plain(value.get("#text") or value.get("text") or value.get("value"))
    return plain(value)


def _flat_text(value: object) -> str:
    if isinstance(value, list): return ", ".join(plain(item) for item in value if plain(item))
    return plain(value)


def _first_matching(details: object, *needles: str) -> str:
    for key, value in _walk(details):
        simplified = key.lower().replace(":", "").replace("_", "")
        if any(needle in simplified for needle in needles):
            text = _text_value(value)
            if text: return text
    return ""


def _cpv_codes(details: object) -> list[str]:
    found = []
    for key, value in _walk(details):
        simplified = key.lower().replace(":", "")
        if "cpv" in simplified or "itemclassificationcode" in simplified:
            candidate = _text_value(value)
            if candidate and any(char.isdigit() for char in candidate): found.append(candidate)
    return list(dict.fromkeys(found))


def _estimated_amount(details: object) -> float | None:
    values = []
    for key, value in _walk(details):
        low = key.lower()
        if ("estimated" in low or "valeur" in low) and ("amount" in low or "value" in low or "montant" in low):
            try: values.append(float(_text_value(value).replace(" ", "").replace(",", ".")))
            except ValueError: pass
    return max(values) if values else None


def _postcode(details: object) -> str:
    return _first_matching(details, "postalzone", "codepostal")


def _location(details: object) -> str:
    city = _first_matching(details, "cityname", "ville", "commune")
    postcode = _postcode(details)
    return " ".join(part for part in (postcode, city) if part)


def _duration(details: object) -> str:
    value = _first_matching(details, "durationmeasure", "duree")
    return f"{value} mois" if value.isdigit() else value


def _lot_titles(details: object) -> list[str]:
    titles = []
    for key, value in _walk(details):
        simplified = key.lower().replace(":", "").replace("_", "")
        if simplified.endswith("name") and "lot" in simplified:
            text = _text_value(value)
            if text: titles.append(text)
    return list(dict.fromkeys(titles))[:20]


def _document_urls(details: object) -> list[str]:
    urls = []
    for _, value in _walk(details):
        text = _text_value(value)
        if text.startswith(("https://", "http://")) and ("document" in text.lower() or "march" in text.lower()):
            urls.append(text)
    return list(dict.fromkeys(urls))[:20]
