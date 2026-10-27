import unittest
from datetime import datetime, timedelta, timezone

from veille.cli import sample_alert
from veille.notify import build_message


class AlertContentTests(unittest.TestCase):
    """Le brief (section 7) énumère ce que l'alerte doit contenir ; on le vérifie."""

    def setUp(self):
        self.item = sample_alert()
        self.message = build_message(self.item, ["direction@baho.example"], threshold=35)
        self.text = self.message.get_payload(0).get_payload(decode=True).decode()
        self.html = self.message.get_payload(1).get_payload(decode=True).decode()

    def test_subject_carries_the_score_and_the_countdown(self):
        self.assertIn("[BAHO 100/100]", self.message["Subject"])
        self.assertIn("J-", self.message["Subject"])

    def test_both_parts_are_present(self):
        self.assertEqual("multipart/alternative", self.message.get_content_type())
        self.assertEqual("text/plain", self.message.get_payload(0).get_content_type())
        self.assertEqual("text/html", self.message.get_payload(1).get_content_type())

    def test_every_field_required_by_the_brief_appears(self):
        tender = self.item.tender
        for part in (self.text, self.html):
            for expected in (tender.title, tender.buyer, tender.reference, tender.rooms_or_nights,
                             tender.procedure, "55110000"):
                self.assertIn(expected, part, msg=f"{expected!r} absent")

    def test_the_score_detail_section_is_present_in_both_parts(self):
        self.assertIn("Détail du score", self.html)
        self.assertIn("DÉTAIL DU SCORE", self.text)
        self.assertIn("seuil d'alerte fixé à 35/100", self.html)

    def test_score_breakdown_is_explained_line_by_line(self):
        for line in self.item.breakdown:
            self.assertIn(line.label, self.html)
            self.assertIn(f"{line.points}", self.html)

    def test_html_escapes_untrusted_source_content(self):
        item = sample_alert()
        item.tender.title = 'Hébergement <script>alert("x")</script>'
        html = build_message(item, ["a@b.c"]).get_payload(1).get_payload(decode=True).decode()
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_missing_fields_are_labelled_not_hidden(self):
        item = sample_alert()
        item.tender.estimate_eur = None
        item.tender.deadline_at = None
        html = build_message(item, ["a@b.c"]).get_payload(1).get_payload(decode=True).decode()
        self.assertIn("Non renseigné", html)

    def test_an_imminent_deadline_is_flagged_as_a_priority(self):
        item = sample_alert()
        item.tender.deadline_at = datetime.now(timezone.utc) + timedelta(days=3)
        message = build_message(item, ["a@b.c"])
        self.assertIn("priorité", message["Subject"])


class RecipientTests(unittest.TestCase):
    def test_no_recipient_means_no_send_attempt(self):
        from veille.notify import send
        self.assertEqual(("skipped_no_recipients", None), send(sample_alert(), []))


if __name__ == "__main__":
    unittest.main()
