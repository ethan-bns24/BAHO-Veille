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
            db.record_notification(result.tender_id, digest, "sent", ["a@b.c"])
            self.assertTrue(db.notification_exists(result.tender_id, digest))

            self.assertEqual(1, db.clear_notifications())

            self.assertFalse(db.notification_exists(result.tender_id, digest),
                             "l'opportunité doit pouvoir être notifiée à nouveau")
            self.assertEqual(1, db.dashboard()["stats"]["total"], "l'annonce doit être conservée")
