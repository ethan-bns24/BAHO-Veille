"""Composition et envoi de l'alerte commerciale.

L'e-mail est le livrable visible du bot : il doit se lire en dix secondes sur un
téléphone et contenir tout ce que le brief exige (section 7), sans avoir à ouvrir
l'annonce. Le rendu est en HTML compatible messagerie — tableaux, styles en ligne,
largeur fixe — avec une version texte de repli pour les clients qui la préfèrent.
"""

from __future__ import annotations

import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from .models import ScoredTender, ScoreLine

PALETTE = {
    "ink": "#13211c", "muted": "#5c6b63", "line": "#e2e7e3", "page": "#f4f6f4",
    "card": "#ffffff", "brand": "#14463a", "accent": "#0c7a52", "soft": "#eef5f1",
    "urgent": "#b4451f", "warn": "#9a6b12",
}


def check_configuration() -> str | None:
    """Retourne un message si la configuration SMTP est inutilisable, sinon None.

    Un identifiant qui n'est pas une adresse est l'erreur la plus fréquente : le serveur
    coupe alors la connexion sans rien expliquer (« Connection unexpectedly closed »).
    Autant le dire franchement avant de tenter l'envoi.
    """
    username = os.getenv("SMTP_USERNAME", "")
    if username and "@" not in username:
        return (f"SMTP_USERNAME doit être l'adresse du compte, pas un nom d'affichage "
                f"(valeur actuelle : {username!r}). Le nom affiché se règle avec SMTP_FROM_NAME.")
    sender = os.getenv("SMTP_FROM", "")
    if sender and "@" not in sender:
        return f"SMTP_FROM doit être une adresse e-mail (valeur actuelle : {sender!r})."
    return None


def send(item: ScoredTender, recipients: list[str], event: str = "created", threshold: int = 35) -> tuple[str, str | None]:
    """Envoie l'alerte. Les identifiants SMTP restent exclusivement dans l'environnement."""
    if not recipients: return "skipped_no_recipients", None
    host = os.getenv("SMTP_HOST")
    if not host: return "skipped_no_smtp", None
    problem = check_configuration()
    if problem: return "failed", problem
    message = build_message(item, recipients, event=event, threshold=threshold)
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=30) as client:
            if os.getenv("SMTP_STARTTLS", "true").lower() != "false": client.starttls()
            username, password = os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD")
            # Google affiche les mots de passe d'application par blocs de quatre ;
            # accepter ce format évite qu'une espace collée invalide l'authentification.
            if host.lower() == "smtp.gmail.com" and password:
                password = "".join(password.split())
            if username: client.login(username, password or "")
            client.send_message(message)
        return "sent", None
    except (OSError, smtplib.SMTPException) as exc:
        return "failed", str(exc)


def build_message(item: ScoredTender, recipients: list[str], event: str = "created", threshold: int = 35) -> EmailMessage:
    tender = item.tender
    detected = datetime.now(timezone.utc)
    urgency = _urgency(tender.deadline_at)
    message = EmailMessage()
    message["Subject"] = _subject(item, urgency, event)
    message["From"] = formataddr((os.getenv("SMTP_FROM_NAME", "BAHO · veille appels d'offres"),
                                  os.getenv("SMTP_FROM", "veille@localhost")))
    message["To"] = ", ".join(recipients)
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="baho-veille")
    message["X-BAHO-Score"] = str(item.score)
    # Un en-tête Reply-To joignable et une identification claire du caractère
    # automatique du message pèsent favorablement dans le classement anti-spam.
    message["Reply-To"] = os.getenv("SMTP_REPLY_TO", os.getenv("SMTP_FROM", "veille@localhost"))
    message["Auto-Submitted"] = "auto-generated"
    message["X-Entity-Ref-ID"] = f"{item.tender.source}:{item.tender.external_id}"
    message.set_content(render_text(item, detected, urgency, event, threshold))
    message.add_alternative(render_html(item, detected, urgency, event, threshold), subtype="html")
    return message


# --------------------------------------------------------------------------- sujet

def _subject(item: ScoredTender, urgency: dict, event: str) -> str:
    prefix = "MISE À JOUR" if event == "updated" else "NOUVEAU"
    countdown = f" · {urgency['label']}" if urgency["label"] else ""
    return f"[BAHO {item.score}/100] {prefix}{countdown} — {_shorten(item.tender.title, 90)}"


# ---------------------------------------------------------------------- rendu HTML

