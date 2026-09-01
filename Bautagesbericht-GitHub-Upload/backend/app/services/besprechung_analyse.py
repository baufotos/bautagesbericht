"""tl;dv-Transkript und -Notizen zu Themen-Vorschlägen verdichten.

WAS DIESES MODUL TUT — UND WAS AUSDRÜCKLICH NICHT
=================================================
Es **schlägt vor**. Nichts von dem, was hier entsteht, ist ein Protokoll.
Jede Zeile landet als Entwurf in der Prüfansicht und muss von einem Menschen
angesehen werden, bevor sie in ein Dokument darf — dieselbe Regel wie im
Mängelmodul, aus demselben Grund: Ein erfundener Termin sieht in einem
Protokoll genauso aus wie ein richtiger.

DIE EIGENTLICHE AUFGABE IST ZUORDNEN, NICHT ZUSAMMENFASSEN
==========================================================
Eine Baubesprechung erzeugt selten neue Themen. Meistens geht es um Punkte,
die seit Wochen laufen: "Der Terminplan kommt nächste Woche" ist kein neues
Thema, sondern der aktuelle Stand von "02. 09. — Übermittlung eines
Detailterminplans". Wird das falsch erkannt, wächst die Themenliste bei jeder
Sitzung um Dubletten und die durchgehende Nachverfolgung — der eigentliche
Zweck der ganzen Liste — ist zerstört.

Deshalb bekommt das Modell die **offenen Themen des Projekts mit ihren
Nummern** in den Prompt und muss sich für jeden erkannten Punkt entscheiden:
Fortschreibung von Thema X, oder wirklich neu. Im Zweifel Fortschreibung —
eine falsch zusammengeführte Zeile fällt beim Prüfen sofort auf, eine Dublette
merkt niemand, bis die Liste unbrauchbar ist.

WAS NICHT GERATEN WIRD
======================
* Fristen nur, wenn sie im Gespräch genannt wurden. Kein "wahrscheinlich
  nächste Woche".
* Zuständige nur als Kürzel, die es in den Projektbeteiligten gibt.
* Teilnehmer nur mit Namen. Firma und Telefon kommen aus den Stammdaten und
  werden als *Vorschlag* markiert, nie als Tatsache — tl;dv liefert beides
  nicht.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.config import settings

#: Dasselbe Modell wie in ``app.services.seitenlesung``. Steht bewusst an zwei
#: Stellen und nicht in der Konfiguration: Ein Modellwechsel ist eine
#: Entscheidung, die man je Anwendungsfall prüft, nicht eine Einstellung, die
#: man versehentlich global umlegt.
CLAUDE_MODELL = "claude-opus-5"

#: Genug für eine lange Sitzung mit vielen Themen.
MAX_TOKENS = 8192

#: Ab hier wird das Transkript gekürzt. Eine zweistündige Besprechung liefert
#: rund 60.000 Zeichen; darüber steht erfahrungsgemäß nur noch Verabschiedung.
MAX_TRANSKRIPT = 120_000
MAX_NOTIZEN = 40_000


class AnalyseFehler(RuntimeError):
    """Die Analyse konnte nicht durchgeführt werden."""


@dataclass
class OffenesThema:
    """Ein bestehendes Thema, wie es dem Modell gezeigt wird."""

    id: int
    kennung: str          # "02. 09."
    kapitel: str          # "VE01 Erweiterte Rohbauarbeiten - Rolfes Bau"
    text: str
    zustaendig: str = ""
    bearb_bis: str = ""
    status: str = "b"


@dataclass
class KapitelInfo:
    id: int
    nummer: str
    titel: str


@dataclass
class BeteiligterInfo:
    kuerzel: str
    name: str
    rolle: str = ""


@dataclass
class ThemenVorschlag:
    """Ein Vorschlag für eine Zeile des Protokolls."""

    #: Gesetzt, wenn es die Fortschreibung eines bestehenden Themas ist.
    thema_id: int | None
    #: Gesetzt, wenn es ein neues Thema ist.
    kapitel_id: int | None
    text: str
    zustaendig: str = ""
    bearb_bis: str = ""
    status: str = "n"
    #: Warum das Modell so zugeordnet hat — steht in der Prüfansicht.
    begruendung: str = ""


@dataclass
class TeilnehmerVorschlag:
    name: str
    firma_kuerzel: str = ""


@dataclass
class AnalyseErgebnis:
    themen: list[ThemenVorschlag] = field(default_factory=list)
    teilnehmer: list[TeilnehmerVorschlag] = field(default_factory=list)
    hinweise: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Werkzeug-Schema (erzwungene strukturierte Antwort)
# ─────────────────────────────────────────────────────────────────────────────

WERKZEUG = {
    "name": "besprechung_auswerten",
    "description": (
        "Gibt die in der Baubesprechung behandelten Punkte strukturiert "
        "zurück, jeweils zugeordnet zu einem bestehenden Thema oder als neues "
        "Thema."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "punkte": {
                "type": "array",
                "description": "Jeder in der Besprechung behandelte Punkt.",
                "items": {
                    "type": "object",
                    "properties": {
                        "bestehendes_thema_id": {
                            "type": ["integer", "null"],
                            "description": (
                                "id des fortgeschriebenen Themas aus der Liste "
                                "der offenen Themen, oder null bei einem neuen "
                                "Thema."
                            ),
                        },
                        "kapitel_id": {
                            "type": ["integer", "null"],
                            "description": (
                                "Nur bei einem neuen Thema: id des Kapitels, in "
                                "das es gehört."
                            ),
                        },
                        "text": {
                            "type": "string",
                            "description": (
                                "Der Punkt als knapper Protokollsatz in der "
                                "Sprache eines Baubesprechungsprotokolls. "
                                "Mehrere Aspekte mit Zeilenumbruch trennen, "
                                "Aufzählungen mit '- ' beginnen."
                            ),
                        },
                        "zustaendig": {
                            "type": "string",
                            "description": (
                                "Kürzel der Zuständigen, nur aus der Liste der "
                                "Projektbeteiligten. Mehrere mit '/' und "
                                "Zeilenumbruch, z.B. 'ROL/\\nSBH/'. Leer, wenn "
                                "nicht genannt."
                            ),
                        },
                        "bearb_bis": {
                            "type": "string",
                            "description": (
                                "Frist genau so, wie sie genannt wurde: "
                                "'31.08.26' oder \"KW 35'26\". Leer, wenn keine "
                                "Frist genannt wurde. Niemals schätzen."
                            ),
                        },
                        "status": {
                            "type": "string",
                            "enum": ["k", "b", "e", "n", "i"],
                            "description": (
                                "k kritisch, b in Bearbeitung, e erledigt, "
                                "n neu in dieser Sitzung, i informativ."
                            ),
                        },
                        "begruendung": {
                            "type": "string",
                            "description": (
                                "Ein Satz: warum dieser Punkt zu diesem "
                                "bestehenden Thema gehört bzw. warum er neu ist."
                            ),
                        },
                    },
                    "required": ["bestehendes_thema_id", "text", "status"],
                },
            },
            "teilnehmer": {
                "type": "array",
                "description": (
                    "Personen, die im Transkript erkennbar gesprochen haben "
                    "oder als anwesend genannt wurden."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name, möglichst als 'Herr X' / 'Frau X'.",
                        },
                        "firma_kuerzel": {
                            "type": "string",
                            "description": (
                                "Kürzel aus den Projektbeteiligten, wenn aus dem "
                                "Gespräch klar hervorgeht, für wen die Person "
                                "spricht. Sonst leer lassen."
                            ),
                        },
                    },
                    "required": ["name"],
                },
            },
            "hinweise": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Was beim Prüfen auffallen sollte: unklare Stellen, "
                    "widersprüchliche Angaben, Punkte ohne erkennbare "
                    "Zuständigkeit."
                ),
            },
        },
        "required": ["punkte"],
    },
}


ANWEISUNG = """\
Du wertest eine Baubesprechung im Hochbau aus. Ergebnis ist die Grundlage für \
das Protokoll eines Architekturbüros (Objektüberwachung). Ein Mensch prüft \
alles nach — deine Aufgabe ist Genauigkeit, nicht Vollständigkeit um jeden \
Preis.

