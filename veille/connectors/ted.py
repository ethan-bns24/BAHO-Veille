from __future__ import annotations

from datetime import datetime, timezone

from ..geo import department_from_nuts, department_from_postcode, departments_from_nuts
from ..http import HttpError, fetch_json
from ..models import Tender
from ..scoring import detect_buyer_profile, detect_volume
from ..text import parse_datetime, plain
from .base import Connector, ConnectorError

# Types d'avis correspondant à une consultation ouverte ou à venir. Les avis
# d'attribution (« can-… ») sont écartés : ils ne présentent plus d'opportunité.
OPEN_NOTICE_PREFIXES = ("cn-", "pin-", "subco", "qs-", "veat")


class TedConnector(Connector):
    """Connecteur TED (Tenders Electronic Daily), l'édition européenne des marchés publics.

    L'API Expert Search v3 est publique et documentée ; elle apporte des champs que le
    BOAMP ne structure pas (valeur estimée par lot, CPV normalisés, NUTS du lieu
    d'exécution). Elle couvre tous les avis français au-dessus des seuils européens.
    """

    endpoint = "https://api.ted.europa.eu/v3/notices/search"
    fields = [
        "publication-number", "notice-title", "description-proc", "description-lot",
        "organisation-name-buyer", "organisation-city-buyer", "organisation-post-code-buyer",
        "place-of-performance", "deadline-receipt-request", "publication-date",
        "estimated-value-proc", "estimated-value-lot", "classification-cpv",
        "notice-type", "procedure-type", "contract-nature", "document-url-lot",
        "buyer-profile", "links",
    ]

    def fetch(self, since: datetime) -> list[Tender]:
        page_size = min(100, int(self.source.get("page_size", 100)))
        limit = int(self.source.get("limit", 400))
        countries = self.source.get("countries") or ["FRA"]
        query = self._query(since, countries)
        notices, token = [], None
        while len(notices) < limit:
            payload = {"query": query, "limit": min(page_size, limit - len(notices)),
                       "fields": self.fields, "paginationMode": "ITERATION"}
            if token: payload["iterationNextToken"] = token
            try:
                response = fetch_json(self.endpoint, method="POST", payload=payload, timeout=45)
            except HttpError as exc:
                raise ConnectorError(f"TED indisponible: {exc}") from exc
            if not isinstance(response, dict):
                raise ConnectorError("TED: réponse inattendue")
            page = response.get("notices") or []
            notices.extend(page)
            token = response.get("iterationNextToken")
            if not page or not token or len(page) < payload["limit"]: break
        return [tender for notice in notices if (tender := self._to_tender(notice))]

    def _query(self, since: datetime, countries: list[str]) -> str:
        """Recherche par code CPV et par expression ciblée sur le titre et l'objet.

        La recherche plein texte (`FT~`) de TED ratisse aussi les annexes et ramène
        beaucoup de bruit : restreindre aux champs `notice-title` et `description-proc`
        conserve le rappel utile sans noyer le scoring.
        """
        blocks = []
        cpvs = " ".join(str(code) for code in self.source.get("cpvs", ()))
        if cpvs: blocks.append(f"classification-cpv IN ({cpvs})")
        for term in self.source.get("title_terms", ()):
            blocks.append(f'notice-title~("{_safe(term)}")')
        for term in self.source.get("description_terms", ()):
            blocks.append(f'description-proc~("{_safe(term)}")')
        subject = " OR ".join(blocks) or 'notice-title~("hébergement")'
        scope = " OR ".join(f"buyer-country={_safe(country)}" for country in countries)
        days = max(1, (datetime.now(timezone.utc) - since).days + 1)
        return f"({subject}) AND ({scope}) AND publication-date>=today(-{days})"

    def _to_tender(self, notice: dict) -> Tender | None:
        number = plain(notice.get("publication-number"))
        if not number: return None
        title = _language(notice.get("notice-title"))
        description = _language(notice.get("description-proc")) or _language(notice.get("description-lot"))
        buyer = _language(notice.get("organisation-name-buyer")) or "Non renseigné"
        nuts = [code for code in _as_list(notice.get("place-of-performance")) if len(code) > 3]
        departments = departments_from_nuts(nuts)
        postcode = plain(_first(notice.get("organisation-post-code-buyer")))
        if not departments and postcode:
            departments = [department_from_postcode(postcode)]
        departments = [item for item in departments if item]
        city = plain(_first(notice.get("organisation-city-buyer")))
        regions = sorted({department_from_nuts(code) or code for code in nuts})
        url = _html_link(notice.get("links")) or f"https://ted.europa.eu/fr/notice/-/detail/{number}"
        return Tender(
            source=self.name,
            external_id=number,
            reference=number,
            title=_french_title(title) or "Intitulé non renseigné",
            description=description,
            buyer=buyer,
            buyer_profile=detect_buyer_profile(buyer),
            cpvs=sorted({plain(code) for code in _as_list(notice.get("classification-cpv")) if plain(code)}),
            published_at=parse_datetime(plain(notice.get("publication-date"))[:10]),
            deadline_at=parse_datetime(_first(notice.get("deadline-receipt-request"))),
            location=", ".join(filter(None, [city, "/".join(regions)])) or "Non renseigné",
            department=", ".join(departments),
            estimate_eur=_amount(notice),
            rooms_or_nights=detect_volume(f"{title} {description}"),
            documents=[u for u in _as_list(notice.get("document-url-lot")) if plain(u).startswith("http")][:10],
            source_url=url,
            procedure=plain(notice.get("procedure-type")),
            notice_kind=plain(notice.get("notice-type")),
            contract_nature=plain(_first(notice.get("contract-nature"))),
            raw={"publication-number": number, "nuts": nuts, "postcode": postcode},
        )


