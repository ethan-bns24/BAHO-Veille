import json
import tempfile
import unittest
from pathlib import Path

from veille.config import load_settings
from veille.web import _validate

TOML = """
[app]
database_path = "veille.sqlite3"
poll_interval_minutes = 30
lookback_days = 5
[notification]
minimum_score = 35
recipients = ["a@b.c"]
[scoring]
keyword_weight = 30
geography_weight = 15
amount_weight = 15
deadline_weight = 15
information_weight = 10
service_weight = 15
minimum_response_days = 5
interesting_amount_eur = 20000
[[sources]]
name = "boamp"
kind = "boamp"
enabled = true
[[sources]]
name = "place"
kind = "feed"
enabled = false
url = ""
"""


class LiveSettingsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "settings.toml"
        self.path.write_text(TOML, encoding="utf-8")
        self.settings = load_settings(self.path)

    def tearDown(self):
        self.dir.cleanup()

    def test_overrides_do_not_rewrite_the_versioned_file(self):
        before = self.path.read_text(encoding="utf-8")
        updated = self.settings.apply({"notification.minimum_score": 55})
        self.assertEqual(55, updated.notification["minimum_score"])
        self.assertEqual(before, self.path.read_text(encoding="utf-8"))

    def test_a_new_process_sees_the_change(self):
        self.settings.apply({"scoring.keyword_weight": 40})
        self.assertEqual(40, load_settings(self.path).scoring["keyword_weight"])

    def test_a_source_can_be_enabled_and_pointed_at_a_feed(self):
        updated = self.settings.apply({"sources": {"place": {"enabled": True, "url": "https://example.test/rss"}}})
        place = next(s for s in updated.sources if s["name"] == "place")
        self.assertTrue(place["enabled"])
        self.assertEqual("https://example.test/rss", place["url"])
        self.assertEqual("feed", place["kind"], "le type défini dans settings.toml doit survivre")

    def test_reset_restores_the_file_values(self):
        self.settings.apply({"notification.minimum_score": 90}).reset()
        self.assertEqual(35, load_settings(self.path).notification["minimum_score"])

    def test_targeting_lists_are_editable_and_fall_back_to_defaults(self):
        self.assertGreater(len(self.settings.targeting["hotel_keywords"]), 10)
        updated = self.settings.apply({"targeting.hotel_keywords": ["nuitée"]})
        self.assertEqual(["nuitée"], updated.targeting["hotel_keywords"])


class ValidationTests(unittest.TestCase):
    def test_rejects_unknown_keys(self):
        with self.assertRaises(ValueError):
            _validate({"app.database_path": "/etc/passwd"})

    def test_rejects_out_of_range_values(self):
        with self.assertRaises(ValueError):
            _validate({"notification.minimum_score": 500})

    def test_accepts_a_textarea_as_a_list(self):
        self.assertEqual(["a", "b"], _validate({"targeting.hotel_keywords": "a\n \nb\n"})["targeting.hotel_keywords"])

    def test_source_patches_are_bounded(self):
        patch = _validate({"sources": {"boamp": {"enabled": "yes", "limit": 99999, "secret": "x"}}})
        self.assertEqual({"enabled": True, "limit": 5000}, patch["sources"]["boamp"])


if __name__ == "__main__":
    unittest.main()


class PacingTests(unittest.TestCase):
    """L'étalement des envois : le bot ne doit jamais partir en rafale."""

    def _settings(self, interval, budget):
        from veille.config import Settings
        return Settings(Path("settings.toml"),
                        {"app": {"database_path": "x"}, "scoring": {},
                         "notification": {"send_interval_seconds": interval, "max_alerts_per_cycle": budget}})

    def test_the_first_alert_of_a_cycle_does_not_wait(self):
        from veille.service import _Pacing
        import time
        pacing = _Pacing(self._settings(600, 10))
        started = time.monotonic()
        pacing.wait()
        self.assertLess(time.monotonic() - started, 0.2)

    def test_the_following_alerts_are_spaced_out(self):
        from veille.service import _Pacing
        import time
        pacing = _Pacing(self._settings(1, 10))
        pacing.record("sent")
        started = time.monotonic()
        pacing.wait()
        self.assertGreaterEqual(time.monotonic() - started, 0.5)

    def test_the_cycle_budget_defers_the_remaining_alerts(self):
        from veille.service import _Pacing
        pacing = _Pacing(self._settings(0, 2))
        self.assertFalse(pacing.exhausted)
        pacing.record("sent"); pacing.record("sent")
        self.assertTrue(pacing.exhausted)

    def test_a_failed_send_also_spaces_the_next_attempt(self):
        from veille.service import _Pacing
        import time
        pacing = _Pacing(self._settings(1, 10))
        pacing.record("failed")
        started = time.monotonic()
        pacing.wait()
        self.assertGreaterEqual(time.monotonic() - started, 0.5)
        self.assertFalse(pacing.exhausted, "un échec ne doit pas consommer le quota du cycle")

    def test_a_skipped_send_does_not_stall_the_cycle(self):
        from veille.service import _Pacing
        import time
        pacing = _Pacing(self._settings(600, 10))
        pacing.record("skipped_no_smtp")
        started = time.monotonic()
        pacing.wait()
        self.assertLess(time.monotonic() - started, 0.2)

    def test_pacing_is_adjustable_from_the_dashboard(self):
        from veille.web import _validate
        patch = _validate({"notification.send_interval_seconds": 300, "notification.max_alerts_per_cycle": 5})
        self.assertEqual(300, patch["notification.send_interval_seconds"])
        with self.assertRaises(ValueError):
            _validate({"notification.send_interval_seconds": 99999})

    def test_a_configuration_without_pacing_keeps_safe_defaults(self):
        from veille.config import Settings
        settings = Settings(Path("settings.toml"), {"app": {}, "scoring": {}, "notification": {"minimum_score": 35}})
        self.assertGreater(settings.notification["send_interval_seconds"], 0)
        self.assertGreater(settings.notification["max_alerts_per_cycle"], 0)


