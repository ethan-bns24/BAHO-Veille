from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .config import Settings
from .connectors import BoampConnector, Connector, ConnectorError, FeedConnector
from .database import Database, version_hash
from .notify import send
from .scoring import score
from .text import normalized

LOG = logging.getLogger(__name__)


def connector_for(source: dict) -> Connector:
    match source.get("kind"):
        case "boamp": return BoampConnector(source)
        case "feed": return FeedConnector(source)
        case other: raise ValueError(f"Type de source non pris en charge: {other}")


class WatchService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.database_path)
        self.db.initialize()

    def run_once(self) -> dict[str, int]:
        since = datetime.now(timezone.utc) - timedelta(days=int(self.settings.app["lookback_days"]))
        summary = {"sources": 0, "fetched": 0, "created": 0, "updated": 0, "alerts_sent": 0, "errors": 0}
        for source in self.settings.sources:
            if not source.get("enabled", False): continue
            summary["sources"] += 1
            try:
                batch = connector_for(source).fetch(since)
                self.db.event("INFO", "source_ok", f"{len(batch)} annonce(s) collectée(s)", source["name"])
            except (ConnectorError, ValueError) as exc:
                LOG.exception("Échec de la source %s", source["name"])
                self.db.event("ERROR", "source_error", str(exc), source["name"])
                summary["errors"] += 1
                continue
            summary["fetched"] += len(batch)
            for tender in _latest_per_source_reference(batch):
                item = score(tender, self.settings.scoring, self.settings.hotels)
                result = self.db.upsert(item)
                if result.event in ("created", "updated"): summary[result.event] += 1
                # A recipient/SMTP configuration can be added after collection. In that
                # case, an already-stored but never-sent opportunity must still alert once.
                if not item.commercial_match or item.score < self.settings.notification["minimum_score"]: continue
                digest = version_hash(item)
                if self.db.notification_exists(result.tender_id, digest): continue
                status, error = send(item, self.settings.recipients)
                self.db.record_notification(result.tender_id, digest, status, self.settings.recipients, error)
                if status == "sent": summary["alerts_sent"] += 1
                elif status == "failed":
                    self.db.event("ERROR", "notification_error", error or "Échec SMTP", tender.source, result.tender_id)
        return summary


def _latest_per_source_reference(batch):
    """Avoid a rectification and its prior BOAMP notice overwriting each other.

    A different platform is deliberately *not* folded here: the database then keeps
    both source links on the same canonical tender.
    """
    selected = {}
    for tender in batch:
        key = (tender.source, normalized(tender.reference) or tender.external_id)
        previous = selected.get(key)
        if previous is None or _notice_order(tender) > _notice_order(previous): selected[key] = tender
    return selected.values()


def _notice_order(tender):
    # BOAMP ids are publication sequence numbers (e.g. 26-103268). The fallback
    # makes custom feeds deterministic without making assumptions about their ids.
    digits = "".join(char for char in tender.external_id if char.isdigit())
    return (tender.published_at or datetime.min.replace(tzinfo=timezone.utc), int(digits or 0), tender.external_id)
