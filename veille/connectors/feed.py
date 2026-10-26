from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..models import Tender
from ..text import parse_datetime, plain
from .base import Connector, ConnectorError


class FeedConnector(Connector):
    """Connector for an approved RSS, Atom, or JSON source feed.

    JSON items may use the normalized Tender field names. This allows an approved
    source adapter to be added without changing scoring or persistence.
    """
    def fetch(self, since: datetime) -> list[Tender]:
        url = plain(self.source.get("url"))
        if not url: raise ConnectorError("URL de flux non configurée")
        try:
            with urlopen(Request(url, headers={"User-Agent": "BAHO-veille/0.1"}), timeout=30) as response:
                body, content_type = response.read(), response.headers.get("Content-Type", "")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ConnectorError(f"Flux indisponible: {exc}") from exc
        if "json" in content_type or body.lstrip().startswith((b"{", b"[")):
            return self._json(body, since)
        return self._xml(body, since)

    def _json(self, body: bytes, since: datetime) -> list[Tender]:
        decoded = json.loads(body)
        rows = decoded.get("results", decoded.get("items", decoded)) if isinstance(decoded, dict) else decoded
        return [t for row in rows if (t := self._row(row)) and (not t.published_at or t.published_at >= since)]

    def _xml(self, body: bytes, since: datetime) -> list[Tender]:
        try: root = ET.fromstring(body)
        except ET.ParseError as exc: raise ConnectorError(f"Flux XML invalide: {exc}") from exc
        items = root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry")
        rows = []
        for item in items:
            data = {child.tag.rsplit("}", 1)[-1]: child.text or "" for child in item}
            link = item.find("link")
            if link is None: link = item.find("{http://www.w3.org/2005/Atom}link")
            if link is not None: data["url"] = link.get("href") or link.text or ""
            rows.append(data)
        return [t for row in rows if (t := self._row(row)) and (not t.published_at or t.published_at >= since)]

    def _row(self, row: dict) -> Tender | None:
        title = plain(row.get("title") or row.get("objet"))
        identifier = plain(row.get("id") or row.get("guid") or row.get("reference") or row.get("url"))
        if not title or not identifier: return None
        cpv = row.get("cpvs") or row.get("cpv") or []
        if isinstance(cpv, str): cpv = [x.strip() for x in cpv.replace(";", ",").split(",")]
        documents = row.get("documents", [])
        if isinstance(documents, str): documents = [documents]
        if not isinstance(documents, list): documents = []
        return Tender(source=self.name, external_id=identifier, reference=plain(row.get("reference")), title=title,
            description=plain(row.get("description") or row.get("summary")), buyer=plain(row.get("buyer")) or "Non renseigné",
            cpvs=cpv, published_at=parse_datetime(row.get("published_at") or row.get("published") or row.get("pubDate")),
            deadline_at=parse_datetime(row.get("deadline_at") or row.get("deadline")), location=plain(row.get("location")) or "Non renseigné",
            department=plain(row.get("department")), estimate_eur=_amount(row.get("estimate_eur") or row.get("amount")),
            rooms_or_nights=plain(row.get("rooms_or_nights")) or "Non renseigné", documents=[plain(x) for x in documents if plain(x)],
            source_url=plain(row.get("url") or row.get("link")), raw=row)


def _amount(value: object) -> float | None:
    import re
    try:
        number = re.search(r"\d[\d\s.,]*", str(value))
        return float(number.group(0).replace(" ", "").replace(",", ".")) if number else None
    except (TypeError, ValueError): return None