def render_html(item: ScoredTender, detected: datetime, urgency: dict, event: str, threshold: int) -> str:
    tender = item.tender
    facts = _facts(item, detected, urgency)
    badge = "Mise à jour d'une annonce suivie" if event == "updated" else "Nouvelle opportunité détectée"
    link = tender.source_url or ""
    cta = (f'<a href="{_attr(link)}" style="display:inline-block;background:{PALETTE["accent"]};color:#ffffff;'
           f'text-decoration:none;padding:13px 26px;border-radius:8px;font-weight:700;font-size:15px">'
           f"Ouvrir l'annonce d'origine</a>") if link.startswith(("http://", "https://")) else \
          f'<span style="color:{PALETTE["muted"]};font-size:14px">Lien direct non publié par la source.</span>'

    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only">
<title>Alerte BAHO</title></head>
<body style="margin:0;padding:0;background:{PALETTE['page']};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">
{_text(_shorten(tender.description or tender.title, 140))} — {_text(tender.buyer)} — score {item.score}/100
</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PALETTE['page']};padding:24px 12px">
<tr><td align="center">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="width:640px;max-width:100%;background:{PALETTE['card']};border-radius:14px;overflow:hidden;border:1px solid {PALETTE['line']};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{PALETTE['ink']}">

  <tr><td style="background:{PALETTE['brand']};padding:22px 26px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="color:#cfe3d9;font-size:11px;letter-spacing:1.6px;text-transform:uppercase;font-weight:700">BAHO · veille appels d'offres</td>
      <td align="right" style="color:#cfe3d9;font-size:12px">{_text(detected.astimezone().strftime('%d/%m/%Y à %H:%M'))}</td>
    </tr></table>
    <div style="margin-top:14px;color:#ffffff;font-size:21px;line-height:1.35;font-weight:700">{_text(tender.title)}</div>
    <div style="margin-top:10px">
      <span style="display:inline-block;background:rgba(255,255,255,.14);color:#ffffff;font-size:12px;padding:5px 11px;border-radius:999px">{badge}</span>
      {_pill(urgency['label'], urgency['color']) if urgency['label'] else ''}
    </div>
  </td></tr>

  {_score_header(item, threshold)}

  <tr><td style="padding:4px 26px 0">
    <div style="font-size:12px;letter-spacing:1.3px;text-transform:uppercase;color:{PALETTE['muted']};font-weight:700;padding:18px 0 10px">Paramètres de l'annonce</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;font-size:14px">
      {''.join(_fact_row(label, value, highlight) for label, value, highlight in facts)}
    </table>
  </td></tr>

  {_breakdown_block(item)}
  {_list_block("Lots de la consultation", tender.lots)}
  {_description_block(tender.description)}
  {_documents_block(tender.documents)}

  <tr><td align="center" style="padding:26px">{cta}</td></tr>

  <tr><td style="background:{PALETTE['soft']};padding:18px 26px;font-size:12px;color:{PALETTE['muted']};line-height:1.7">
    <b style="color:{PALETTE['ink']}">Réglages appliqués à ce classement</b><br>
    Seuil d'alerte {threshold}/100 · source « {_text(tender.source)} » · détection {_text(detected.astimezone().strftime('%d/%m/%Y %H:%M'))}<br>
    Pondérations : {_text(' · '.join(f"{line.label} {line.maximum}" for line in item.breakdown)) or 'par défaut'}<br>
    Ces valeurs se modifient dans le tableau de bord ; elles s'appliquent dès le cycle suivant.
  </td></tr>

