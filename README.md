# BAHO · veille des appels d’offres

Un bot autonome qui collecte les avis de marchés publics, détecte les opportunités liées à l’hébergement hôtelier, les dédoublonne entre plateformes, les classe et envoie une alerte e-mail explicable. Il est construit à partir du brief fourni.

## Ce qui est opérationnel

- **Deux API publiques officielles branchées et actives** : le BOAMP (open data DILA) et le TED (édition européenne des marchés publics). Aucune clé, aucun compte, aucun scraping.
- **Connecteur de flux générique** : n’importe quel flux RSS, Atom, XML ou JSON autorisé se branche depuis `settings.toml` ou depuis le tableau de bord, sans écrire une ligne de code — y compris les flux protégés par identifiants.
- **Déduplication inter-plateformes** : un même marché publié au BOAMP et au TED est regroupé sur une seule fiche, qui conserve les deux liens sources.
- **Scoring explicable sur 100** et entièrement configurable : adéquation métier, géographie, montant, délai, complétude, prestations associées. Chaque point est justifié ligne par ligne dans l’alerte et dans le tableau de bord.
- **Alerte e-mail HTML** reprenant tous les champs demandés par le brief, avec repli texte, compte à rebours d’échéance et détail du score.
- **Tableau de bord local** permettant de modifier en direct le seuil, les pondérations, les mots-clés, les destinataires et les sources actives.
- **Garde-fous métier** : « hôtel de ville » et consultations de restauration isolées sont historisées sans déclencher d’alerte ; une correspondance purement générique est pondérée à la baisse.
- Historique SQLite, détection des modifications et des échéances changées, journal d’exécution, reprise automatique après erreur réseau, conteneurs Docker.

## Sources

| Source | Type | État | Accès |
|---|---|---|---|
| BOAMP | API open data DILA | **active** | Publique, sans compte |
| TED (Union européenne) | API Expert Search v3 | **active** | Publique, sans compte |
| PLACE (marches-publics.gouv.fr) | Flux RSS | à activer | Compte entreprise requis : le flux d’alerte n’est pas public |
| France Marchés, AWS-Achat, e-marchés publics, Klekoon, Marchés Online | Flux RSS | à activer | Flux lié à un compte, conditions d’utilisation à valider |
| Profils d’acheteurs (exports XML ouverts) | XML | à activer | Public, une URL par acheteur suivi |

Le BOAMP est interrogé côté serveur sur l’objet, le descripteur métier et les codes CPV, pour cinq natures d’avis (avis de marché, rectificatif, modification, pré-information, intention de conclure) : la collecte ne se limite pas aux derniers avis publiés. Le TED apporte en complément la valeur estimée, les codes CPV normalisés et le code NUTS du lieu d’exécution, que le BOAMP ne structure pas ; la table NUTS 3 → département est dérivée de la nomenclature Eurostat 2021.

Les plateformes commerciales n’exposent pas de flux public : leur activation suppose un compte BAHO, une alerte enregistrée sur les mots-clés hôteliers, puis le collage de l’URL fournie dans `settings.toml` ou dans l’onglet « Sources ». Les identifiants passent par variables d’environnement (`username_env` / `password_env`), jamais en clair dans un fichier versionné. Le brief demande explicitement cette vérification des conditions d’accès : rien ne les contourne.

## Démarrage local

Python 3.11+ suffit ; le projet n’a aucune dépendance applicative externe.

```bash
python3 -m veille.cli init-db
python3 -m veille.cli run-once      # une collecte, puis arrêt
python3 -m veille.cli serve         # tableau de bord sur http://127.0.0.1:8080
python3 -m veille.cli run           # veille continue
```

Commandes utiles :

```bash
python3 -m veille.cli sources        # état de configuration de chaque source
python3 -m veille.cli preview-email  # écrit un aperçu HTML de l'alerte, sans rien envoyer
python3 -m veille.cli test-email     # envoie réellement une alerte de test
python3 -m veille.cli reset-alerts   # oublie les alertes déjà envoyées
```

