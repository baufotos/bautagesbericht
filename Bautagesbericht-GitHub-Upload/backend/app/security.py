"""Passwortschutz für die gesamte Weboberfläche.

Ohne gesetztes ``BTB_SEITEN_PASSWORT`` bleibt die App offen wie bisher —
z. B. auf dem Bürorechner, wo kein Zugriff von außen möglich ist (siehe
app.config). Ist ein Passwort gesetzt, muss sich jeder Aufruf ausweisen,
sonst antwortet der Server mit 401.

``pruefe_seitenpasswort`` wird in app.main als globale Abhängigkeit
eingebunden und gilt damit automatisch für jede Route — auch neue, die
später dazukommen, ohne dass jeder Router einzeln daran denken muss.


Zwei Wege, sich auszuweisen — und warum es zwei sein müssen
-----------------------------------------------------------

1. Der Kopf ``X-Seiten-Passwort``. Den setzt die Oberfläche bei jedem
   ``fetch`` (frontend/src/lib/api.ts) und ihn benutzen Skripte.

2. Das Cookie ``hpp_zugang``, gesetzt bei der Anmeldung.

Der zweite Weg ist nicht Bequemlichkeit, sondern Notwendigkeit: Die App
zeigt Fotos über ``<img src="/api/.../bild">`` an und bietet Dateien über
``<a href="/api/.../zip">`` an. Bei solchen Aufrufen lädt der BROWSER die
Adresse selbst — dabei kann kein JavaScript eine Kopfzeile mitgeben. Mit
Kopfzeilen allein blieben sämtliche Fotos, Pläne, Anhänge und Downloads
leer, obwohl man angemeldet ist. Ein Cookie schickt der Browser dagegen
von sich aus mit, auch bei ``<img>`` und ``<a>``.

Im Cookie steht nicht das Passwort selbst, sondern ein davon abgeleiteter
Fingerabdruck (siehe ``_fingerabdruck``). Wird das Passwort bei Render
geändert, passen alle alten Cookies nicht mehr — die Anmeldung erneuert
sich dann von selbst.


Ausnahmen
---------

  - ``/api/health*``: Der Gesundheitscheck von Render braucht kein
    Passwort, sonst hält Render die App fälschlich für gestört.

  - Der Abholweg der Bürorechner: die Abholrouten (``.../abholung/...``)
    UND der ZIP-Download ``/fotosaetze/{id}/zip``, den das Skript danach
    aufruft (``desktop/abholung/Baufotos-Abholen.ps1``). Der ZIP-Pfad
    gehört ausdrücklich dazu: Er sieht nicht nach Abholung aus, ist aber
    Teil davon — fehlt er hier, bricht die Abholung mit 401 ab, nachdem
    sie den Satz bereits beansprucht hat.

Der Abholweg ist dabei NICHT einfach offen, sondern verlangt das eigene
Losungswort ``BTB_ABHOL_TOKEN``. Grund: Fotosatz-Nummern sind fortlaufend
und damit ratbar. Wäre ``/fotosaetze/7/zip`` ohne alles erreichbar, könnte
jeder mit dem Render-Link sämtliche Baufotos herunterladen — genau das,
was das Seiten-Passwort verhindern soll. Sobald ein Seiten-Passwort
gesetzt ist, braucht der Abholweg deshalb ein GESETZTES und passendes
``BTB_ABHOL_TOKEN``; fehlt es, gibt es 401. Das fällt sofort im Protokoll
der Abholung auf — die stille Alternative wäre, die Fotos offen ins Netz
zu stellen.
"""

import hashlib
import re
import secrets

from fastapi import Header, HTTPException, Request, Response

from app.config import settings

_OFFENE_PFADE_PRAEFIXE = ("/api/health",)

# Der ZIP-Download des Abholskripts, z. B. "/api/fotosaetze/6/zip".
_ZIP_PFAD = re.compile(r"/fotosaetze/\d+/zip$")

COOKIE_NAME = "hpp_zugang"

# Ein halbes Jahr. Lang genug, dass niemand auf der Baustelle ständig neu
# tippt; das Cookie wird ohnehin ungültig, sobald das Passwort wechselt.
COOKIE_MAX_ALTER = 180 * 24 * 60 * 60


def _fingerabdruck(passwort: str) -> str:
    """Was statt des Passworts im Cookie steht.

    Der feste Zusatz bindet den Wert an diesen Zweck, damit derselbe
    Fingerabdruck nicht anderswo wiederverwendbar ist.
    """
    return hashlib.sha256(f"hpp-baumanagement:{passwort}".encode()).hexdigest()


def _ist_abholweg(pfad: str) -> bool:
    """Gehört dieser Pfad zum Ablauf der Bürorechner-Abholung?"""
    return "/abholung/" in pfad or _ZIP_PFAD.search(pfad) is not None


def _abholrecht_nachgewiesen(x_abhol_token: str) -> bool:
    """Weist der Aufruf sich als Bürorechner aus?

    Anders als ``routers.baufotos.pruefe_abholrecht`` gilt ein fehlendes
    ``BTB_ABHOL_TOKEN`` hier NICHT als „offen" (siehe Modulkopf): Ohne
    hinterlegtes Losungswort gibt es keinen Nachweis, also auch keine
    Ausnahme vom Seiten-Passwort.
    """
    erwartet = (settings.abhol_token or "").strip()
    if not erwartet:
        return False
    return secrets.compare_digest((x_abhol_token or "").strip(), erwartet)


def anmeldung_merken(antwort: Response, passwort: str, sicher: bool) -> None:
    """Setzt das Zugangs-Cookie nach erfolgreicher Anmeldung.

    ``httponly``: JavaScript soll den Wert nicht lesen können — gebraucht
    wird er nur vom Browser selbst beim Nachladen von Bildern und Dateien.
    ``secure`` nur bei HTTPS, sonst käme das Cookie auf dem Bürorechner
    (http://localhost) gar nicht erst an.
    """
    antwort.set_cookie(
        COOKIE_NAME,
        _fingerabdruck(passwort),
        max_age=COOKIE_MAX_ALTER,
        httponly=True,
        secure=sicher,
        samesite="lax",
        path="/",
    )


def pruefe_seitenpasswort(
    request: Request,
    x_seiten_passwort: str = Header(""),
    x_abhol_token: str = Header(""),
) -> None:
    erwartet = (settings.seiten_passwort or "").strip()
    if not erwartet:
        return  # kein Passwort gesetzt -> offen wie bisher

    pfad = request.url.path
    if pfad.startswith(_OFFENE_PFADE_PRAEFIXE):
        return

    # Weg 1: Kopfzeile (fetch aus der Oberfläche, Skripte)
    if secrets.compare_digest((x_seiten_passwort or "").strip(), erwartet):
        return

    # Weg 2: Cookie (<img src>, <a href> — der Browser lädt selbst)
    cookie = request.cookies.get(COOKIE_NAME, "")
    if cookie and secrets.compare_digest(cookie, _fingerabdruck(erwartet)):
        return

    if _ist_abholweg(pfad) and _abholrecht_nachgewiesen(x_abhol_token):
        return

    raise HTTPException(401, "Seiten-Passwort fehlt oder stimmt nicht")
