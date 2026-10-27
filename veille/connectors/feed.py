from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from ..geo import department_from_postcode
from ..http import HttpError, fetch
from ..models import Tender
from ..scoring import detect_buyer_profile, detect_volume
from ..text import parse_datetime, plain
from .base import Connector, ConnectorError

# Noms de champs acceptés sans configuration. Un profil d'acheteur qui nomme ses
# colonnes autrement se branche via `field_map` dans settings.toml, sans toucher au code.
ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "titre", "objet", "intitule", "libelle", "name"),
    "identifier": ("id", "guid", "identifier", "reference", "ref", "key", "url", "link"),
    "reference": ("reference", "ref", "numero", "num_consultation", "contractfolderid"),
    "description": ("description", "summary", "detail", "resume", "objet_complet", "content"),
    "buyer": ("buyer", "acheteur", "personnepublique", "organisme", "entite", "author"),
    "cpvs": ("cpvs", "cpv", "code_cpv", "codescpv"),
    "published_at": ("published_at", "published", "pubDate", "datepubli", "date_publication", "updated", "date"),
    "deadline_at": ("deadline_at", "deadline", "datelim", "date_limite", "datelimitereponse", "date_limite_reponse"),
    "location": ("location", "lieu", "lieu_execution", "ville", "commune", "city"),
    "department": ("department", "departement", "code_departement", "dept"),
    "postcode": ("postcode", "code_postal", "cp", "postalzone"),
    "estimate_eur": ("estimate_eur", "amount", "montant", "montant_estime", "valeur"),
    "rooms_or_nights": ("rooms_or_nights", "volume", "quantite"),
    "documents": ("documents", "document", "pieces", "dce"),
    "url": ("url", "link", "lien", "href"),
    "procedure": ("procedure", "mode", "mode_passation", "type_procedure"),
    "contract_nature": ("contract_nature", "typemarche", "type_marche", "nature", "secteuractivite"),
    "lots": ("lots", "lot"),
}


class FeedConnector(Connector):
    """Connecteur générique pour un flux RSS, Atom, XML ou JSON autorisé.

    Il couvre les plateformes dont le brief demande de vérifier les conditions d'accès
    (PLACE, France Marchés, AWS-Achat, e-marchés publics, Klekoon, profils d'acheteurs
    « xmarches »…). Chacune se branche depuis `settings.toml` en renseignant son URL,
    éventuellement ses identifiants et une correspondance de champs — aucun code à écrire.

    Options reconnues : `url`, `headers`, `username`/`password` (ou `username_env`/
    `password_env`), `item_path` pour un JSON imbriqué, `item_tag` pour un XML non RSS,
    et `field_map` pour renommer les champs.
    """

    def fetch(self, since: datetime) -> list[Tender]:
        url = plain(self.source.get("url"))
        if not url: raise ConnectorError("URL de flux non configurée")
        try:
            body = fetch(url, headers=self.source.get("headers"), timeout=int(self.source.get("timeout", 30)),
                         username=self._secret("username"), password=self._secret("password"))
        except HttpError as exc:
            raise ConnectorError(f"Flux indisponible: {exc}") from exc
        rows = self._json(body) if body.lstrip()[:1] in (b"{", b"[") else self._xml(body)
        tenders = [tender for row in rows if (tender := self._row(row))]
        return [t for t in tenders if not t.published_at or t.published_at >= since]

    def _secret(self, name: str) -> str | None:
        variable = self.source.get(f"{name}_env")
        return os.getenv(variable) if variable else self.source.get(name)

    def _json(self, body: bytes) -> list[dict]:
        try: decoded = json.loads(body)
        except json.JSONDecodeError as exc: raise ConnectorError(f"Flux JSON invalide: {exc}") from exc
        for step in plain(self.source.get("item_path")).split("."):
            if step and isinstance(decoded, dict): decoded = decoded.get(step, [])
        if isinstance(decoded, dict):
            decoded = decoded.get("results") or decoded.get("items") or decoded.get("records") or []
        return [row for row in decoded if isinstance(row, dict)]

    def _xml(self, body: bytes) -> list[dict]:
        try: root = ET.fromstring(body)
        except ET.ParseError as exc: raise ConnectorError(f"Flux XML invalide: {exc}") from exc
        tag = plain(self.source.get("item_tag"))
        if tag: items = root.findall(f".//{tag}")
        else:
            items = root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry")
            # Les exports de profils d'acheteurs (xmarches…) nomment chaque entrée
            # d'après son identifiant : à défaut d'item/entry, on prend les enfants directs.
            if not items: items = list(root)
        rows = []
        for item in items:
            data: dict[str, Any] = {}
            for child in item:
                name = child.tag.rsplit("}", 1)[-1]
                nested = [plain(sub.text) for sub in child if plain(sub.text)]
                data[name] = nested if nested else plain(child.text)
            link = item.find("link") if item.find("link") is not None else item.find("{http://www.w3.org/2005/Atom}link")
            if link is not None: data["url"] = link.get("href") or plain(link.text)
            rows.append(data)
        return rows

    def _row(self, row: dict) -> Tender | None:
        pick = _picker(row, self.source.get("field_map") or {})
        title = pick("title")
        identifier = pick("identifier")
        if not title or not identifier: return None
        buyer = pick("buyer") or "Non renseigné"
        description = pick("description")
        lots = _as_list(pick("lots", raw=True))
        postcode = pick("postcode")
        department = pick("department") or department_from_postcode(postcode)
        return Tender(
            source=self.name, external_id=identifier, reference=pick("reference"), title=title,
            description=description, buyer=buyer, buyer_profile=detect_buyer_profile(buyer),
            cpvs=_codes(pick("cpvs", raw=True)),
            published_at=parse_datetime(pick("published_at")), deadline_at=parse_datetime(pick("deadline_at")),
            location=pick("location") or (f"{postcode}".strip() or "Non renseigné"),
            department=department, estimate_eur=_amount(pick("estimate_eur")),
            rooms_or_nights=pick("rooms_or_nights") or detect_volume(f"{title} {description} {' '.join(lots)}"),
            documents=[plain(x) for x in _as_list(pick("documents", raw=True)) if plain(x)],
            source_url=pick("url"), procedure=pick("procedure"), contract_nature=pick("contract_nature"),
            lots=lots, raw=row,
        )


def _picker(row: dict, field_map: dict):
    lowered = {str(key).lower(): value for key, value in row.items()}

    def pick(field: str, raw: bool = False):
        names = [field_map[field]] if field in field_map else list(ALIASES.get(field, (field,)))
        for name in names:
            value = lowered.get(str(name).lower())
            if value not in (None, "", []):
                return value if raw else plain(value if not isinstance(value, list) else value[0])
        return [] if raw else ""
    return pick


def _as_list(value) -> list[str]:
    if value in (None, ""): return []
    if isinstance(value, list): return [plain(item) for item in value if plain(item)]
    return [plain(value)]


def _codes(value) -> list[str]:
    codes = []
    for item in _as_list(value):
        codes.extend(part.strip() for part in item.replace(";", ",").split(",") if part.strip())
    return list(dict.fromkeys(codes))


def _amount(value: object) -> float | None:
    import re
    match = re.search(r"\d[\d\s .,]*", str(value or ""))
    if not match: return None
    cleaned = match.group(0).replace(" ", "").replace(" ", "").replace(",", ".")
    try: return float(cleaned)
    except ValueError: return None
