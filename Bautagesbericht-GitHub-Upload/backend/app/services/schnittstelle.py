"""Der Umgang mit der Anthropic-Schnittstelle, an einer Stelle.

WOZU
====
Drei Module fragen dort an: das seitenweise Lesen handschriftlicher
Bautagebücher (``seitenlesung``), die Auswertung gescannter Formblätter
(``pdf_extraction``) und die Analyse der Baubesprechungen
(``besprechung_analyse``). Alle drei haben dieselben drei Sorgen:

1. **Nicht die Ereignisschleife blockieren.** Das Anthropic-Paket wird hier
   synchron benutzt, und eine Bilderkennung dauert zehn Sekunden und mehr.
   Direkt in der Schleife stünde der ganze Webserver so lange still.
2. **Vorübergehende Störungen aussitzen.** Überlastung, ein Limit, ein kurzer
   Netzaussetzer. Ohne Wiederholung ging dafür eine ganze Seite verloren — in
   der Woche fehlte dann ein Tag.
3. **Verständlich melden, was los ist.** Die Schnittstelle antwortet auf
   Englisch und mit Statuscodes. Wer im Büro einen Bautagesbericht hochlädt,
   kann mit "Error code: 401 - {'type': 'error', ...}" nichts anfangen — und
   sucht den Fehler beim Scan, während der Grund die Konfiguration ist.

WAS NICHT WIEDERHOLT WIRD
=========================
Ein falscher Schlüssel ist beim dritten Versuch genauso falsch wie beim
ersten, ein leeres Konto genauso leer. Solche Fehler gelten als endgültig und
gehen sofort an den Aufrufer weiter.
"""

from __future__ import annotations

import asyncio

#: Wie oft eine Anfrage wiederholt wird, die an etwas Vorübergehendem
#: gescheitert ist.
VERSUCHE = 3

#: Wartezeit vor dem zweiten Versuch, danach jeweils das Doppelte.
WARTEN_SEKUNDEN = 2.0


#: Wortfetzen, an denen sich der Grund eines Fehlschlags erkennen lässt, und
#: was der Anwender stattdessen lesen soll.
_FEHLERDEUTUNG = (
    (("authentication", "401", "invalid x-api-key", "invalid api key"),
     "Der Anthropic-Schlüssel wird nicht angenommen. Bitte den Wert hinter "
     "„anthropic_key=“ prüfen — er beginnt mit „sk-ant-“ und darf keine "
     "Leerzeichen oder Anführungszeichen enthalten."),
    (("permission", "403"),
     "Der Anthropic-Schlüssel darf dieses Modell nicht benutzen."),
    (("credit", "billing", "quota", "insufficient"),
     "Das Anthropic-Konto hat kein Guthaben mehr."),
    (("rate_limit", "429", "overloaded", "529"),
     "Die Anthropic-Schnittstelle ist gerade überlastet oder das Limit ist "
     "erreicht. In ein paar Minuten noch einmal versuchen."),
    (("connection", "timeout", "getaddrinfo", "ssl", "network"),
     "Keine Verbindung zur Anthropic-Schnittstelle. Internetverbindung oder "
     "Firewall prüfen."),
)

#: Was sich nicht von selbst gibt: Schlüssel, Rechte, Guthaben.
_ENDGUELTIG = (
    "authentication", "401", "403", "permission",
    "credit", "billing", "quota", "invalid x-api-key",
)

#: Was sich von selbst wieder gibt: Überlastung, Limits, Netzaussetzer und
#: die Serverfehler der Gegenseite.
_VORUEBERGEHEND = (
    "rate_limit", "429", "overloaded", "529", "500", "502", "503",
    "timeout", "timed out", "connection", "getaddrinfo", "temporarily",
    "apiconnection", "remote end closed",
)


def _roh(fehler: Exception) -> str:
    return f"{type(fehler).__name__}: {fehler}".lower()


def fehlertext(fehler: Exception) -> str:
    """Aus einer Ausnahme der Schnittstelle einen brauchbaren Satz machen."""
    roh = _roh(fehler)
    for stichworte, klartext in _FEHLERDEUTUNG:
        if any(wort in roh for wort in stichworte):
            return klartext
    return f"Die Texterkennung meldete: {fehler}"


def endgueltig(fehler: Exception) -> bool:
    """Hat es keinen Sinn, dieselbe Anfrage noch einmal zu schicken?

    Ein falscher Schlüssel bleibt bei Seite 12 genauso falsch wie bei Seite 1.
    Ohne diese Prüfung liefen bei einer Woche Bautagebuch 24 aussichtslose
    Anfragen durch, bevor am Ende "0 Tage erkannt" herauskam.
    """
    return any(wort in _roh(fehler) for wort in _ENDGUELTIG)


def vorruebergehend(fehler: Exception) -> bool:
    """Lohnt ein zweiter Versuch?"""
    if endgueltig(fehler):
        return False
    return any(wort in _roh(fehler) for wort in _VORUEBERGEHEND)


async def mit_wiederholung(ruf, *, versuche: int | None = None,
                           warten: float | None = None):
    """Führt ``ruf`` in einem eigenen Thread aus und wiederholt bei Störungen.

    ``ruf`` ist eine gewöhnliche Funktion ohne Argumente — die Aufrufer haben
    unterschiedliche Anfragen, gemeinsam ist nur der Umgang mit dem Fehlschlag.

    ``versuche`` und ``warten`` sind übergebbar, weil die Aufrufer eigene
    Grenzen kennen dürfen: Ein Wochenpaket mit 24 Anfragen verträgt weniger
    Wartezeit als eine einzelne Besprechungsanalyse.
    """
    grenze = VERSUCHE if versuche is None else versuche
    warten = WARTEN_SEKUNDEN if warten is None else warten
    for versuch in range(1, max(1, grenze) + 1):
        try:
            return await asyncio.to_thread(ruf)
        except Exception as fehler:
            if versuch >= grenze or not vorruebergehend(fehler):
                raise
            await asyncio.sleep(warten)
            warten *= 2
    return None
