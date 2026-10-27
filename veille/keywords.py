"""Ciblage commercial par défaut.

Ces listes sont les valeurs de repli : `settings.toml` (section `[targeting]`) et les
ajustements faits depuis le tableau de bord les remplacent sans toucher au code.
"""

from __future__ import annotations

# Codes CPV du brief : correspondance directe avec le coeur de métier BAHO.
PRIMARY_CPVS: tuple[str, ...] = (
    "55100000",  # Services d'hôtellerie
    "55110000",  # Services d'hébergement hôtelier
    "55120000",  # Réunions et conférences organisées dans des hôtels
    "55130000",  # Autres services d'hôtellerie
    "55270000",  # Chambres avec petit-déjeuner
)

# Codes CPV périphériques : pertinents mais non décisifs (demi-pondération).
SECONDARY_CPVS: tuple[str, ...] = (
    "55000000",  # Services d'hôtellerie, de restauration et de commerce au détail
    "55200000",  # Terrains de camping et autres hébergements non hôteliers
    "55210000",  # Services d'auberges de jeunesse
    "55240000",  # Centres et villages de vacances
    "55250000",  # Location de logements de courte durée
    "55300000",  # Services de restaurant et services de personnel en salle
    "55310000",  # Services de restaurant
    "55320000",  # Services de distribution de repas
    "55520000",  # Services traiteur
    "55900000",  # Services de commerce au détail
    "60000000",  # Transport (déplacements de délégations groupées)
    "63510000",  # Services d'agences de voyages
    "79951000",  # Organisation de séminaires
    "79952000",  # Services d'organisation d'événements
    "79952100",  # Organisation d'événements culturels
    "98341000",  # Services d'hébergement
)

HOTEL_KEYWORDS: tuple[str, ...] = (
    # Hébergement hôtelier — vocabulaire du brief
    "hébergement hôtelier", "hébergement en hôtel", "hébergement hotelier",
    "réservation d'hôtel", "réservation hotel", "réservation de chambres", "réservation de chambre",
    "réservation hôtelière", "nuitée", "nuitées", "allotement de chambres", "allotement hôtelier",
    "hébergement de groupes", "hébergement professionnel", "hébergement temporaire",
    "hébergement de délégations", "hébergement de personnel", "hébergement de personnels",
    "prestations d'hébergement", "prestation d'hébergement", "service d'hébergement",
    "services d'hébergement", "référencement hôtelier", "accord-cadre hébergement",
    # Variantes rencontrées dans les avis publiés
    "mise à l'abri", "hébergement d'urgence", "hébergement collectif", "chambres d'hôtel",
    "nuitées hôtelières", "capacité hôtelière", "marché d'hébergement", "logement temporaire",
    "hébergement des stagiaires", "hébergement des agents", "hébergement des participants",
    "hébergement et transport", "séjour", "séjours", "centrale de réservation",
    "prestations hôtelières", "prestation hôtelière", "accueil hôtelier",
    # Termes génériques — volontairement faibles, encadrés par les exclusions
    "hôtel", "hôtels", "hôtellerie",
)

SERVICE_KEYWORDS: tuple[str, ...] = (
    "séminaire résidentiel", "séminaire", "séminaires", "journée d'étude", "journées d'étude",
    "salle de réunion", "salles de réunion", "location de salles", "congressiste", "congressistes",
    "congrès", "convention", "conventions", "réunion institutionnelle", "forfait hébergement",
    "petit-déjeuner", "petit déjeuner", "restauration de groupe", "restauration pour groupes",
    "demi-pension", "pension complète", "traiteur", "hébergement et restauration",
    "colloque", "colloques", "assemblée générale", "team building", "séance plénière",
    "pause gourmande", "pauses café", "plateau-repas", "salle de séminaire", "espace de réception",
)

# Un terme générique seul ne doit jamais déclencher une alerte.
BROAD_TERMS: tuple[str, ...] = ("hôtel", "hôtels", "hôtellerie", "séjour", "séjours", "séminaire", "séminaires")

# Emplois institutionnels du mot « hôtel » : historisés, jamais alertés.
EXCLUSIONS: tuple[str, ...] = (
    "hotel de ville", "hotel de la ville", "hotel de police", "hotel de region",
    "hotel du departement", "hotel de la marine", "hotel de la guerre", "hotel des impots",
    "hotel communautaire", "hotel d agglomeration", "hotel des ventes", "hotel dieu",
    "hotel particulier", "ecole hoteliere", "lycee hotelier", "hotel de prefecture",
    "hotel du parlement", "hotel des postes",
)

# Expressions qui, à elles seules, qualifient une opportunité hôtelière.
DECISIVE_SERVICES: tuple[str, ...] = (
    "séminaire résidentiel", "congressiste", "congressistes", "forfait hébergement",
    "hébergement et restauration", "demi-pension", "pension complète",
)

# Acheteurs publics visés par le brief : utilisé pour expliciter le profil dans l'alerte.
BUYER_PROFILES: dict[str, tuple[str, ...]] = {
    "Hôpital / santé": ("centre hospitalier", "chu", "chr", "hopital", "ars", "ehpad", "clinique", "assistance publique"),
    "Université / enseignement": ("universite", "rectorat", "academie", "crous", "ecole nationale", "institut national", "lycee", "college"),
    "Collectivité territoriale": ("commune", "mairie", "ville de", "departement", "conseil departemental", "conseil regional", "region", "metropole", "communaute de communes", "communaute d agglomeration", "syndicat mixte"),
    "État / administration": ("ministere", "prefecture", "prefet", "direction departementale", "direction regionale", "sgami", "sgar", "deets", "ddets", "drihl", "service departemental"),
    "Défense / sécurité": ("armee", "defense", "gendarmerie", "police nationale", "sdis", "marine nationale"),
    "Opérateur public / autre": ("office public", "etablissement public", "agence", "sncf", "ratp", "la poste", "pole emploi", "france travail"),
}
