"""Passwortschutz für die gesamte Weboberfläche.

Ohne gesetztes ``BTB_SEITEN_PASSWORT`` bleibt die App offen wie bisher —
z. B. auf dem Bürorechner, wo kein Zugriff von außen möglich ist (siehe
app.config). Ist ein Passwort gesetzt, verlangt jeder Aufruf des API den
Kopf ``X-Seiten-Passwort`` mit genau diesem Wert, sonst antwortet der
Server mit 401.

``pruefe_seitenpasswort`` wird in app.main als globale Abhängigkeit
eingebunden und gilt damit automatisch für jede Route — auch neue, die
später dazukommen, ohne dass jeder Router einzeln daran denken muss.

Zwei Ausnahmen, weil andere Aufrufer als die Weboberfläche sie
ansprechen:
  - ``/api/health*``: Der Gesundheitscheck von Render braucht kein
    Passwort, sonst hält Render die App fälschlich für gestört.
  - ``.../abholung/...``: Die Abholrouten für die Bürorechner haben ihr
    eigenes Losungswort (``BTB_ABHOL_TOKEN``, siehe
    routers.baufotos.pruefe_abholrecht) — die Abholskripte kennen keine
    Anmeldung und sollen unabhängig vom Seiten-Passwort weiterlaufen.
"""

from fastapi import Header, HTTPException, Request

from app.config import settings

_OFFENE_PFADE_PRAEFIXE = ("/api/health",)


def pruefe_seitenpasswort(
    request: Request, x_seiten_passwort: str = Header("")
) -> None:
    erwartet = (settings.seiten_passwort or "").strip()
    if not erwartet:
        return  # kein Passwort gesetzt -> offen wie bisher

    pfad = request.url.path
    if pfad.startswith(_OFFENE_PFADE_PRAEFIXE) or "/abholung/" in pfad:
        return

    if (x_seiten_passwort or "").strip() != erwartet:
        raise HTTPException(401, "Seiten-Passwort fehlt oder stimmt nicht")
