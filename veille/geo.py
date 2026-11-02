"""Correspondances géographiques utilisées pour le score « zone BAHO ».

La table NUTS 3 -> département est dérivée de la nomenclature officielle Eurostat
NUTS 2021, croisée par libellé exact avec la liste INSEE des départements. Elle sert
aux sources européennes (TED) qui ne publient que le code NUTS du lieu d'exécution.
"""

from __future__ import annotations

import re

NUTS3_TO_DEPARTMENT: dict[str, str] = {
    "FR101": "75", "FR102": "77", "FR103": "78", "FR104": "91", "FR105": "92", "FR106": "93",
    "FR107": "94", "FR108": "95", "FRB01": "18", "FRB02": "28", "FRB03": "36", "FRB04": "37",
    "FRB05": "41", "FRB06": "45", "FRC11": "21", "FRC12": "58", "FRC13": "71", "FRC14": "89",
    "FRC21": "25", "FRC22": "39", "FRC23": "70", "FRC24": "90", "FRD11": "14", "FRD12": "50",
    "FRD13": "61", "FRD21": "27", "FRD22": "76", "FRE11": "59", "FRE12": "62", "FRE21": "02",
    "FRE22": "60", "FRE23": "80", "FRF11": "67", "FRF12": "68", "FRF21": "08", "FRF22": "10",
    "FRF23": "51", "FRF24": "52", "FRF31": "54", "FRF32": "55", "FRF33": "57", "FRF34": "88",
    "FRG01": "44", "FRG02": "49", "FRG03": "53", "FRG04": "72", "FRG05": "85", "FRH01": "22",
    "FRH02": "29", "FRH03": "35", "FRH04": "56", "FRI11": "24", "FRI12": "33", "FRI13": "40",
    "FRI14": "47", "FRI15": "64", "FRI21": "19", "FRI22": "23", "FRI23": "87", "FRI31": "16",
    "FRI32": "17", "FRI33": "79", "FRI34": "86", "FRJ11": "11", "FRJ12": "30", "FRJ13": "34",
    "FRJ14": "48", "FRJ15": "66", "FRJ21": "09", "FRJ22": "12", "FRJ23": "31", "FRJ24": "32",
    "FRJ25": "46", "FRJ26": "65", "FRJ27": "81", "FRJ28": "82", "FRK11": "03", "FRK12": "15",
    "FRK13": "43", "FRK14": "63", "FRK21": "01", "FRK22": "07", "FRK23": "26", "FRK24": "38",
    "FRK25": "42", "FRK26": "69", "FRK27": "73", "FRK28": "74", "FRL01": "04", "FRL02": "05",
    "FRL03": "06", "FRL04": "13", "FRL05": "83", "FRL06": "84", "FRM01": "2A", "FRM02": "2B",
    "FRY10": "971", "FRY20": "972", "FRY30": "973", "FRY40": "974", "FRY50": "976",
}

# Les codes postaux d'outre-mer tiennent sur trois chiffres (971xx a 978xx).
OVERSEAS_PREFIXES = ("971", "972", "973", "974", "975", "976", "977", "978")


def department_from_postcode(postcode: str) -> str:
    """Code département déduit d'un code postal français, ou chaîne vide."""
    digits = "".join(character for character in str(postcode) if character.isdigit())
    if len(digits) < 2:
        return ""
    if digits.startswith(OVERSEAS_PREFIXES):
        return digits[:3]
    # La Corse partage le préfixe postal 20 : 2A/2B n'est pas déductible sans la commune.
    return digits[:2]


def department_from_nuts(code: str) -> str:
    """Code département correspondant à un code NUTS 3 français."""
    return NUTS3_TO_DEPARTMENT.get(str(code).strip().upper(), "")


def departments_from_nuts(codes: list[str]) -> list[str]:
    found: list[str] = []
    for code in codes:
        department = department_from_nuts(code)
        if department and department not in found:
            found.append(department)
    return found


# Régions administratives (découpage 2016). Sert à ne retenir que les annonces situées
# dans une région où BAHO exploite au moins un établissement.
REGION_DEPARTMENTS: dict[str, tuple[str, ...]] = {
    "Auvergne-Rhône-Alpes": ("01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"),
    "Bourgogne-Franche-Comté": ("21", "25", "39", "58", "70", "71", "89", "90"),
    "Bretagne": ("22", "29", "35", "56"),
    "Centre-Val de Loire": ("18", "28", "36", "37", "41", "45"),
    "Corse": ("2A", "2B", "20"),
    "Grand Est": ("08", "10", "51", "52", "54", "55", "57", "67", "68", "88"),
    "Hauts-de-France": ("02", "59", "60", "62", "80"),
    "Île-de-France": ("75", "77", "78", "91", "92", "93", "94", "95"),
    "Normandie": ("14", "27", "50", "61", "76"),
    "Nouvelle-Aquitaine": ("16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"),
    "Occitanie": ("09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"),
    "Pays de la Loire": ("44", "49", "53", "72", "85"),
    "Provence-Alpes-Côte d'Azur": ("04", "05", "06", "13", "83", "84"),
    "Outre-mer": OVERSEAS_PREFIXES,
}
DEPARTMENT_REGION: dict[str, str] = {
    department: region for region, departments in REGION_DEPARTMENTS.items() for department in departments
}

# TED publie parfois un NUTS de niveau région (« FRM0 », « FRY1 ») sans département.
NUTS_PREFIX_REGION: dict[str, str] = {
    "FR1": "Île-de-France", "FRB": "Centre-Val de Loire", "FRC": "Bourgogne-Franche-Comté",
    "FRD": "Normandie", "FRE": "Hauts-de-France", "FRF": "Grand Est", "FRG": "Pays de la Loire",
    "FRH": "Bretagne", "FRI": "Nouvelle-Aquitaine", "FRJ": "Occitanie", "FRK": "Auvergne-Rhône-Alpes",
    "FRL": "Provence-Alpes-Côte d'Azur", "FRM": "Corse", "FRY": "Outre-mer",
}
NUTS_PATTERN = re.compile(r"\bFR[0-9A-Z]{1,3}\b")


def normalize_department(code: str) -> str:
    """« 6 » -> « 06 », « 20A » -> « 2A » : les sources ne formatent pas le code pareil."""
    value = str(code).strip().upper()
    if value in ("20A", "20B"): return "2" + value[-1]
    if value.isdigit() and len(value) == 1: return value.zfill(2)
    return value


def region_of_department(code: str) -> str:
    return DEPARTMENT_REGION.get(normalize_department(code), "")


def regions_of(departments) -> set[str]:
    return {region for code in departments if (region := region_of_department(code))}


def tender_regions(department: str, location: str = "") -> set[str]:
    """Régions citées par une annonce, d'après ses départements ou, à défaut, ses codes NUTS."""
    found = regions_of(part for part in str(department).split(",") if part.strip())
    if not found:
        found = {NUTS_PREFIX_REGION[code[:3]] for code in NUTS_PATTERN.findall(str(location).upper())
                 if code[:3] in NUTS_PREFIX_REGION}
    return found


def in_regions(department: str, location: str, allowed: set[str]) -> bool:
    """Vrai si l'annonce touche une région autorisée.

    Un lieu non publié ne vaut pas exclusion : l'annonce est conservée et qualifiée.
    """
    if not allowed: return True
    found = tender_regions(department, location)
    return not found or bool(found & allowed)
