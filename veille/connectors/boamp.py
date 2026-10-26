from __future__ import annotations

import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..models import Tender
from ..text import parse_datetime, plain
from .base import Connector, ConnectorError


class BoampConnector(Connector):
    """Official DILA BOAMP OpenDataSoft API connector."""
    endpoint = "https://www.boamp.fr/api/explore/v2.1/catalog/datasets/boamp/records"

    def fetch(self, since: datetime) -> list[Tender]:
        # Server-side filtering avoids losing a relevant tender when a busy publication
        # day produces more rows than one API page. The date is deliberately widened by
        # the service lookback; local versioning makes the replay harmless.
        limit, offset, rows = int(self.source.get("limit", 500)), 0, []
        where = self._where(since)
        while offset < limit:
            query = urlencode({"limit": min(100, limit - offset), "offset": offset, "order_by": "dateparution desc", "where": where})
            request = Request(f"{self.endpoint}?{query}", headers={"User-Agent": "BAHO-veille/0.1 (+contact-configure)"})
            try:
                with urlopen(request, timeout=30) as response: payload = json.load(response)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise ConnectorError(f"BOAMP indisponible: {exc}") from exc
            page = payload.get("results", [])
            rows.extend(page)
            if len(page) < 100 or offset + len(page) >= payload.get("total_count", 0): break
            offset += len(page)
        return [self._to_tender(row) for row in rows]

    @staticmethod
    def _where(since: datetime) -> str:
        # These are intentionally broad commercial signals; final scoring handles nuance.
        terms = ("hôtel", "hotel", "hébergement", "hebergement", "réservation", "reservation", "nuitée", "nuitee",
                 "séminaire", "seminaire", "congrès", "congres", "convention", "restauration")
        conditions = " OR ".join(f"search(objet, '{term}')" for term in terms)
        return f"nature = 'APPEL_OFFRE' AND dateparution >= date'{since.date().isoformat()}' AND ({conditions})"

    def _to_tender(self, row: dict) -> Tender:
        raw = row.get("donnees") or row.get("DONNEES") or ""
        try: details = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError: details = {}
        description = plain(row.get("objet"))
        codes = _cpv_codes(details)
        reference = plain(row.get("contractfolderid") or row.get("idweb") or row.get("id"))
        url = plain(row.get("url_avis"))
        if url.startswith("/"): url = f"https://www.boamp.fr{url}"
        department = _flat_text(row.get("code_departement_prestation") or row.get("code_departement"))
        return Tender(
            source=self.name,
            external_id=plain(row.get("idweb") or row.get("id") or reference),
            reference=reference,
            title=description or "Intitulé non renseigné",
            description=description,
            buyer=plain(row.get("nomacheteur")) or "Non renseigné",
            cpvs=codes,
            published_at=parse_datetime(row.get("dateparution")),
            deadline_at=parse_datetime(row.get("datelimitereponse")),
            department=department,
            location=department or "Non renseigné",
            source_url=url,
            estimate_eur=_estimated_amount(details),
            documents=_document_urls(details),
            raw=details if isinstance(details, dict) else {},
        )


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
        if "estimated" in low and ("amount" in low or "value" in low):
            try: values.append(float(_text_value(value).replace(",", ".")))
            except ValueError: pass
    return max(values) if values else None


def _document_urls(details: object) -> list[str]:
    urls = []
    for _, value in _walk(details):
        text = _text_value(value)
        if text.startswith(("https://", "http://")) and ("document" in text.lower() or "march" in text.lower()): urls.append(text)
    return list(dict.fromkeys(urls))[:20]
