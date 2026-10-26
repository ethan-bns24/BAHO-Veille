from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone

from .config import load_settings
from .database import Database
from .service import WatchService
from .web import serve
from .models import ScoredTender, Tender
from .notify import send


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Veille automatisée BAHO des appels d'offres")
    root.add_argument("--config", help="Chemin du fichier TOML (défaut: settings.toml)")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Initialise la base SQLite")
    commands.add_parser("run-once", help="Exécute une collecte et s'arrête")
    commands.add_parser("run", help="Exécute la veille en continu")
    commands.add_parser("test-email", help="Envoie un e-mail de test aux destinataires configurés")
    dashboard = commands.add_parser("serve", help="Lance le tableau de bord local")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8080)
    return root


def main() -> None:
    args = parser().parse_args()
    settings = load_settings(args.config)
    logging.basicConfig(level=getattr(logging, settings.app.get("log_level", "INFO")), format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "init-db":
        Database(settings.database_path).initialize(); print(f"Base initialisée: {settings.database_path}"); return
    if args.command == "test-email":
        test = ScoredTender(
            tender=Tender(source="test", external_id="smtp-test", reference="TEST-SMTP", title="Test d'alerte BAHO",
                          buyer="BAHO", description="La configuration SMTP fonctionne.", published_at=datetime.now(timezone.utc)),
            score=100, reasons=["Message de test demandé manuellement"], keyword_hits=[], commercial_match=True,
        )
        status, error = send(test, settings.recipients)
        if status == "sent": print(f"E-mail de test envoyé à {', '.join(settings.recipients)}"); return
        raise SystemExit(f"E-mail de test non envoyé ({status}): {error or 'configuration SMTP incomplète'}")
    if args.command == "serve":
        db = Database(settings.database_path); db.initialize()
        print(f"Tableau de bord: http://{args.host}:{args.port}")
        serve(db, args.host, args.port, int(settings.notification["minimum_score"])); return
    service = WatchService(settings)
    if args.command == "run-once":
        print(service.run_once()); return
    interval = max(1, int(settings.app["poll_interval_minutes"])) * 60
    while True:
        try: print(service.run_once())
        except Exception: logging.exception("Cycle de veille interrompu")
        time.sleep(interval)


if __name__ == "__main__": main()
