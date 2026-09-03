"""Anmeldung an der Weboberfläche.

Diese eine Route hat keine eigene fachliche Aufgabe — sie dient nur
dazu, dass die Oberfläche ein eingegebenes Passwort prüfen kann, bevor
sie sich zeigt. Die eigentliche Prüfung übernimmt die globale
Abhängigkeit ``app.security.pruefe_seitenpasswort`` (siehe app.main),
die für diese Route genauso gilt wie für jede andere: Ist kein Passwort
gesetzt, antwortet sie immer mit "ok"; ist eines gesetzt, nur wenn der
Kopf ``X-Seiten-Passwort`` stimmt.
"""

from fastapi import APIRouter

router = APIRouter(tags=["anmeldung"])


@router.get("/anmeldung")
def anmeldung() -> dict[str, bool]:
    return {"ok": True}
