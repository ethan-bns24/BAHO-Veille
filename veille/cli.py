from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone

from .config import load_settings
from .database import Database
from .models import ScoredTender, ScoreLine, Tender
from .notify import send
from .service import WatchService
from .web import serve


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Veille automatisée BAHO des appels d'offres")
    root.add_argument("--config", help="Chemin du fichier TOML (défaut: settings.toml)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Initialise la base SQLite")
    commands.add_parser("run-once", help="Exécute une collecte et s'arrête")
    commands.add_parser("run", help="Exécute la veille en continu")
    commands.add_parser("test-email", help="Envoie un e-mail de test aux destinataires configurés")
    commands.add_parser("sources", help="Affiche l'état de configuration de chaque source")
    commands.add_parser("reset-alerts", help="Purge l'historique d'envoi : les opportunités seront re-notifiées")
    preview = commands.add_parser("preview-email", help="Écrit un aperçu HTML de l'alerte sans rien envoyer")
    preview.add_argument("--out", default="alerte-exemple.html")
    dashboard = commands.add_parser("serve", help="Lance le tableau de bord local")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8080)
    return root


def sample_alert() -> ScoredTender:
    """Annonce fictive servant aux tests d'envoi et à l'aperçu du rendu."""
    now = datetime.now(timezone.utc)
    tender = Tender(
        source="test", external_id="smtp-test", reference="TEST-SMTP",
        title="Accord-cadre d'hébergement hôtelier et de séminaires résidentiels",
        buyer="Centre Hospitalier Universitaire de Lyon", buyer_profile="Hôpital / santé",
        description="Message de contrôle : la chaîne de collecte, de scoring et d'envoi fonctionne. "
                    "Prestations d'hébergement et de restauration pour 2 400 nuitées annuelles.",
        cpvs=["55110000", "55120000"], published_at=now - timedelta(days=1), deadline_at=now + timedelta(days=18),
        location="Saint-Fons, Rhône", department="69", estimate_eur=450_000.0,
        rooms_or_nights="2 400 nuitées", procedure="Procédure ouverte", contract_nature="Services",
        notice_kind="Avis de marché", duration="48 mois",
        lots=["Lot 1 — Hébergement", "Lot 2 — Séminaires résidentiels"],
        documents=["https://www.boamp.fr/exemple/reglement-de-consultation.pdf"],
        source_url="https://www.boamp.fr/",
    )
    breakdown = [
        ScoreLine("Mots-clés et CPV", 30, 30, "CPV prioritaire 55110000, 55120000"),
        ScoreLine("Zone BAHO", 15, 15, "SH Saint-Fons (69)"),
        ScoreLine("Montant estimé", 15, 15, "450 000 € ≥ seuil 20 000 €"),
        ScoreLine("Délai de réponse", 15, 15, "18 jours restants"),
        ScoreLine("Informations disponibles", 10, 10, "4/4 champs clés · 1 document"),
        ScoreLine("Prestations associées", 15, 15, "séminaire résidentiel, demi-pension"),
    ]
    return ScoredTender(tender=tender, score=100, reasons=["Message de test demandé manuellement"],
                        keyword_hits=["hébergement hôtelier", "séminaire résidentiel"],
                        commercial_match=True, breakdown=breakdown)


def main() -> None:
    args = parser().parse_args()
    settings = load_settings(args.config)
    logging.basicConfig(level=getattr(logging, settings.app.get("log_level", "INFO")),
                        format="%(asctime)s %(levelname)s %(message)s")

    if args.command == "init-db":
        Database(settings.database_path).initialize()
        print(f"Base initialisée: {settings.database_path}")
        return

    if args.command == "reset-alerts":
        database = Database(settings.database_path)
        database.initialize()
        removed = database.clear_notifications()
        pending = sum(1 for t in database.dashboard(limit=10_000,
                      minimum_score=int(settings.notification["minimum_score"]))["tenders"]
                      if t["score"] >= int(settings.notification["minimum_score"]))
        print(f"Historique purgé : {removed} entrée(s) supprimée(s).")
        print(f"{pending} opportunité(s) au-dessus du seuil seront re-notifiées, "
              f"par lots de {settings.notification['max_alerts_per_cycle']} "
              f"espacés de {settings.notification['send_interval_seconds']} s.")
        print(f"Destinataires : {', '.join(settings.recipients) or 'aucun'}")
        return

    if args.command == "sources":
        for source in settings.sources:
            state = "active " if source.get("enabled") else "inactive"
            detail = source.get("url") or f"limite {source.get('limit', '-')}"
            print(f"{state}  {source['name']:<16} {source.get('kind', '?'):<6} {detail}")
        return

    if args.command == "preview-email":
        from .notify import render_html, _urgency
        item = sample_alert()
        now = datetime.now(timezone.utc)
        html = render_html(item, now, _urgency(item.tender.deadline_at), "created",
                           int(settings.notification["minimum_score"]))
        with open(args.out, "w", encoding="utf-8") as handle: handle.write(html)
        print(f"Aperçu écrit dans {args.out}")
        return

    if args.command == "test-email":
        status, error = send(sample_alert(), settings.recipients,
                             threshold=int(settings.notification["minimum_score"]))
        if status == "sent":
            print(f"E-mail de test envoyé à {', '.join(settings.recipients)}")
            return
        raise SystemExit(f"E-mail de test non envoyé ({status}): {error or 'configuration SMTP incomplète'}")

    if args.command == "serve":
        print(f"Tableau de bord: http://{args.host}:{args.port}")
        serve(settings, args.host, args.port)
        return

    service = WatchService(settings)
    if args.command == "run-once":
        print(service.run_once())
        return
    while True:
        try:
            print(service.run_once())
        except Exception:
            logging.exception("Cycle de veille interrompu")
        time.sleep(max(1, int(service.settings.app["poll_interval_minutes"])) * 60)


if __name__ == "__main__": main()
