"""Anmeldung an der Weboberfläche.

Diese eine Route hat keine eigene fachliche Aufgabe — sie dient nur dazu,
dass die Oberfläche ein eingegebenes Passwort prüfen kann, bevor sie sich
zeigt. Die eigentliche Prüfung übernimmt die globale Abhängigkeit
``app.security.pruefe_seitenpasswort`` (siehe app.main), die für diese
Route genauso gilt wie für jede andere: Ist kein Passwort gesetzt,
antwortet sie immer mit "ok"; ist eines gesetzt, nur wenn der Aufruf sich
ausweist.

Wird sie erreicht, war die Anmeldung erfolgreich — dann setzt sie das
Zugangs-Cookie. Das braucht die App für alles, was der Browser selbst
nachlädt: Fotos in der Galerie, Planvorschauen, ZIP- und Anhang-Downloads.
Diese Aufrufe können keine Kopfzeile mitgeben (siehe app.security).
"""

from fastapi import APIRouter, Request, Response

from app.config import settings
from app.security import anmeldung_merken

router = APIRouter(tags=["anmeldung"])


@router.get("/anmeldung")
def anmeldung(request: Request, antwort: Response) -> dict[str, bool]:
    passwort = (settings.seiten_passwort or "").strip()
    if passwort:
        # Hinter einem Reverse-Proxy (Render, Next.js-Rewrite) steht das
        # ursprüngliche Schema im X-Forwarded-Proto; request.url.scheme wäre
        # dort "http" und das Cookie bekäme fälschlich kein "secure".
        schema = request.headers.get("x-forwarded-proto", request.url.scheme)
        anmeldung_merken(antwort, passwort, sicher=schema == "https")
    return {"ok": True}
