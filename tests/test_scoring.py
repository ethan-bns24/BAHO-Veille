from datetime import datetime, timedelta, timezone
import unittest

from veille.models import Tender
from veille.scoring import score


SETTINGS = {"keyword_weight": 30, "geography_weight": 15, "amount_weight": 15, "deadline_weight": 15,
            "information_weight": 10, "service_weight": 15, "minimum_response_days": 5, "interesting_amount_eur": 20_000}


class ScoringTests(unittest.TestCase):
    def test_hotel_cpv_is_a_commercial_match(self):
        tender = Tender(source="test", external_id="1", title="Prestations d'hôtellerie pour délégation", cpvs=["55110000-4"],
                        deadline_at=datetime.now(timezone.utc) + timedelta(days=12), source_url="https://example.test")
        result = score(tender, SETTINGS, [])
        self.assertTrue(result.commercial_match)
        self.assertGreaterEqual(result.score, 45)
        self.assertTrue(any("CPV" in reason or "mots-clés" in reason for reason in result.reasons))

    def test_hotel_de_ville_is_not_an_alert_candidate(self):
        tender = Tender(source="test", external_id="2", title="Travaux de rénovation de l'Hôtel de Ville", description="Marché de bâtiment")
        result = score(tender, SETTINGS, [])
        self.assertFalse(result.commercial_match)
        self.assertLess(result.score, 35)

    def test_residential_seminar_is_a_commercial_match(self):
        tender = Tender(source="test", external_id="3", title="Organisation d'un séminaire résidentiel de groupe")
        self.assertTrue(score(tender, SETTINGS, []).commercial_match)
