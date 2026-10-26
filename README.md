# BAHO · veille des appels d’offres

Un bot autonome qui collecte les avis de marchés, détecte les opportunités liées à l’hébergement hôtelier, les dédoublonne, les classe et envoie une alerte e-mail explicable. Il a été construit à partir du brief fourni.

## Ce qui est opérationnel

- Connecteur BOAMP actif, via l’API open data officielle de la DILA ; il interroge côté serveur les termes BAHO et ne se limite donc pas aux 100 derniers avis.
- Historique SQLite, déduplication par référence/identifiant de dossier et consolidation des liens de plusieurs sources.
- Détection des modifications (dont une échéance modifiée) et nouvelle alerte pour la nouvelle version.
- Scoring configurable sur 100 : adéquation métier, géographie, montant, délai, complétude et prestations associées. Les motifs sont visibles dans chaque alerte et le tableau de bord.
- Garde-fou métier : « Hôtel de Ville » et les consultations de restauration isolées sont historisés mais ne déclenchent pas une alerte hôtelière.
- E-mail SMTP, journal d’exécution, reprise au cycle suivant après erreur, état de chaque source, tableau de bord local et conteneurs Docker.

Les adaptateurs `place`, `france_marches` et `aws_achat` sont présents mais volontairement inactifs dans `settings.toml` : avant de les activer, il faut renseigner leur flux RSS/Atom/JSON officiellement autorisé et valider leurs conditions d’utilisation. Le brief demande explicitement cette vérification. Aucun scraping contournant ces conditions n’est mis en place.

## Démarrage local

Python 3.11+ suffit ; le projet n’a aucune dépendance applicative externe.

```bash
python3 -m veille.cli init-db
python3 -m veille.cli run-once
python3 -m veille.cli serve
```

Après configuration SMTP, valider l’envoi sans attendre une opportunité :

```bash
python3 -m veille.cli test-email
```

Le tableau de bord est alors disponible sur [http://127.0.0.1:8080](http://127.0.0.1:8080). Pour faire tourner la veille en continu :

```bash
python3 -m veille.cli run
```

Ou avec Docker :

```bash
cp .env.example .env
docker compose up --build -d
```

## Passage en production

1. Remplir les implantations, départements, capacités et services BAHO dans `settings.toml`. La géographie est alors intégrée au score.
2. Créer `.env` depuis `.env.example`, définir `ALERT_RECIPIENTS` et les paramètres SMTP. Ce fichier est chargé aussi bien par Docker que par les commandes Python locales ; tant que le SMTP est absent, les notifications sont auditées dans la base mais aucun e-mail n’est envoyé.
3. Faire valider les flux/API de PLACE, France Marchés et AWS-Achat ; renseigner leur `url`, puis passer `enabled = true`. Le connecteur générique accepte RSS, Atom et JSON avec les noms de champs documentés dans `veille/connectors/feed.py`.
4. Conserver le volume `data/` et surveiller le tableau de bord ; les erreurs d’une source n’empêchent pas les autres cycles de s’exécuter.

Les seuils et pondérations sont dans `settings.toml`. Le seuil d’alerte est 35/100 par défaut ; une annonce non retenue n’est jamais supprimée.

## Vérification

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q veille
```

## Limites à lever avec BAHO

Les adresses/capacités des hôtels, les destinataires, le serveur SMTP et les flux autorisés des plateformes complémentaires ne figuraient pas dans le brief. Ils ont donc été configurés comme des paramètres de déploiement, pas inventés dans le code.
