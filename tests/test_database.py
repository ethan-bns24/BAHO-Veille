from datetime import datetime, timezone
import unittest

from veille.database import Database
from veille.models import ScoredTender, Tender


class DatabaseTests(unittest.TestCase):
    def test_same_reference_is_deduplicated_and_changed_deadline_updates(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            from pathlib import Path
            db = Database(Path(directory) / "watch.sqlite3")
            db.initialize()
            tender = Tender(source="boamp", external_id="26-1", reference="folder-1", title="Hébergement de groupe", buyer="Ville A",
                            deadline_at=datetime(2026, 11, 1, tzinfo=timezone.utc))
            first = db.upsert(ScoredTender(tender, 70, ["test"], ["hébergement"], True))
            second = db.upsert(ScoredTender(tender, 70, ["test"], ["hébergement"], True))
            self.assertEqual(first.event, "created")
            self.assertEqual(second.event, "unchanged")
            tender.deadline_at = datetime(2026, 11, 3, tzinfo=timezone.utc)
            changed = db.upsert(ScoredTender(tender, 70, ["test"], ["hébergement"], True))
            self.assertEqual(changed.event, "updated")
            self.assertEqual(db.dashboard()["stats"]["total"], 1)
