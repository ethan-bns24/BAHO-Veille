"""Accès réseau partagé par les connecteurs : en-têtes, authentification et reprise."""

from __future__ import annotations

import base64
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = "BAHO-veille/0.2 (veille appels d'offres; contact a configurer)"
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class HttpError(RuntimeError):
    pass


def fetch(url: str, *, method: str = "GET", payload: dict | None = None, headers: dict | None = None,
          username: str | None = None, password: str | None = None, timeout: int = 30,
          attempts: int = 3, backoff: float = 2.0) -> bytes:
    """Récupère une ressource en réessayant les erreurs transitoires.

    Le brief demande une reprise automatique : une indisponibilité passagère d'une
    plateforme ne doit pas faire perdre un cycle de veille entier.
    """
    request_headers = {"User-Agent": USER_AGENT, "Accept-Language": "fr", **(headers or {})}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
        request_headers.setdefault("Accept", "application/json")
    if username:
        token = base64.b64encode(f"{username}:{password or ''}".encode()).decode()
        request_headers["Authorization"] = f"Basic {token}"
    last: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            last = exc
            if exc.code not in RETRYABLE_STATUS: break
        except (URLError, TimeoutError, OSError) as exc:
            last = exc
        if attempt < attempts:
            time.sleep(backoff * attempt)
    raise HttpError(f"{url.split('?')[0]} — {last}") from last


def fetch_json(url: str, **kwargs) -> dict | list:
    raw = fetch(url, **kwargs)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HttpError(f"Réponse non JSON: {exc}") from exc