</table>
</td></tr></table>
</body></html>"""


def _score_header(item: ScoredTender, threshold: int) -> str:
    color = PALETTE["accent"] if item.score >= threshold + 20 else PALETTE["brand"] if item.score >= threshold else PALETTE["warn"]
    width = max(2, min(100, item.score))
    return f"""<tr><td style="padding:22px 26px 0">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="font-size:34px;font-weight:800;color:{color};line-height:1" width="110">{item.score}<span style="font-size:15px;color:{PALETTE['muted']};font-weight:600">/100</span></td>
      <td style="padding-left:6px">
        <div style="background:{PALETTE['line']};border-radius:999px;height:10px;width:100%">
          <table role="presentation" width="{width}%" cellpadding="0" cellspacing="0"><tr><td style="background:{color};border-radius:999px;height:10px;font-size:0;line-height:0">&nbsp;</td></tr></table>
        </div>
        <div style="font-size:12px;color:{PALETTE['muted']};padding-top:7px">Score de pertinence · seuil d'alerte fixé à {threshold}/100</div>
      </td>
    </tr></table>
  </td></tr>"""


def _fact_row(label: str, value: str, highlight: bool) -> str:
    weight = "700" if highlight else "500"
    color = PALETTE["ink"] if value and value != "Non renseigné" else PALETTE["muted"]
    return (f'<tr><td style="padding:9px 0;border-bottom:1px solid {PALETTE["line"]};color:{PALETTE["muted"]};'
            f'width:40%;vertical-align:top">{_text(label)}</td>'
            f'<td style="padding:9px 0;border-bottom:1px solid {PALETTE["line"]};color:{color};font-weight:{weight};'
            f'vertical-align:top">{_text(value or "Non renseigné")}</td></tr>')


def _breakdown_block(item: ScoredTender) -> str:
    if not item.breakdown: return ""
    rows = []
    for line in item.breakdown:
        share = round(100 * line.points / line.maximum) if line.maximum else 0
        color = PALETTE["accent"] if line.points else PALETTE["line"]
        rows.append(f"""<tr>
          <td style="padding:8px 0;width:38%;vertical-align:top;font-size:13px">{_text(line.label)}<br>
            <span style="color:{PALETTE['muted']};font-size:12px">{_text(line.detail)}</span></td>
          <td style="padding:8px 10px;vertical-align:middle;width:44%">
            <div style="background:{PALETTE['line']};border-radius:999px;height:7px">
              <table role="presentation" width="{max(share, 2)}%" cellpadding="0" cellspacing="0"><tr>
                <td style="background:{color};border-radius:999px;height:7px;font-size:0;line-height:0">&nbsp;</td></tr></table>
            </div></td>
          <td align="right" style="padding:8px 0;vertical-align:middle;font-size:13px;font-weight:700;white-space:nowrap">
            {line.points}<span style="color:{PALETTE['muted']};font-weight:500">/{line.maximum}</span></td>
        </tr>""")
    return f"""<tr><td style="padding:4px 26px 0">
      <div style="font-size:12px;letter-spacing:1.3px;text-transform:uppercase;color:{PALETTE['muted']};font-weight:700;padding:22px 0 6px">Détail du score</div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{''.join(rows)}</table>
    </td></tr>"""


def _list_block(title: str, values: list[str]) -> str:
    if not values: return ""
    items = "".join(f'<li style="margin:4px 0">{_text(value)}</li>' for value in values[:12])
    extra = f'<li style="margin:4px 0;color:{PALETTE["muted"]}">… et {len(values) - 12} autre(s)</li>' if len(values) > 12 else ""
    return f"""<tr><td style="padding:4px 26px 0">
      <div style="font-size:12px;letter-spacing:1.3px;text-transform:uppercase;color:{PALETTE['muted']};font-weight:700;padding:22px 0 4px">{_text(title)}</div>
      <ul style="margin:0;padding-left:20px;font-size:14px;line-height:1.6">{items}{extra}</ul>
    </td></tr>"""


def _description_block(description: str) -> str:
    if not description: return ""
    return f"""<tr><td style="padding:4px 26px 0">
      <div style="font-size:12px;letter-spacing:1.3px;text-transform:uppercase;color:{PALETTE['muted']};font-weight:700;padding:22px 0 6px">Objet de la consultation</div>
      <div style="background:{PALETTE['soft']};border-left:3px solid {PALETTE['accent']};border-radius:0 8px 8px 0;padding:14px 16px;font-size:14px;line-height:1.65">{_text(_shorten(description, 1200))}</div>
    </td></tr>"""


def _documents_block(documents: list[str]) -> str:
    if not documents: return ""
    links = "".join(
        f'<li style="margin:5px 0"><a href="{_attr(url)}" style="color:{PALETTE["accent"]};word-break:break-all">{_text(_shorten(url, 80))}</a></li>'
        for url in documents[:8])
    return f"""<tr><td style="padding:4px 26px 0">
      <div style="font-size:12px;letter-spacing:1.3px;text-transform:uppercase;color:{PALETTE['muted']};font-weight:700;padding:22px 0 4px">Dossier de consultation</div>
      <ul style="margin:0;padding-left:20px;font-size:13px">{links}</ul>
    </td></tr>"""


def _pill(label: str, color: str) -> str:
    return (f'<span style="display:inline-block;background:{color};color:#ffffff;font-size:12px;font-weight:700;'
            f'padding:5px 11px;border-radius:999px;margin-left:6px">{_text(label)}</span>')


# -------------------------------------------------------------------- rendu texte

def render_text(item: ScoredTender, detected: datetime, urgency: dict, event: str, threshold: int) -> str:
    tender = item.tender
    rule = "-" * 62
    lines = [
        f"BAHO · veille appels d'offres — score {item.score}/100 (seuil {threshold})",
        "Mise à jour d'une annonce suivie" if event == "updated" else "Nouvelle opportunité détectée",
        urgency["label"] or "", rule, tender.title, rule, "",
    ]
    for label, value, _ in _facts(item, detected, urgency):
        lines.append(f"{label:<26}: {value or 'Non renseigné'}")
    if item.breakdown:
        lines += ["", "DÉTAIL DU SCORE", rule]
        lines += [f"{line.points:>3}/{line.maximum:<3} {line.label} — {line.detail}" for line in item.breakdown]
    if tender.lots:
        lines += ["", "LOTS", rule, *[f"- {lot}" for lot in tender.lots[:12]]]
    if tender.description:
        lines += ["", "OBJET", rule, _shorten(tender.description, 1200)]
    lines += ["", "DOSSIER DE CONSULTATION", rule]
    lines += [f"- {url}" for url in tender.documents[:8]] or ["- Non renseigné"]
    lines += ["", f"Annonce d'origine : {tender.source_url or 'non publiée'}", "",
              f"Pondérations appliquées : {' · '.join(f'{line.label} {line.maximum}' for line in item.breakdown) or 'par défaut'}",
              "Réglages modifiables dans le tableau de bord BAHO."]
    return "\n".join(line for line in lines if line is not None)


# ------------------------------------------------------------------------- champs

def _facts(item: ScoredTender, detected: datetime, urgency: dict) -> list[tuple[str, str, bool]]:
    tender = item.tender
    return [
        ("Acheteur", tender.buyer, True),
        ("Type d'acheteur", tender.buyer_profile, False),
        ("Échéance de réponse", _deadline_text(tender.deadline_at, urgency), True),
        ("Lieu d'exécution", tender.location, True),
        ("Département", tender.department or "Non renseigné", False),
        ("Montant estimé", _euro(tender.estimate_eur), True),
        ("Volume (chambres / nuitées)", tender.rooms_or_nights, True),
        ("Nature du marché", tender.contract_nature or tender.notice_kind, False),
        ("Procédure", tender.procedure, False),
        ("Durée", tender.duration, False),
        ("Codes CPV", ", ".join(tender.cpvs) if tender.cpvs else "Non renseigné", False),
        ("Référence consultation", tender.reference, False),
        ("Publication", _stamp(tender.published_at), False),
        ("Détection par le bot", detected.astimezone().strftime("%d/%m/%Y à %H:%M"), False),
        ("Source", tender.source, False),
        ("Mots-clés déclencheurs", ", ".join(dict.fromkeys(item.keyword_hits))[:220] or "Aucun", False),
    ]


def _urgency(deadline: datetime | None) -> dict:
    if not deadline: return {"label": "", "color": PALETTE["muted"], "days": None}
    days = (deadline - datetime.now(timezone.utc)).total_seconds() / 86400
    if days < 0: return {"label": "Échéance dépassée", "color": PALETTE["muted"], "days": days}
    if days < 7: return {"label": f"J-{days:.0f} · à traiter en priorité", "color": PALETTE["urgent"], "days": days}
    if days < 21: return {"label": f"J-{days:.0f}", "color": PALETTE["warn"], "days": days}
    return {"label": f"J-{days:.0f}", "color": PALETTE["accent"], "days": days}


def _deadline_text(deadline: datetime | None, urgency: dict) -> str:
    if not deadline: return "Non renseignée"
    suffix = f" ({urgency['label']})" if urgency["label"] else ""
    return deadline.astimezone().strftime("%d/%m/%Y à %H:%M") + suffix


def _stamp(value: datetime | None) -> str:
    return value.astimezone().strftime("%d/%m/%Y") if value else "Non renseignée"


def _euro(amount: float | None) -> str:
    if amount is None: return "Non renseigné"
    return f"{amount:,.0f} €".replace(",", " ")


def _shorten(value: str, size: int) -> str:
    value = " ".join(str(value).split())
    return value if len(value) <= size else value[: size - 1].rstrip() + "…"


def _text(value: object) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _attr(value: object) -> str:
    return _text(value).replace('"', "&quot;")