DIE WICHTIGSTE REGEL
Das Projekt führt EINE fortlaufende Themenliste. Die meisten Punkte einer \
Besprechung sind Fortschreibungen bestehender Themen, keine neuen. Ordne \
deshalb jeden Punkt zuerst einem bestehenden offenen Thema zu und lege nur \
dann ein neues an, wenn wirklich keines passt. Im Zweifel: bestehendes Thema.

WAS EIN PUNKT IST
Ein Sachverhalt, zu dem in dieser Sitzung etwas gesagt wurde: eine \
Entscheidung, eine Zusage, eine Frist, eine Feststellung. Kein Punkt sind \
Begrüßung, Small Talk, Terminfindung für den Anruf selbst.

FORMULIERUNG
Knapp, sachlich, im Stil eines Protokolls ("Übermittlung des Detailterminplans"\
, nicht "Herr Meier sagt, dass er den Terminplan schickt"). Keine wörtliche \
Rede, keine Namen im Text — Namen gehören in "zuständig" als Firmenkürzel.

WAS DU NICHT TUST
- Fristen erfinden. Nur übernehmen, was genannt wurde.
- Zuständige raten. Nur Kürzel aus der Liste der Projektbeteiligten.
- Einen Punkt auf "e" (erledigt) setzen, wenn er nur besprochen wurde. "e" \
  heißt: in dieser Sitzung ausdrücklich als abgeschlossen festgestellt.
