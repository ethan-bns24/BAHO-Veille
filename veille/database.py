from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .models import ScoredTender, UpsertResult
from .text import fingerprint, iso, normalized


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS tenders (
  id INTEGER PRIMARY KEY, canonical_key TEXT NOT NULL UNIQUE, reference TEXT, title TEXT NOT NULL,
  buyer TEXT NOT NULL, description TEXT, cpvs_json TEXT NOT NULL, published_at TEXT, deadline_at TEXT,
  location TEXT, department TEXT, estimate_eur REAL, rooms_or_nights TEXT, documents_json TEXT NOT NULL,
  score INTEGER NOT NULL, reasons_json TEXT NOT NULL, version_hash TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tender_sources (
  id INTEGER PRIMARY KEY, tender_id INTEGER NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
  source TEXT NOT NULL, external_id TEXT NOT NULL, source_url TEXT, first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL, UNIQUE(source, external_id)
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, tender_id INTEGER REFERENCES tenders(id) ON DELETE SET NULL,
  source TEXT, level TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY, tender_id INTEGER NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
  version_hash TEXT NOT NULL, status TEXT NOT NULL, recipients TEXT, error TEXT, sent_at TEXT NOT NULL,
  UNIQUE(tender_id, version_hash)
);
CREATE INDEX IF NOT EXISTS idx_tenders_score ON tenders(score DESC, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenders_deadline ON tenders(deadline_at);
"""

# Colonnes ajoutées après la première mise en service. Elles sont créées à la volée pour
# qu'une base existante continue de fonctionner sans export/import.
ADDED_COLUMNS = {
    "procedure": "TEXT", "notice_kind": "TEXT", "contract_nature": "TEXT", "duration": "TEXT",
    "buyer_profile": "TEXT", "lots_json": "TEXT", "breakdown_json": "TEXT", "dedup_key": "TEXT",
}
ADDED_NOTIFICATION_COLUMNS = {"alert_deadline": "TEXT", "alert_score": "INTEGER"}

# Écart de score à partir duquel une annonce déjà alertée mérite un rappel. En deçà,
# la requalification est visible au tableau de bord sans encombrer la boîte.
SIGNIFICANT_SCORE_GAIN = 15
ADDED_INDEXES = ("CREATE INDEX IF NOT EXISTS idx_tenders_dedup ON tenders(dedup_key)",)


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with closing(self.connect()) as conn:
            conn.executescript(SCHEMA)
            present = {row["name"] for row in conn.execute("PRAGMA table_info(tenders)")}
            for column, kind in ADDED_COLUMNS.items():
                if column not in present:
                    conn.execute(f"ALTER TABLE tenders ADD COLUMN {column} {kind}")
            present = {row["name"] for row in conn.execute("PRAGMA table_info(notifications)")}
            for column, kind in ADDED_NOTIFICATION_COLUMNS.items():
                if column not in present:
                    conn.execute(f"ALTER TABLE notifications ADD COLUMN {column} {kind}")
            for statement in ADDED_INDEXES:
                conn.execute(statement)
            conn.commit()

    def event(self, level: str, kind: str, message: str, source: str | None = None, tender_id: int | None = None) -> None:
        with closing(self.connect()) as conn:
            conn.execute("INSERT INTO events(tender_id,source,level,kind,message,created_at) VALUES(?,?,?,?,?,?)",
                         (tender_id, source, level, kind, message, _now())); conn.commit()

    def upsert(self, item: ScoredTender) -> UpsertResult:
        tender = item.tender
        canonical = _canonical(tender.reference, tender.buyer, tender.title, tender.deadline_at)
        dedup = dedup_key(tender)
        version = version_hash(item)
        now = _now()
        columns = ("reference", "title", "buyer", "description", "cpvs_json", "published_at", "deadline_at",
                   "location", "department", "estimate_eur", "rooms_or_nights", "documents_json", "score",
                   "reasons_json", "procedure", "notice_kind", "contract_nature", "duration", "buyer_profile",
                   "lots_json", "breakdown_json", "dedup_key", "version_hash", "updated_at")
        values = (tender.reference, tender.title, tender.buyer, tender.description, json.dumps(tender.cpvs),
                  iso(tender.published_at), iso(tender.deadline_at), tender.location, tender.department,
                  tender.estimate_eur, tender.rooms_or_nights, json.dumps(tender.documents), item.score,
                  json.dumps(item.reasons, ensure_ascii=False), tender.procedure, tender.notice_kind,
                  tender.contract_nature, tender.duration, tender.buyer_profile,
                  json.dumps(tender.lots, ensure_ascii=False),
                  json.dumps([line.as_dict() for line in item.breakdown], ensure_ascii=False), dedup, version, now)
        with closing(self.connect()) as conn:
            existing = conn.execute("SELECT id, version_hash FROM tenders WHERE canonical_key=?", (canonical,)).fetchone()
            if existing is None and dedup:
                # Le même marché publié sur deux plateformes porte deux références.
                # On le regroupe sur l'intitulé et l'échéance, en conservant les deux liens.
                existing = conn.execute(
                    "SELECT id, version_hash FROM tenders WHERE dedup_key=? ORDER BY id LIMIT 1", (dedup,)).fetchone()
                if existing is not None:
                    conn.execute("INSERT INTO events(tender_id,source,level,kind,message,created_at) VALUES(?,?,?,?,?,?)",
                        (existing["id"], tender.source, "INFO", "merged",
                         f"Doublon inter-plateformes rattaché: {tender.source} {tender.external_id}", now))
            if existing is None:
                placeholders = ",".join("?" for _ in range(len(columns) + 2))
                cursor = conn.execute(
                    f"INSERT INTO tenders(canonical_key,{','.join(columns)},created_at) VALUES({placeholders})",
                    (canonical, *values, now))
                tender_id, event = cursor.lastrowid, "created"
            elif existing["version_hash"] != version:
                tender_id, event = existing["id"], "updated"
                assignments = ",".join(f"{column}=?" for column in columns)
                conn.execute(f"UPDATE tenders SET {assignments} WHERE id=?", (*values, tender_id))
            else:
                tender_id, event = existing["id"], "unchanged"
                # Les règles et les implantations peuvent changer sans que l'avis bouge.
                # On rafraîchit le classement sans re-notifier l'équipe commerciale.
                conn.execute("UPDATE tenders SET score=?, reasons_json=?, breakdown_json=? WHERE id=?",
                             (item.score, json.dumps(item.reasons, ensure_ascii=False),
                              json.dumps([line.as_dict() for line in item.breakdown], ensure_ascii=False), tender_id))
            source_insert = conn.execute(
                "INSERT OR IGNORE INTO tender_sources(tender_id,source,external_id,source_url,first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?)",
                (tender_id, tender.source, tender.external_id, tender.source_url, now, now))
            source_added = source_insert.rowcount > 0
            conn.execute("UPDATE tender_sources SET last_seen_at=?, source_url=? WHERE source=? AND external_id=?",
                         (now, tender.source_url, tender.source, tender.external_id))
            if event != "unchanged":
                conn.execute("INSERT INTO events(tender_id,source,level,kind,message,created_at) VALUES(?,?,?,?,?,?)",
                    (tender_id, tender.source, "INFO", event, f"Annonce {event}: {tender.title}", now))
            conn.commit()
        return UpsertResult(tender_id, event, source_added)

    def should_notify(self, tender_id: int, deadline: datetime | None, score: int) -> bool:
        """Décide si une annonce déjà vue mérite une nouvelle alerte.

        Le critère ne peut pas être l'empreinte de l'avis : un même marché publié sur deux
        plateformes arrive avec deux descriptions, deux références et deux montants, donc
        deux empreintes — et déclencherait deux alertes pour une seule opportunité.

        On s'en tient à ce que le brief qualifie de motif de renvoi et qui ne dépend pas de
        la source : un changement d'échéance, ou une requalification nettement à la hausse.
        Le reste se consulte au tableau de bord.
        """
        with closing(self.connect()) as conn:
            sent = conn.execute(
                """SELECT alert_deadline, alert_score FROM notifications
                   WHERE tender_id=? AND status='sent' ORDER BY sent_at DESC""", (tender_id,)).fetchall()
        if not sent:
            return True
        # Les alertes antérieures à ces deux champs ne portent ni échéance ni score. On ne
        # les rejoue sur aucun des deux motifs, sinon le correctif provoquerait lui-même
        # la rafale de renvois qu'il est censé supprimer.
        last_deadline = sent[0]["alert_deadline"]
        if last_deadline and _day(last_deadline) != _day(iso(deadline)):
            return True
        scores = [row["alert_score"] for row in sent if row["alert_score"] is not None]
        if not scores:
            return False
        return score >= max(scores) + SIGNIFICANT_SCORE_GAIN

    def record_notification(self, tender_id: int, version_hash: str, status: str, recipients: list[str],
                            error: str | None = None, deadline: datetime | None = None, score: int = 0) -> None:
        with closing(self.connect()) as conn:
            conn.execute("""INSERT INTO notifications(tender_id,version_hash,status,recipients,error,sent_at,alert_deadline,alert_score)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(tender_id,version_hash) DO UPDATE SET status=excluded.status, recipients=excluded.recipients,
                error=excluded.error, sent_at=excluded.sent_at, alert_deadline=excluded.alert_deadline,
                alert_score=excluded.alert_score""",
                (tender_id, version_hash, status, ", ".join(recipients), error, _now(), iso(deadline), score)); conn.commit()

    def clear_notifications(self) -> int:
        """Oublie les alertes déjà envoyées.

        Les annonces et leur classement sont conservés : seul l'historique d'envoi
        disparaît, de sorte que les opportunités au-dessus du seuil soient notifiées à
        nouveau — typiquement après un changement de destinataire.
        """
        with closing(self.connect()) as conn:
            removed = conn.execute("DELETE FROM notifications").rowcount
            conn.execute("INSERT INTO events(tender_id,source,level,kind,message,created_at) VALUES(?,?,?,?,?,?)",
                         (None, "veille", "INFO", "notifications_reset",
                          f"Historique d'envoi purgé ({removed} entrée(s))", _now()))
            conn.commit()
        return removed

    def dashboard(self, limit: int = 200, minimum_score: int = 35) -> dict:
        with closing(self.connect()) as conn:
            rows = conn.execute("""SELECT t.*, GROUP_CONCAT(DISTINCT s.source) AS source_names,
                GROUP_CONCAT(DISTINCT s.source_url) AS source_urls,
                (SELECT status FROM notifications n WHERE n.tender_id=t.id ORDER BY n.sent_at DESC LIMIT 1) AS alert_status
                FROM tenders t LEFT JOIN tender_sources s ON s.tender_id=t.id
                GROUP BY t.id ORDER BY t.score DESC,t.updated_at DESC LIMIT ?""", (limit,)).fetchall()
            health = conn.execute("""SELECT source, level, kind, message, created_at FROM events
                WHERE id IN (SELECT MAX(id) FROM events WHERE source IS NOT NULL GROUP BY source) ORDER BY source""").fetchall()
            stats = conn.execute("""SELECT COUNT(*) AS total,
                SUM(CASE WHEN score >= ? THEN 1 ELSE 0 END) AS relevant,
                SUM(CASE WHEN deadline_at > ? THEN 1 ELSE 0 END) AS open_tenders,
                MAX(updated_at) AS last_update FROM tenders""", (minimum_score, _now())).fetchone()
            alerts = conn.execute("SELECT COUNT(*) AS sent FROM notifications WHERE status='sent'").fetchone()
        payload = dict(stats)
        payload["threshold"] = minimum_score
        payload["alerts"] = alerts["sent"] or 0
        return {"tenders": [_row(row) for row in rows], "health": [_row(row) for row in health], "stats": payload}

    def recent_events(self, limit: int = 40) -> list[dict]:
        with closing(self.connect()) as conn:
            rows = conn.execute("SELECT level,kind,source,message,created_at FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def tender(self, tender_id: int) -> dict | None:
        with closing(self.connect()) as conn:
            row = conn.execute("""SELECT t.*, GROUP_CONCAT(DISTINCT s.source) AS source_names,
                GROUP_CONCAT(DISTINCT s.source_url) AS source_urls FROM tenders t
                LEFT JOIN tender_sources s ON s.tender_id=t.id WHERE t.id=? GROUP BY t.id""", (tender_id,)).fetchone()
        return _row(row) if row else None


def _canonical(reference: str, buyer: str, title: str, deadline: datetime | None) -> str:
    # A contract folder/reference is authoritative. The fallback is intentionally conservative.
    if reference: return f"ref:{normalized(reference)}"
    return "fallback:" + fingerprint([normalized(buyer), normalized(title), iso(deadline) or ""])


def dedup_key(tender) -> str:
    """Identifie un même marché publié sur plusieurs plateformes.

    L'intitulé normalisé et la date d'échéance suffisent et restent prudents : deux
    consultations distinctes partagent rarement les deux. Sans échéance publiée, on
    n'engage pas de rapprochement.
    """
    title = normalized(tender.title)
    deadline = iso(tender.deadline_at)
    if len(title) < 15 or not deadline: return ""
    return fingerprint(["dedup", title, deadline[:10]])


def version_hash(item: ScoredTender) -> str:
    t = item.tender
    return fingerprint([t.title, t.buyer, t.description, ",".join(sorted(t.cpvs)), iso(t.published_at) or "", iso(t.deadline_at) or "",
                        t.location, str(t.estimate_eur), t.rooms_or_nights, ",".join(t.documents)])


def _day(value: str | None) -> str:
    return (value or "")[:10]


def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _row(row: sqlite3.Row) -> dict:
    out = dict(row)
    for key in ("cpvs_json", "documents_json", "reasons_json", "lots_json", "breakdown_json"):
        if key in out: out[key[:-5]] = json.loads(out.pop(key) or "[]")
    return out
