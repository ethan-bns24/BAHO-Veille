from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .database import Database


def serve(db: Database, host: str, port: int, minimum_score: int = 35) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            data = db.dashboard(minimum_score=minimum_score)
            if path == "/api/tenders": return self._json(data)
            if path != "/": return self.send_error(404)
            page = _page(data)
            encoded = page.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
        def _json(self, value: dict) -> None:
            encoded = json.dumps(value, ensure_ascii=False, default=str).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
        def log_message(self, format: str, *args: object) -> None: pass
    ThreadingHTTPServer((host, port), Handler).serve_forever()


def _page(data: dict) -> str:
    statistics = data["stats"]
    rows = "".join(_tender_row(t) for t in data["tenders"]) or '<tr><td colspan="7">Aucune annonce collectée pour le moment.</td></tr>'
    health = "".join(f'<li><b>{html.escape(str(x["source"]))}</b> — {html.escape(str(x["kind"]))}: {html.escape(str(x["message"]))}</li>' for x in data["health"]) or "<li>En attente du premier cycle</li>"
    return f'''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BAHO — Veille appels d’offres</title><style>
body{{max-width:1400px;margin:32px auto;padding:0 20px;background:#f6f7f5;color:#17211d;font:15px system-ui,sans-serif}}h1{{margin-bottom:4px}}.sub{{color:#536158}}.cards{{display:flex;gap:16px;margin:24px 0}}.card{{background:#fff;border-radius:12px;padding:18px;min-width:150px;box-shadow:0 1px 4px #0001}}.n{{font-size:30px;font-weight:700}}table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 4px #0001}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #e7e9e7;vertical-align:top}}th{{background:#173f32;color:#fff}}.score{{font-weight:700;color:#086b43}}small{{color:#536158}}a{{color:#006c48}}ul{{padding-left:20px}}</style>
<h1>BAHO · veille commerciale</h1><p class="sub">Historique centralisé — toutes les opportunités sont conservées, même sous le seuil d’alerte.</p>
<section class="cards"><div class="card"><div class="n">{statistics["total"] or 0}</div>annonces détectées</div><div class="card"><div class="n">{statistics["relevant"] or 0}</div>score ≥ {statistics["threshold"]}</div></section>
<h2>État des sources</h2><ul>{health}</ul><h2>Opportunités</h2><table><thead><tr><th>Score</th><th>Appel d’offres</th><th>Acheteur</th><th>Échéance</th><th>Lieu</th><th>Sources</th><th>Motifs</th></tr></thead><tbody>{rows}</tbody></table>
</html>'''


def _tender_row(t: dict) -> str:
    title = html.escape(t["title"])
    url = next((x for x in (t.get("source_urls") or "").split(",") if x), "")
    label = f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noreferrer">{title}</a>' if url.startswith(("https://", "http://")) else title
    reasons = "<br>".join(html.escape(str(r)) for r in t.get("reasons", []))
    return f'<tr><td class="score">{t["score"]}/100</td><td>{label}<br><small>{html.escape(t.get("reference") or "Référence non renseignée")}</small></td><td>{html.escape(t["buyer"])}</td><td>{html.escape(t.get("deadline_at") or "Non renseignée")}</td><td>{html.escape(t.get("location") or "Non renseigné")}</td><td>{html.escape(t.get("source_names") or "")}</td><td><small>{reasons}</small></td></tr>'
