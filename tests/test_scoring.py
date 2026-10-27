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

    def test_generic_hotel_mention_is_damped_below_threshold(self):
        # « autres que l'hôtel » : la seule mention générique ne doit pas suffire.
        tender = Tender(source="test", external_id="4", title="Nettoyage des réseaux aérauliques autres que l'hôtel",
                        description="Marché de nettoyage technique", location="Lyon", department="69",
                        deadline_at=datetime.now(timezone.utc) + timedelta(days=40), source_url="https://example.test")
        hotels = [{"name": "SH Saint-Fons", "city": "Saint-Fons", "department": "69"}]
        result = score(tender, SETTINGS, hotels)
        self.assertLess(result.score, 35)
        self.assertTrue(any("générique" in reason for reason in result.reasons + [l.detail for l in result.breakdown]))

    def test_geography_scores_only_for_commercial_matches(self):
        tender = Tender(source="test", external_id="5", title="Rénovation de l'Hôtel de Ville",
                        location="Saint-Fons", department="69")
        hotels = [{"name": "SH Saint-Fons", "city": "Saint-Fons", "department": "69"}]
        result = score(tender, SETTINGS, hotels)
        self.assertFalse(result.commercial_match)
        self.assertEqual(0, next(line.points for line in result.breakdown if line.label == "Zone BAHO"))

    def test_breakdown_covers_every_criterion_of_the_brief(self):
        tender = Tender(source="test", external_id="6", title="Hébergement hôtelier pour délégations",
                        cpvs=["55110000"], deadline_at=datetime.now(timezone.utc) + timedelta(days=30))
        labels = [line.label for line in score(tender, SETTINGS, []).breakdown]
        for expected in ("Mots-clés et CPV", "Zone BAHO", "Montant estimé", "Délai de réponse",
                         "Informations disponibles", "Prestations associées"):
            self.assertIn(expected, labels)

    def test_targeting_can_be_overridden_at_runtime(self):
        tender = Tender(source="test", external_id="7", title="Fourniture de yourtes de montagne")
        self.assertFalse(score(tender, SETTINGS, []).commercial_match)
        custom = {"hotel_keywords": ["yourte", "yourtes"], "broad_terms": []}
        self.assertTrue(score(tender, SETTINGS, [], custom).commercial_match)


class VolumeTests(unittest.TestCase):
    def test_extracts_rooms_and_nights(self):
        from veille.scoring import detect_volume
        self.assertEqual("120 chambres · 4 500 nuitées", detect_volume("Marché de 120 chambres et 4 500 nuitées"))

    def test_ignores_unrelated_quantities(self):
        from veille.scoring import detect_volume
        self.assertEqual("Non renseigné", detect_volume("Livraison de 20 000 litres de fioul"))


class BuyerProfileTests(unittest.TestCase):
    def test_recognises_the_buyer_types_listed_in_the_brief(self):
        from veille.scoring import detect_buyer_profile
        self.assertEqual("Hôpital / santé", detect_buyer_profile("Centre Hospitalier de Valence"))
        self.assertEqual("Université / enseignement", detect_buyer_profile("Université de Bourgogne"))
        self.assertEqual("Collectivité territoriale", detect_buyer_profile("Métropole de Lyon"))