def _safe(value) -> str:
    """Neutralise les caractères qui casseraient l'expression de recherche TED."""
    return str(value).replace('"', " ").replace("(", " ").replace(")", " ").strip()


def _as_list(value) -> list[str]:
    if value is None: return []
    if isinstance(value, list): return [plain(x) for x in value]
    if isinstance(value, dict):
        out = []
        for item in value.values(): out.extend(_as_list(item))
        return out
    return [plain(value)]


def _first(value):
    items = _as_list(value)
    return items[0] if items else ""


def _language(value) -> str:
    """TED renvoie des dictionnaires multilingues ; le français prime, l'anglais dépanne."""
    if isinstance(value, dict):
        for code in ("fra", "FRA", "fr", "eng", "ENG", "en"):
            if code in value:
                items = _as_list(value[code])
                if items: return items[0]
        for item in value.values():
            items = _as_list(item)
            if items: return items[0]
        return ""
    return _first(value)


def _french_title(title: str) -> str:
    # Les titres TED sont préfixés « France – <CPV> – <objet> ». L'objet suffit.
    parts = [part.strip() for part in title.split("–")]
    return parts[-1] if len(parts) > 2 and parts[-1] else title


def _amount(notice: dict) -> float | None:
    procedure = _numbers(notice.get("estimated-value-proc"))
    if procedure: return max(procedure)
    lots = _numbers(notice.get("estimated-value-lot"))
    return sum(lots) if lots else None


def _numbers(value) -> list[float]:
    found = []
    for item in _as_list(value):
        try: found.append(float(item))
        except (TypeError, ValueError): pass
    return found


def _html_link(links) -> str:
    if not isinstance(links, dict): return ""
    html = links.get("html") or links.get("htmlDirect") or {}
    if isinstance(html, dict):
        for code in ("FRA", "ENG"):
            value = html.get(code)
            if isinstance(value, str) and value.startswith("http"): return value
        for value in html.values():
            if isinstance(value, str) and value.startswith("http"): return value
    return ""
