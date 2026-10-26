from __future__ import annotations

import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from .models import ScoredTender


def send(item: ScoredTender, recipients: list[str]) -> tuple[str, str | None]:
    """Send the operational alert. SMTP credentials stay exclusively in environment variables."""
    if not recipients: return "skipped_no_recipients", None
    host = os.getenv("SMTP_HOST")
    if not host: return "skipped_no_smtp", None
    tender = item.tender
    msg = EmailMessage()
    msg["Subject"] = f"[BAHO • {item.score}/100] {tender.title}"
    msg["From"] = os.getenv("SMTP_FROM", "veille@localhost")
    msg["To"] = ", ".join(recipients)
    lines = [
        f"Appel d'offres détecté — score de pertinence : {item.score}/100", "",
        f"Intitulé : {tender.title}", f"Acheteur : {tender.buyer}", f"Référence : {tender.reference or 'Non renseignée'}",
        f"Publication : {tender.published_at.isoformat() if tender.published_at else 'Non renseignée'}",
        f"Détection : {datetime.now(timezone.utc).isoformat()}",
        f"Échéance : {tender.deadline_at.isoformat() if tender.deadline_at else 'Non renseignée'}",
        f"Lieu : {tender.location}", f"CPV : {', '.join(tender.cpvs) or 'Non renseigné'}",
        f"Chambres / nuitées : {tender.rooms_or_nights}", f"Montant estimé : {tender.estimate_eur if tender.estimate_eur is not None else 'Non renseigné'}",
        f"Lien : {tender.source_url or 'Non renseigné'}", "", "Motifs de classement :",
        *[f"- {reason}" for reason in item.reasons], "", "Documents associés :",
        *([f"- {document}" for document in tender.documents] or ["- Non renseignés"]), "", "Description :", tender.description or "Non renseignée",
    ]
    msg.set_content("\n".join(lines))
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=30) as client:
            if os.getenv("SMTP_STARTTLS", "true").lower() != "false": client.starttls()
            username, password = os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD")
            # Google displays app passwords in blocks of four; accepting that display
            # format prevents a pasted space from invalidating SMTP authentication.
            if host.lower() == "smtp.gmail.com" and password:
                password = "".join(password.split())
            if username: client.login(username, password or "")
            client.send_message(msg)
        return "sent", None
    except (OSError, smtplib.SMTPException) as exc:
        return "failed", str(exc)
