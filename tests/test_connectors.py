import unittest
from datetime import datetime, timezone

from veille.connectors.feed import FeedConnector
from veille.connectors.ted import TedConnector
from veille.geo import department_from_nuts, department_from_postcode

SINCE = datetime(2020, 1, 1, tzinfo=timezone.utc)

TED_NOTICE = {
    "publication-number": "679926-2026",
    "notice-title": {"fra": "France – Services d'hébergement hôtelier – Achat de nuitées d'urgence"},
    "description-proc": {"fra": "Accord-cadre portant sur 2 400 nuitées auprès d'hôteliers."},
    "organisation-name-buyer": {"fra": ["Centre Hospitalier de Bourges"]},
    "organisation-city-buyer": ["Bourges"],
    "organisation-post-code-buyer": ["18000"],
    "place-of-performance": ["FRB01", "FRA"],
    "deadline-receipt-request": ["2026-12-20T17:00:00+01:00"],
    "publication-date": "2026-10-02+02:00",
    "estimated-value-lot": ["108000", "180000"],
    "classification-cpv": ["55110000", "55000000"],
    "notice-type": "cn-standard",
    "procedure-type": "open",
    "contract-nature": ["services"],
    "links": {"html": {"FRA": "https://ted.europa.eu/fr/notice/-/detail/679926-2026"}},
}


class TedParsingTests(unittest.TestCase):
    def setUp(self):
        self.tender = TedConnector({"name": "ted"})._to_tender(TED_NOTICE)

    def test_keeps_the_french_object_without_the_cpv_prefix(self):
        self.assertEqual("Achat de nuitées d'urgence", self.tender.title)

    def test_maps_the_nuts_code_to_a_department(self):
        self.assertEqual("18", self.tender.department)

    def test_sums_the_estimated_value_of_the_lots(self):
        self.assertEqual(288000.0, self.tender.estimate_eur)

    def test_extracts_the_volume_and_the_buyer_profile(self):
        self.assertEqual("2 400 nuitées", self.tender.rooms_or_nights)
        self.assertEqual("Hôpital / santé", self.tender.buyer_profile)

    def test_query_restricts_to_the_requested_countries(self):
        query = TedConnector({"name": "ted", "cpvs": ["55110000"]})._query(SINCE, ["FRA"])
        self.assertIn("classification-cpv IN (55110000)", query)
        self.assertIn("buyer-country=FRA", query)


class FeedParsingTests(unittest.TestCase):
    xml = b"""<?xml version="1.0" encoding="UTF-8"?><marches>
      <marche_1>
        <ref>EET-2026036</ref><titre>Hebergement des stagiaires</titre>
        <detail>Reservation de 60 chambres</detail><typemarche>Services</typemarche>
        <mode>Procedure adaptee</mode><datepubli>18/09/2026</datepubli>
        <datelim>03/11/2026 12:00</datelim>
        <lots><lot>Lot 1</lot><lot>Lot 2</lot></lots>
        <personnepublique>Ville de Vire</personnepublique>
        <url>https://example.test/consultation/1</url>
      </marche_1></marches>"""

    def test_reads_a_buyer_profile_xml_export_without_configuration(self):
        rows = FeedConnector({"name": "profil"})._xml(self.xml)
        tender = FeedConnector({"name": "profil"})._row(rows[0])
        self.assertEqual("Hebergement des stagiaires", tender.title)
        self.assertEqual("Ville de Vire", tender.buyer)
        self.assertEqual(["Lot 1", "Lot 2"], tender.lots)
        self.assertEqual("Procedure adaptee", tender.procedure)
        self.assertEqual("60 chambres", tender.rooms_or_nights)

    def test_field_map_renames_unknown_columns(self):
        row = {"libelle_marche": "Nuitées hôtelières", "cle": "42", "acheteur_public": "CCAS"}
        source = {"name": "custom", "field_map": {"title": "libelle_marche", "identifier": "cle", "buyer": "acheteur_public"}}
        tender = FeedConnector(source)._row(row)
        self.assertEqual("Nuitées hôtelières", tender.title)
        self.assertEqual("CCAS", tender.buyer)

    def test_json_item_path_walks_into_the_payload(self):
        body = b'{"data": {"consultations": [{"title": "Hebergement", "id": "7"}]}}'
        rows = FeedConnector({"name": "api", "item_path": "data.consultations"})._json(body)
        self.assertEqual(1, len(rows))


class GeoTests(unittest.TestCase):
    def test_nuts_and_postcodes_resolve_to_departments(self):
        self.assertEqual("75", department_from_nuts("FR101"))
        self.assertEqual("95", department_from_nuts("FR108"))
        self.assertEqual("972", department_from_nuts("FRY20"))
        self.assertEqual("69", department_from_postcode("69190"))
        self.assertEqual("972", department_from_postcode("97200"))

    def test_unknown_codes_are_empty_rather_than_wrong(self):
        self.assertEqual("", department_from_nuts("DE123"))
        self.assertEqual("", department_from_postcode("x"))


if __name__ == "__main__":
    unittest.main()
