"""Tableau de bord local.

Il sert trois usages : suivre les opportunités collectées, surveiller l'état de chaque
source, et surtout régler la veille en direct. Les modifications sont écrites dans
`overrides.json` et relues au cycle suivant : aucun redémarrage, aucun fichier versionné
réécrit.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .config import LIST_KEYS, NUMERIC_KEYS, load_settings
from .dashboard import PAGE
from .database import Database
from .service import WatchService

MAX_BODY = 1 << 20


def serve(settings, host: str, port: int) -> None:
    state = {"settings": settings, "running": False, "last_run": None}
    db = Database(settings.database_path)
    db.initialize()
    lock = threading.Lock()

    def current():
        return state["settings"]

    def run_cycle() -> None:
        with lock:
            if state["running"]: return
            state["running"] = True
        try:
            state["last_run"] = WatchService(load_settings(current().path)).run_once()
        except Exception as exc:  # une erreur de cycle ne doit pas tuer le serveur
            state["last_run"] = {"error": str(exc)}
            db.event("ERROR", "cycle_error", str(exc), "dashboard")
        finally:
            state["running"] = False

    class Handler(BaseHTTPRequestHandler):
        server_version = "BAHO-veille"

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                return self._html(PAGE)
            if path == "/api/state":
                return self._json(self._state())
            if path == "/api/events":
                return self._json({"events": db.recent_events()})
            return self.send_error(404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                payload = self._body()
            except ValueError as exc:
                return self._json({"error": str(exc)}, status=400)
            if path == "/api/settings":
                try:
                    patch = _validate(payload)
                except ValueError as exc:
                    return self._json({"error": str(exc)}, status=400)
                state["settings"] = current().apply(patch)
                return self._json(self._state() | {"saved": sorted(patch)})
            if path == "/api/settings/reset":
                state["settings"] = current().reset()
                return self._json(self._state() | {"saved": ["réglages d'origine restaurés"]})
            if path == "/api/alerts/reset":
                removed = db.clear_notifications()
                return self._json({"removed": removed})
            if path == "/api/run":
                if state["running"]:
                    return self._json({"error": "Un cycle est déjà en cours."}, status=409)
                threading.Thread(target=run_cycle, daemon=True).start()
                return self._json({"started": True})
            if path == "/api/test-email":
                from .cli import sample_alert
                from .notify import send
                settings_now = current()
                status, error = send(sample_alert(), settings_now.recipients,
                                     threshold=int(settings_now.notification["minimum_score"]))
                return self._json({"status": status, "error": error, "recipients": settings_now.recipients})
            return self.send_error(404)

        # ---------------------------------------------------------------- helpers

        def _state(self) -> dict:
            settings = current()
            threshold = int(settings.notification["minimum_score"])
            data = db.dashboard(minimum_score=threshold)
            return {
                **data,
                "settings": settings.editable(),
                "schema": {
                    "numeric": {key: {"label": label, "min": low, "max": high}
                                for key, (label, low, high) in NUMERIC_KEYS.items()},
                    "lists": LIST_KEYS,
                },
                "sources": [{"name": s.get("name"), "kind": s.get("kind"), "enabled": bool(s.get("enabled")),
                             "url": s.get("url", ""), "limit": s.get("limit", 0)} for s in settings.sources],
                "hotels": settings.hotels,
                "running": state["running"],
                "last_run": state["last_run"],
                "overrides": bool(settings.overrides),
            }

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0: return {}
            if length > MAX_BODY: raise ValueError("Requête trop volumineuse")
            try:
                value = json.loads(self.rfile.read(length))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON invalide: {exc}") from exc
            if not isinstance(value, dict): raise ValueError("Corps de requête inattendu")
            return value

        def _json(self, value: dict, status: int = 200) -> None:
            self._send(json.dumps(value, ensure_ascii=False, default=str).encode(), "application/json", status)

        def _html(self, page: str) -> None:
            self._send(page.encode(), "text/html", 200)

        def _send(self, body: bytes, kind: str, status: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None: pass

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def _validate(payload: dict) -> dict:
    """N'accepte que les clés exposées, dans leurs bornes. Le reste est rejeté."""
    patch: dict = {}
    for key, value in payload.items():
        if key in NUMERIC_KEYS:
            _, low, high = NUMERIC_KEYS[key]
            try: number = float(value)
            except (TypeError, ValueError) as exc: raise ValueError(f"{key}: valeur numérique attendue") from exc
            if not low <= number <= high: raise ValueError(f"{key}: attendu entre {low:g} et {high:g}")
            patch[key] = int(number) if float(number).is_integer() else number
        elif key in LIST_KEYS:
            items = value if isinstance(value, list) else str(value).splitlines()
            patch[key] = [str(item).strip() for item in items if str(item).strip()]
        elif key == "sources":
            if not isinstance(value, dict): raise ValueError("sources: objet attendu")
            cleaned = {}
            for name, item in value.items():
                if not isinstance(item, dict): raise ValueError(f"sources.{name}: objet attendu")
                allowed = {k: v for k, v in item.items() if k in ("enabled", "url", "limit", "kind")}
                if "enabled" in allowed: allowed["enabled"] = bool(allowed["enabled"])
                if "limit" in allowed: allowed["limit"] = max(1, min(5000, int(allowed["limit"] or 1)))
                cleaned[str(name)] = allowed
            patch["sources"] = cleaned
        else:
            raise ValueError(f"Réglage inconnu: {key}")
    if not patch: raise ValueError("Aucun réglage à enregistrer")
    return patch