`reset-alerts` supprime l'historique d'envoi sans toucher aux annonces ni à leur classement : les opportunités au-dessus du seuil repartent au cycle suivant. C'est la commande à utiliser après un changement de destinataire. Le même bouton existe dans le tableau de bord.

⚠️ `run-once`, `run` et `test-email` envoient de vrais e-mails dès que `SMTP_HOST` est renseigné dans `.env`. Pour travailler sans rien envoyer, laissez `SMTP_HOST` vide : les notifications sont alors tracées dans la base sans partir.

Avec Docker :

```bash
cp .env.example .env
docker compose up --build -d
```

## Rythme d'envoi

Une rafale d'e-mails quasi identiques vers une même boîte est le premier motif de classement en indésirable. Deux garde-fous, tous deux réglables depuis le tableau de bord :

| Réglage | Défaut | Effet |
|---|---|---|
| `send_interval_seconds` | 120 s | Délai minimum entre deux alertes d'un même cycle |
| `max_alerts_per_cycle` | 12 | Plafond par cycle ; le reliquat part au cycle suivant, rien n'est perdu |

Le résumé de cycle distingue `alerts_sent` des `alerts_deferred`. Un échec SMTP espace lui aussi la tentative suivante, mais ne consomme pas le quota.

Chaque message porte un `Message-ID`, une `Date`, un `Reply-To` joignable, `Auto-Submitted: auto-generated` et une version texte complète en plus du HTML — autant de signaux qui pèsent favorablement dans le classement anti-spam.

⚠️ Un point reste hors du code : l'expéditeur. Envoyer depuis une boîte Gmail personnelle vers un domaine d'entreprise passe l'authentification (Gmail signe en DKIM) mais reste moins bien noté qu'un envoi depuis le domaine du destinataire. Pour une mise en production durable, utiliser le SMTP de `groupe-baho.fr` et y publier les enregistrements SPF et DKIM.

## Régler la veille en direct

Le tableau de bord (`serve`) expose quatre onglets :

- **Opportunités** — toutes les annonces collectées, filtrables par intitulé, score et échéance. Chaque ligne se déplie sur le détail complet et le décompte des points.
- **Sources** — activer ou désactiver une plateforme, renseigner l’URL d’un flux autorisé, consulter l’état du dernier cycle de chaque source.
- **Réglages** — seuil d’alerte, cadence de collecte, rythme d’envoi, profondeur de collecte, les six pondérations, les listes de mots-clés et de codes CPV, les destinataires.
- **Journal** — les événements de collecte, de classement et de notification.

Les modifications sont écrites dans `data/overrides.json` et relues au début de chaque cycle : **aucun redémarrage n’est nécessaire**, et `settings.toml` — versionné et commenté — n’est jamais réécrit. Le bouton « Rétablir settings.toml » supprime les surcharges. Le serveur n’accepte que les clés exposées et vérifie leurs bornes ; il écoute sur `127.0.0.1` par défaut.

## Passage en production

1. Compléter les implantations, capacités et prestations BAHO dans `settings.toml`. La géographie entre alors dans le score.
2. Créer `.env` depuis `.env.example`, définir `ALERT_RECIPIENTS` et les paramètres SMTP.
3. Faire valider les conditions d’accès des plateformes complémentaires, renseigner leur `url`, puis les activer depuis l’onglet « Sources ».
4. Conserver le volume `data/` (base + réglages) et surveiller le tableau de bord ; l’erreur d’une source n’interrompt pas les autres.

## Vérification

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q veille
```

## Limites à lever avec BAHO

Les capacités de chambres et les prestations exactes de chaque hôtel, les destinataires finaux, le serveur SMTP de production et les accès aux plateformes commerciales ne figuraient pas dans le brief : ils sont traités comme des paramètres de déploiement, pas inventés dans le code.
