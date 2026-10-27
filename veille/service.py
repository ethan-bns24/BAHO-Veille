from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from .config import Settings, load_settings
from .connectors import CONNECTORS, Connector, ConnectorError
from .database import Database, version_hash
from .notify import send
from .scoring import score
from .text import normalized

LOG = logging.getLogger(__name__)


def connector_for(source: dict) -> Connector:
    kind = source.get("kind")
    if kind not in CONNECTORS:
        raise ValueError(f"Type de source non pris en charge: {kind}")
    return CONNECTORS[kind](source)


class WatchService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.database_path)
        self.db.initialize()

    def refresh_settings(self) -> Settings:
        """Relit la configuration avant chaque cycle.

        Les réglages modifiés depuis le tableau de bord (seuil, pondérations, mots-clés,
        sources activées) sont ainsi pris en compte sans redémarrer le bot.
        """
        self.settings = load_settings(self.settings.path)
        return self.settings

    def run_once(self) -> dict[str, int]:
        settings = self.refresh_settings()
        since = datetime.now(timezone.utc) - timedelta(days=int(settings.app["lookback_days"]))
        summary = {"sources": 0, "fetched": 0, "created": 0, "updated": 0, "alerts_sent": 0,
                   "alerts_deferred": 0, "errors": 0}
        targeting = settings.targeting
        pacing = _Pacing(settings)
        for source in settings.sources:
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
                item = score(tender, settings.scoring, settings.hotels, targeting)
                result = self.db.upsert(item)
                if result.event in ("created", "updated"): summary[result.event] += 1
                # La configuration SMTP peut arriver après la collecte : une opportunité
                # déjà stockée mais jamais notifiée doit tout de même alerter une fois.
                if not item.commercial_match or item.score < int(settings.notification["minimum_score"]): continue
                digest = version_hash(item)
                if self.db.notification_exists(result.tender_id, digest): continue
                if pacing.exhausted:
                    # Le plafond du cycle est atteint : l'annonce n'est pas notifiée
                    # maintenant, elle le sera au cycle suivant. Rien n'est perdu.
                    summary["alerts_deferred"] += 1
                    continue
                pacing.wait()
                status, error = send(item, settings.recipients, event=result.event, threshold=int(settings.notification["minimum_score"]))
                self.db.record_notification(result.tender_id, digest, status, settings.recipients, error)
                pacing.record(status)
                if status == "sent": summary["alerts_sent"] += 1
                elif status == "failed":
                    self.db.event("ERROR", "notification_error", error or "Échec SMTP", tender.source, result.tender_id)
        self.db.event("INFO", "cycle", " · ".join(f"{key}={value}" for key, value in summary.items()), "veille")
        return summary


class _Pacing:
    """Étale les alertes d'un même cycle.

    Une rafale d'e-mails identiques vers la même boîte est le principal motif de
    classement en indésirable. On laisse respirer entre deux envois et on plafonne le
    nombre d'alertes par cycle ; le reliquat part au cycle suivant.
    """

    def __init__(self, settings):
        self.interval = max(0, int(settings.notification["send_interval_seconds"]))
        self.budget = max(1, int(settings.notification["max_alerts_per_cycle"]))
        self.sent = 0
        self._last: float | None = None

    # Statuts signifiant que le serveur SMTP a réellement été sollicité. Les envois
    # « skipped_* » n'ouvrent aucune connexion : les espacer ferait traîner un cycle
    # entier sans qu'aucun message ne parte.
    CONTACTED = ("sent", "failed")

    @property
    def exhausted(self) -> bool:
        return self.sent >= self.budget

    def wait(self) -> None:
        if self._last is None or not self.interval: return
        remaining = self.interval - (time.monotonic() - self._last)
        if remaining > 0:
            LOG.info("Attente de %.0f s avant la prochaine alerte", remaining)
            time.sleep(remaining)

    def record(self, status: str) -> None:
        # Un échec compte aussi comme une sollicitation : enchaîner les tentatives
        # ratées vers le même serveur est le meilleur moyen de se faire limiter.
        if status in self.CONTACTED: self._last = time.monotonic()
        if status == "sent": self.sent += 1


def _latest_per_source_reference(batch):
    """Évite qu'un rectificatif et l'avis initial du BOAMP s'écrasent mutuellement.

    Une plateforme différente n'est volontairement pas fusionnée ici : la base conserve
    alors les deux liens sources sur la même annonce canonique.
    """
    selected = {}
    for tender in batch:
        key = (tender.source, normalized(tender.reference) or tender.external_id)
        previous = selected.get(key)
        if previous is None or _notice_order(tender) > _notice_order(previous): selected[key] = tender
    return selected.values()


def _notice_order(tender):
    # Les identifiants BOAMP sont des numéros de publication (ex. 26-103268). Le repli
    # rend les flux personnalisés déterministes sans présumer de leur format d'identifiant.
    digits = "".join(char for char in tender.external_id if char.isdigit())
    return (tender.published_at or datetime.min.replace(tzinfo=timezone.utc), int(digits or 0), tender.external_id)