class NotificationResetTests(unittest.TestCase):
    def test_clearing_the_history_keeps_the_tenders(self):
        import tempfile
        from veille.cli import sample_alert
        from veille.database import Database, version_hash
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "v.sqlite3")
            db.initialize()
            item = sample_alert()
            result = db.upsert(item)
            digest = version_hash(item)
            deadline = item.tender.deadline_at
            db.record_notification(result.tender_id, digest, "sent", ["a@b.c"],
                                   deadline=deadline, score=item.score)
            self.assertFalse(db.should_notify(result.tender_id, deadline, item.score))

            self.assertEqual(1, db.clear_notifications())

            self.assertTrue(db.should_notify(result.tender_id, deadline, item.score),
                            "l'opportunité doit pouvoir être notifiée à nouveau")
            self.assertEqual(1, db.dashboard()["stats"]["total"], "l'annonce doit être conservée")


class RenotificationTests(unittest.TestCase):
    """Le garde-fou anti-renvoi doit être neutre vis-à-vis de la plateforme d'origine."""

    def setUp(self):
        import tempfile
        from veille.database import Database
        self.folder = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.folder.name) / "v.sqlite3")
        self.db.initialize()

    def tearDown(self):
        self.folder.cleanup()

    def _store(self, source, title, description, reference, deadline, score=55):
        from veille.database import version_hash
        from veille.models import ScoredTender, Tender
        tender = Tender(source=source, external_id=f"{source}-1", title=title, description=description,
                        reference=reference, buyer="Mairie d'Argenteuil", deadline_at=deadline)
        item = ScoredTender(tender=tender, score=score, reasons=[], keyword_hits=[], commercial_match=True)
        return self.db.upsert(item), item, version_hash(item)

    def test_the_same_market_from_two_platforms_alerts_once(self):
        from datetime import datetime, timezone
        deadline = datetime(2026, 11, 20, 11, 0, tzinfo=timezone.utc)
        boamp, item, digest = self._store("boamp", "Organisation de séjours de vacances",
                                          "Description BOAMP", "8e85e44c-ae66", deadline)
        self.assertTrue(self.db.should_notify(boamp.tender_id, deadline, 55))
        self.db.record_notification(boamp.tender_id, digest, "sent", ["a@b.c"], deadline=deadline, score=55)

        # Même marché, même échéance, mais champs TED différents : aucune seconde alerte.
        ted, _, ted_digest = self._store("ted", "Organisation de séjours de vacances",
                                         "Description TED, bien plus longue", "734177-2026", deadline)
        self.assertEqual(boamp.tender_id, ted.tender_id, "les deux sources doivent être fusionnées")
        self.assertNotEqual(digest, ted_digest, "les empreintes diffèrent bien d'une source à l'autre")
        self.assertFalse(self.db.should_notify(ted.tender_id, deadline, 55),
                         "une seule opportunité ne doit déclencher qu'une seule alerte")

    def test_a_changed_deadline_triggers_a_new_alert(self):
        from datetime import datetime, timezone
        first = datetime(2026, 11, 20, 11, 0, tzinfo=timezone.utc)
        result, item, digest = self._store("boamp", "Hébergement hôtelier annuel", "Objet", "REF-1", first)
        self.db.record_notification(result.tender_id, digest, "sent", ["a@b.c"], deadline=first, score=55)
        moved = datetime(2026, 12, 5, 11, 0, tzinfo=timezone.utc)
        self.assertTrue(self.db.should_notify(result.tender_id, moved, 55))

    def test_a_marginal_score_change_does_not_realert(self):
        from datetime import datetime, timezone
        deadline = datetime(2026, 11, 20, 11, 0, tzinfo=timezone.utc)
        result, item, digest = self._store("boamp", "Hébergement hôtelier annuel", "Objet", "REF-2", deadline)
        self.db.record_notification(result.tender_id, digest, "sent", ["a@b.c"], deadline=deadline, score=55)
        self.assertFalse(self.db.should_notify(result.tender_id, deadline, 60))
        self.assertTrue(self.db.should_notify(result.tender_id, deadline, 75), "une requalification nette alerte")

    def test_legacy_rows_without_a_recorded_deadline_are_not_replayed(self):
        from datetime import datetime, timezone
        import sqlite3
        from contextlib import closing
        deadline = datetime(2026, 11, 20, 11, 0, tzinfo=timezone.utc)
        result, item, digest = self._store("boamp", "Hébergement hôtelier annuel", "Objet", "REF-3", deadline)
        with closing(self.db.connect()) as conn:
            conn.execute("""INSERT INTO notifications(tender_id,version_hash,status,recipients,sent_at)
                            VALUES(?,?,'sent','a@b.c','2026-10-01T00:00:00+00:00')""", (result.tender_id, digest))
            conn.commit()
        self.assertFalse(self.db.should_notify(result.tender_id, deadline, 55))