- Themen zusammenfassen, die verschiedene Gewerke betreffen.

STATUS
n  in dieser Sitzung neu aufgenommen
b  läuft weiter, heute wurde etwas dazu gesagt
e  heute ausdrücklich als erledigt festgestellt
k  kritisch, gefährdet Termin oder Kosten
i  reine Information, keine Aufgabe für jemanden
"""


# ─────────────────────────────────────────────────────────────────────────────
# Prompt-Aufbau
# ─────────────────────────────────────────────────────────────────────────────


def _liste_kapitel(kapitel: list[KapitelInfo]) -> str:
    if not kapitel:
        return "(noch keine Kapitel angelegt)"
    return "\n".join(f"  id={k.id}  {k.nummer} {k.titel}" for k in kapitel)


def _liste_beteiligte(beteiligte: list[BeteiligterInfo]) -> str:
    if not beteiligte:
        return "(keine hinterlegt — 'zuständig' dann leer lassen)"
    return "\n".join(
        f"  {b.kuerzel}  {b.name}" + (f"  ({b.rolle})" if b.rolle else "")
        for b in beteiligte
    )


def _liste_themen(themen: list[OffenesThema]) -> str:
    if not themen:
        return "(noch keine — alles ist neu)"
    zeilen = []
    for t in themen:
        kopf = f"  id={t.id}  {t.kennung}  [{t.kapitel}]  Status {t.status}"
        if t.zustaendig:
            kopf += f"  zuständig {t.zustaendig}"
        if t.bearb_bis:
            kopf += f"  bis {t.bearb_bis}"
        text = " ".join(t.text.split())[:400]
        zeilen.append(f"{kopf}\n      {text}")
    return "\n".join(zeilen)


def _kuerze(text: str, grenze: int) -> tuple[str, bool]:
    text = (text or "").strip()
    if len(text) <= grenze:
        return text, False
    return text[:grenze], True


def baue_prompt(
    *,
    transkript: str,
    notizen: str,
    offene_themen: list[OffenesThema],
    kapitel: list[KapitelInfo],
    beteiligte: list[BeteiligterInfo],
    projektname: str,
    besprechungsdatum: str,
) -> tuple[str, list[str]]:
    """Baut den Benutzertext und meldet, was dabei gekürzt werden musste."""
    hinweise: list[str] = []
    transkript, gekuerzt_t = _kuerze(transkript, MAX_TRANSKRIPT)
    notizen, gekuerzt_n = _kuerze(notizen, MAX_NOTIZEN)
    if gekuerzt_t:
        hinweise.append(
            f"Das Transkript war länger als {MAX_TRANSKRIPT:,} Zeichen und "
            f"wurde für die Analyse gekürzt. Bitte das Ende der Besprechung "
            f"gegenprüfen.".replace(",", ".")
        )
    if gekuerzt_n:
        hinweise.append("Die tl;dv-Notizen wurden für die Analyse gekürzt.")

    teile = [
        f"PROJEKT: {projektname}",
        f"BESPRECHUNGSDATUM: {besprechungsdatum}",
        "",
        "KAPITEL DIESES PROJEKTS (für neue Themen):",
        _liste_kapitel(kapitel),
        "",
        "PROJEKTBETEILIGTE (gültige Kürzel für 'zuständig'):",
        _liste_beteiligte(beteiligte),
        "",
        "OFFENE THEMEN DES PROJEKTS — hierhin gehören die meisten Punkte:",
        _liste_themen(offene_themen),
    ]
    if notizen:
        teile += ["", "TL;DV-NOTIZEN (KI-Zusammenfassung der Besprechung):", notizen]
    if transkript:
        teile += ["", "TL;DV-TRANSKRIPT (Wortprotokoll):", transkript]
    return "\n".join(teile), hinweise


# ─────────────────────────────────────────────────────────────────────────────
# Die Anfrage
# ─────────────────────────────────────────────────────────────────────────────


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _werkzeug_antwort(antwort, name: str) -> dict:
    for block in antwort.content:
        if block.type == "tool_use" and block.name == name:
            return dict(block.input or {})
    return {}


async def _frage(client, text: str) -> dict:
    """Eine Anfrage, außerhalb der Ereignisschleife ausgeführt.

    ``asyncio.to_thread`` wie in ``seitenlesung``: Das Anthropic-Paket wird
    hier synchron benutzt, und der Webserver soll währenddessen weiter
    antworten.
    """

    def ruf():
        return client.messages.create(
            model=CLAUDE_MODELL,
            max_tokens=MAX_TOKENS,
            system=ANWEISUNG,
            tools=[WERKZEUG],
            tool_choice={"type": "tool", "name": WERKZEUG["name"]},
            messages=[{"role": "user", "content": text}],
        )

    antwort = await asyncio.to_thread(ruf)
    return _werkzeug_antwort(antwort, WERKZEUG["name"])


# ─────────────────────────────────────────────────────────────────────────────
# Ergebnis säubern
# ─────────────────────────────────────────────────────────────────────────────

_ERLAUBTE_STATUS = {"k", "b", "e", "n", "i"}


def _zu_ergebnis(
    roh: dict,
    *,
    offene_themen: list[OffenesThema],
    kapitel: list[KapitelInfo],
    beteiligte: list[BeteiligterInfo],
) -> AnalyseErgebnis:
    """Aus der Modellantwort saubere Vorschläge machen.

    Alles, was das Modell erfunden haben könnte, wird hier gegen die
    Wirklichkeit geprüft: Thema-ids, Kapitel-ids und Firmenkürzel müssen
    existieren. Was nicht passt, wird nicht stillschweigend verworfen, sondern
    zu einem neuen Thema bzw. zu einem Hinweis.
    """
    bekannte_themen = {t.id for t in offene_themen}
    bekannte_kapitel = {k.id for k in kapitel}
    erstes_kapitel = kapitel[0].id if kapitel else None
    bekannte_kuerzel = {b.kuerzel.upper() for b in beteiligte}

    ergebnis = AnalyseErgebnis(hinweise=list(roh.get("hinweise") or []))

    for eintrag in (roh.get("punkte") or []):
        text = str(eintrag.get("text") or "").strip()
        if not text:
            continue

        thema_id = eintrag.get("bestehendes_thema_id")
        if thema_id is not None and thema_id not in bekannte_themen:
            ergebnis.hinweise.append(
                f"Die Analyse hat „{text[:60]}“ einem Thema zugeordnet, das es "
                f"nicht gibt. Der Punkt steht jetzt als neues Thema drin — "
                f"bitte die Zuordnung prüfen."
            )
            thema_id = None

        kapitel_id = eintrag.get("kapitel_id")
        if thema_id is None:
            if kapitel_id not in bekannte_kapitel:
                kapitel_id = erstes_kapitel
            if kapitel_id is None:
                ergebnis.hinweise.append(
                    f"„{text[:60]}“ konnte keinem Kapitel zugeordnet werden — "
                    f"für dieses Projekt ist noch keins angelegt."
                )
                continue
        else:
            kapitel_id = None

        status = str(eintrag.get("status") or "n").strip().lower()
        if status not in _ERLAUBTE_STATUS:
            status = "n"

        zustaendig, unbekannt = _pruefe_kuerzel(
            str(eintrag.get("zustaendig") or ""), bekannte_kuerzel
        )
        if unbekannt:
            ergebnis.hinweise.append(
                f"Unbekannte Kürzel bei „{text[:60]}“: {', '.join(unbekannt)}. "
                f"Bitte Zuständigkeit prüfen oder die Projektbeteiligten ergänzen."
            )

        ergebnis.themen.append(ThemenVorschlag(
            thema_id=thema_id,
            kapitel_id=kapitel_id,
            text=text,
            zustaendig=zustaendig,
            bearb_bis=str(eintrag.get("bearb_bis") or "").strip(),
            status=status,
            begruendung=str(eintrag.get("begruendung") or "").strip(),
        ))

    for eintrag in (roh.get("teilnehmer") or []):
        name = str(eintrag.get("name") or "").strip()
        if not name:
            continue
        kuerzel = str(eintrag.get("firma_kuerzel") or "").strip().upper()
        if kuerzel and kuerzel not in bekannte_kuerzel:
            kuerzel = ""
        ergebnis.teilnehmer.append(TeilnehmerVorschlag(name=name, firma_kuerzel=kuerzel))

    return ergebnis


def _pruefe_kuerzel(wert: str, bekannt: set[str]) -> tuple[str, list[str]]:
    """Behält nur Kürzel, die es wirklich gibt; meldet die anderen.

    "ALL" bleibt immer stehen — im Original steht es für "alle Beteiligten"
    und ist kein Firmenkürzel.
    """
    if not wert.strip():
        return "", []
    behalten: list[str] = []
    unbekannt: list[str] = []
    for roh in wert.replace("\n", "/").split("/"):
        teil = roh.strip().strip(",").upper()
        if not teil:
            continue
        if teil == "ALL" or teil in bekannt:
            behalten.append(teil)
        else:
            unbekannt.append(teil)
    if not behalten:
        return "", unbekannt
    # Mehrere Zuständige stehen im Protokoll untereinander, jeweils mit "/".
    if len(behalten) == 1:
        return behalten[0], unbekannt
    return "\n".join(f"{k}/" for k in behalten[:-1]) + f"\n{behalten[-1]}", unbekannt


# ─────────────────────────────────────────────────────────────────────────────
# Öffentliche Funktion
# ─────────────────────────────────────────────────────────────────────────────


def ist_verfuegbar() -> bool:
    """Steckt ein Anthropic-Schlüssel in der Konfiguration?"""
    return bool((settings.anthropic_api_key or "").strip())


async def analysiere(
    *,
    transkript: str,
    notizen: str,
    offene_themen: list[OffenesThema],
    kapitel: list[KapitelInfo],
    beteiligte: list[BeteiligterInfo],
    projektname: str,
    besprechungsdatum: str,
) -> AnalyseErgebnis:
    """Wertet eine Besprechung aus und gibt Vorschläge zurück."""
    if not ist_verfuegbar():
        raise AnalyseFehler(
            "Für die Analyse fehlt der Anthropic-Schlüssel. In "
            "einstellungen.txt bei „anthropic_key=“ eintragen — er beginnt "
            "mit „sk-ant-“. Ohne ihn lassen sich die Themen von Hand erfassen."
        )
    if not (transkript.strip() or notizen.strip()):
        raise AnalyseFehler(
            "Weder Transkript noch Notizen vorhanden — es gibt nichts "
            "auszuwerten."
        )

    text, hinweise = baue_prompt(
        transkript=transkript,
        notizen=notizen,
        offene_themen=offene_themen,
        kapitel=kapitel,
        beteiligte=beteiligte,
        projektname=projektname,
        besprechungsdatum=besprechungsdatum,
    )

    try:
        roh = await _frage(_client(), text)
    except Exception as fehler:  # Netz, Schlüssel, Kontingent
        raise AnalyseFehler(f"Die Analyse ist fehlgeschlagen: {fehler}") from fehler

    if not roh:
        raise AnalyseFehler(
            "Die Analyse kam ohne verwertbares Ergebnis zurück. Bitte erneut "
            "versuchen oder die Themen von Hand erfassen."
        )

    ergebnis = _zu_ergebnis(
        roh,
        offene_themen=offene_themen,
        kapitel=kapitel,
        beteiligte=beteiligte,
    )
    ergebnis.hinweise = hinweise + ergebnis.hinweise
    if not ergebnis.themen:
        ergebnis.hinweise.append(
            "Die Analyse hat keinen einzigen Punkt gefunden. Bitte prüfen, ob "
            "der eingefügte Text wirklich die Besprechung enthält."
        )
    return ergebnis
