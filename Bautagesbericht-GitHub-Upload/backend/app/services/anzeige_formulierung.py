"""Aus Stichpunkten die Stellungnahme formulieren.

WAS DIESES MODUL TUT — UND WAS NICHT
====================================
Es macht aus hingeschriebenen Stichpunkten den Absatztext, der ins
Antwortschreiben kommt. Es entscheidet **nicht**, ob eine Anzeige berechtigt
ist, und es schreibt **kein** Schreiben. Der Weg ins Dokument bleibt derselbe
wie ohne dieses Modul:

    Stichpunkte  ->  [hier]  ->  Infofeld  ->  Mensch liest und ändert
                                            ->  Vorschau  ->  Word

Das Infofeld in der Mitte ist die Stelle, an der ein Mensch verantwortet, was
das Büro schreibt. Deshalb formuliert dieses Modul **in das Feld hinein** und
nicht in das Dokument: Der erzeugte Text ist ein Vorschlag im Formular, kein
fertiger Brief. Ohne diesen Zwischenschritt gäbe es einen Weg, auf dem ein
Modell ungelesen ein rechtserhebliches Schreiben verfasst — und den soll es
nicht geben.

WAS DAS MODELL NICHT DARF
=========================
Erfinden. Ein Antwortschreiben auf eine Mehrkostenanzeige wehrt
Vergütungsansprüche ab; eine erfundene LV-Position oder ein erfundenes Datum
darin ist keine Stilfrage, sondern ein Eigentor im Streitfall. Die Anweisung
verbietet deshalb ausdrücklich alles, was nicht in den Stichpunkten oder in
der eingegangenen Anzeige steht, und verlangt stattdessen einen Eintrag in
``offene_fragen``. Diese Liste zeigt die Oberfläche neben dem Feld an.

WOHER DER STIL KOMMT
====================
Aus den acht echten Antwortschreiben des Büros von 2020 bis 2026 (siehe
``STIL`` und ``WENDUNGEN``). Nichts davon ist erfunden: Es sind die Sätze und
Abkürzungen, die in diesen Briefen wirklich stehen.

OHNE SCHLÜSSEL
==============
Ohne Anthropic-Schlüssel in ``einstellungen.txt`` tut dieses Modul nichts und
sagt das auch. Das Infofeld funktioniert dann wie zuvor — man schreibt den
Text selbst hinein. Es ist eine Erleichterung, keine Voraussetzung.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import settings
from app.services import dokumenttext, schnittstelle

#: Modell für das Formulieren. Modellkennungen laufen ab, deshalb steht sie
#: hier an EINER Stelle — wie in ``besprechung_analyse`` und
#: ``pdf_extraction``.
CLAUDE_MODELL = "claude-opus-5"

#: Obergrenze der Antwort. Eine Stellungnahme hat selten mehr als eine Seite;
#: großzügig gerechnet reicht das für zwei.
MAX_TOKENS = 4000

#: So viel Text der eingegangenen Anzeige geht mit in die Anfrage. Zwei Seiten
#: Fließtext sind rund 6000 Zeichen; darüber wird gekürzt, damit eine
#: zwanzigseitige Anlage nicht das ganze Fenster füllt.
MAX_ANZEIGE_ZEICHEN = 14000

#: Und so viel von den Stichpunkten. Wer mehr schreibt, hat den Brief schon
#: geschrieben und braucht dieses Modul nicht.
MAX_STICHPUNKTE_ZEICHEN = 8000

#: Wie lange auf eine Antwort gewartet wird. Eine Stellungnahme entsteht in
#: zehn bis dreißig Sekunden; eine Minute ist großzügig. Siehe ``_client``,
#: dort steht, warum die Grenze überhaupt gesetzt wird.
ZEITGRENZE_SEKUNDEN = 60.0


class FormulierungFehler(Exception):
    """Formulieren war nicht möglich — mit einem Text für die Oberfläche."""


# ─────────────────────────────────────────────────────────────────────────────
# Der Stil des Büros
#
# Alles hier ist aus den Referenzschreiben abgelesen, nicht ausgedacht.
# ─────────────────────────────────────────────────────────────────────────────

STIL = """\
So schreibt das Büro HPP Architekten seine Antwortschreiben:

- Kurze, sachliche Sätze. Keine Ausschmückung, keine Höflichkeitsfloskeln
  mitten im Text, keine Superlative.
- "wir" ist HPP als Objektüberwachung des Auftraggebers. "Sie" / "Ihr" ist die
  Baufirma. Gesiezt wird durchgehend.
- Punkt für Punkt geantwortet, in der Reihenfolge der Anzeige, mit "1)", "2)",
  "3)" am Zeilenanfang.
- Begründet wird mit dem Vertrag: Leistungsverzeichnis, Auftrags-LV,
  Terminplan, Planunterlagen, Baubesprechung, Vergabegespräch.
- Übliche Abkürzungen: AG (Auftraggeber), AN (Auftragnehmer), LV
  (Leistungsverzeichnis), EP / EP's (Einheitspreise), BE (Baustelleneinrichtung),
  BZP (Bauzeitenplan), ZTV (Zusätzliche Technische Vertragsbedingungen),
  Pos. (Position), KW (Kalenderwoche).
- Wird eine Leistung als vertraglich geschuldet angesehen, heißt das:
  "mit den Einheitspreisen abgegolten", "im Hauptauftrag enthalten",
  "einzukalkulieren", "Nebenleistung".
- Wird eine Leistung als zusätzlich anerkannt, heißt das: "dies ist eine
  Zusatzleistung", "Abrechnung erfolgt über Pos. ... im LV".
"""

#: Wendungen, die in den Referenzbriefen wirklich vorkommen. Sie dienen als
#: Muster für den Ton — nicht als Bausteine, die eingesetzt werden müssen.
WENDUNGEN = """\
Beispielsätze aus echten Schreiben des Büros:

- "Wir sehen hier keinen Mehrvergütungsanspruch. In der Ausschreibung bzw. in
  ihrem Auftrags-LV ist ihr Vertragssoll dargelegt."
- "Diese Unterbrechungen sind einzukalkulieren und mit den EP's abgegolten."
- "Die Einbausituation gemäß Planunterlagen und technischem Vergabegespräch
  war für Sie klar ersichtlich. Diese Leistung ist im Hauptauftrag enthalten.
  Hier wird keine Mehrleistung anerkannt."
- "Kernbohrungen - dies ist eine Zusatzleistung. Abrechnung erfolgt über Pos.
  Kernbohrung im LV."
- "Sämtliche BE-Kosten, Anfahrten sind mit den EPs abgegolten."
- "Die Leistung erfolgt nach Abruf und ist mit keinem vertraglich fixierten
  Termin verbunden."
- "Daraus resultierende Mehrkosten können daher seitens AG nicht akzeptiert
  werden und werden vollumfänglich abgelehnt."
- "Hier können wir Ihren Ausführungen nicht ganz folgen, da es im LV
  entsprechende Pos. gibt, über die diese Leistung abgerechnet werden kann."
- "Ebenfalls wollen wir erneut darauf hinweisen, dass sich die Arbeiten nicht
  auf dem kritischen Weg befinden."
"""

ANWEISUNG = f"""\
Du formulierst die Stellungnahme für ein Antwortschreiben des
Architekturbüros HPP an eine Baufirma. Die Firma hat eine Anzeige geschickt
(Mehrkostenanzeige, Behinderungsanzeige, Nachtrag oder ähnlich). Ein
Mitarbeiter des Büros hat in Stichpunkten hingeschrieben, was in der Antwort
stehen soll. Deine Aufgabe ist es, daraus die Absätze des Briefes zu machen.

{STIL}
{WENDUNGEN}
HARTE REGELN

1. Erfinde nichts. Verwende ausschließlich Tatsachen, die in den Stichpunkten
   oder in der eingegangenen Anzeige stehen. Keine erfundenen LV-Positionen,
   keine erfundenen Daten, Fristen, Mengen, Maße, Plannummern, Namen,
   Kalenderwochen oder Baubesprechungen. Wenn ein Stichpunkt zu vage ist, um
   daraus einen belastbaren Satz zu machen, schreibe ihn NICHT aus, sondern
   trage in "offene_fragen" ein, welche Angabe fehlt.
2. Entscheide nicht über die Rechtslage. Ob abgelehnt, anerkannt oder geprüft
   wird, gibt die Haltung vor, die dir mitgeteilt wird. Formuliere in dieser
   Richtung, ohne sie zu verschärfen oder abzuschwächen.
3. Schreibe KEINE Anrede ("Sehr geehrte..."), KEINE Grußformel, KEINE
   Unterschrift, KEINEN Betreff und KEINEN Einleitungssatz der Art "wir haben
   Ihr Schreiben erhalten und nehmen wie folgt Stellung". Das alles setzt die
   Briefvorlage selbst. Fange direkt mit der Sache an.
4. Gliedere wie die Anzeige: Hat sie nummerierte Punkte oder sind die
   Stichpunkte aufgezählt, antworte mit "1) ", "2) " am Zeilenanfang, in
   derselben Reihenfolge und mit demselben Gegenstand.
5. Zitiere aus dem Leistungsverzeichnis nur, wenn der Wortlaut in den
   Stichpunkten steht. Setze dann einen Absatz mit dem Text "Auszug LV:" und
   danach die zitierten Zeilen mit "zitat": true. Formuliere ein Zitat niemals
   um und kürze es nicht.
6. Deutsch, Sie-Form, sachlich. Ein Absatz ist ein Gedanke; kein Absatz länger
   als etwa fünf Zeilen.
7. Übernimm keine Rechtschreibfehler und keine Stichwortsprache. Aus
   "Pos 3.11 bereits ausgeschrieben, EP abgegolten" wird ein vollständiger
   Satz.
"""

WERKZEUG: dict = {
    "name": "stellungnahme",
    "description": (
        "Die formulierten Absätze der Stellungnahme, in der Reihenfolge, in "
        "der sie im Brief stehen sollen."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "absaetze": {
                "type": "array",
                "description": (
                    "Die Absätze des Brieftextes. Ohne Anrede, ohne Grußformel."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Der Absatz als vollständiger Text.",
                        },
                        "zitat": {
                            "type": "boolean",
                            "description": (
                                "true nur für wörtlich zitierte LV-Zeilen. Sie "
                                "werden im Brief eingerückt."
                            ),
                        },
                    },
                    "required": ["text"],
                },
            },
            "offene_fragen": {
                "type": "array",
                "description": (
                    "Angaben, die für einen belastbaren Satz fehlten und "
                    "deshalb NICHT ausformuliert wurden."
                ),
                "items": {"type": "string"},
            },
        },
        "required": ["absaetze"],
    },
}

#: Klartext der Haltung für die Anfrage. Dieselben Kennungen wie im Erzeuger.
HALTUNG_TEXT: dict[str, str] = {
    "ablehnung": (
        "Die Anzeige wird abgelehnt. Begründe, warum die Leistung vertraglich "
        "geschuldet und mit den Einheitspreisen abgegolten ist."
    ),
    "teilweise": (
        "Die Anzeige wird teilweise anerkannt. Sage zu jedem Punkt getrennt, "
        "ob er anerkannt oder abgelehnt wird."
    ),
    "pruefung": (
        "Die Anzeige wird noch geprüft. Formuliere zurückhaltend und lege dich "
        "nicht auf ein Ergebnis fest."
    ),
    "anerkennung": (
        "Die Anzeige wird anerkannt. Sage, worüber abgerechnet wird, und "
        "verlange die noch fehlenden Unterlagen."
    ),
    "kenntnisnahme": (
        "Es wird nur zur Kenntnis genommen, ohne die Rechtslage zu bewerten."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Ein- und Ausgabe
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Auftrag:
    """Was zum Formulieren gebraucht wird."""

    #: Die Stichpunkte aus dem Infofeld. Ohne sie geht nichts.
    stichpunkte: str
    #: Art der eingegangenen Anzeige ("Mehrkostenanzeige", …).
    art: str = ""
    nummer: str = ""
    datum: str = ""
    #: Worum es geht — der Sachverhalt aus dem Betreff.
    kurzbezeichnung: str = ""
    #: Die nummerierten Punkte der Anzeige, als "1. Titel" je Zeile.
    punkte: list[str] = field(default_factory=list)
    #: Die LV-Positionen, die die Firma nennt.
    lv_positionen: list[str] = field(default_factory=list)
    #: Ihr Satz zur Bauzeit, falls vorhanden.
    bauzeit: str = ""
    #: Rechtsgrundlage, auf die sie sich beruft.
    rechtsgrundlage: str = ""
    #: Der Volltext der Anzeige — die wichtigste Quelle für Tatsachen.
    anzeigetext: str = ""
    #: Haltung des Büros, Kennung wie im Erzeuger.
    haltung: str = "kenntnisnahme"
    #: Projekt und Vergabeeinheit, für die Wortwahl.
    projekt: str = ""
    vergabeeinheit: str = ""


@dataclass
class Ergebnis:
    """Der Vorschlag für das Infofeld."""

    #: Fertig für das Infofeld — mit "Auszug LV:" und Leerzeilen an den
    #: Stellen, an denen der Erzeuger sie erwartet.
    stellungnahme: str = ""
    #: Was das Modell nicht ausformuliert hat, weil eine Angabe fehlte.
    offene_fragen: list[str] = field(default_factory=list)
    #: Was beim Zusammenstellen der Anfrage aufgefallen ist (Kürzungen).
    hinweise: list[str] = field(default_factory=list)


def ist_verfuegbar() -> bool:
    """Steckt ein Anthropic-Schlüssel in der Konfiguration?"""
    return bool((settings.anthropic_api_key or "").strip())


def warum_nicht() -> str:
    """Ein Satz für die Oberfläche, wenn das Formulieren nicht geht."""
    return (
        "Zum Formulieren fehlt der Anthropic-Schlüssel. In einstellungen.txt "
        "bei „anthropic_key=“ eintragen (er beginnt mit „sk-ant-“) und die App "
        "neu starten. Ohne ihn schreibt man den Text weiterhin selbst ins "
        "Infofeld — das Schreiben entsteht genauso."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Anfrage bauen
# ─────────────────────────────────────────────────────────────────────────────


def baue_anfrage(auftrag: Auftrag) -> tuple[str, list[str]]:
    """Der Text der Anfrage samt Hinweisen auf Kürzungen."""
    hinweise: list[str] = []

    stichpunkte, gekuerzt = _kuerze(auftrag.stichpunkte, MAX_STICHPUNKTE_ZEICHEN)
    if gekuerzt:
        hinweise.append(
            f"Die Stichpunkte waren länger als {MAX_STICHPUNKTE_ZEICHEN} "
            f"Zeichen und wurden für die Anfrage gekürzt."
        )
    anzeigetext, gekuerzt = _kuerze(auftrag.anzeigetext, MAX_ANZEIGE_ZEICHEN)
    if gekuerzt:
        hinweise.append(
            f"Die eingegangene Anzeige war länger als {MAX_ANZEIGE_ZEICHEN} "
            f"Zeichen; für die Anfrage wurde der Anfang verwendet."
        )

    teile: list[str] = ["## Die eingegangene Anzeige", ""]
    for kopf, wert in (
        ("Art", auftrag.art),
        ("Nummer", auftrag.nummer),
        ("Datum", auftrag.datum),
        ("Sachverhalt", auftrag.kurzbezeichnung),
        ("Rechtsgrundlage, auf die sich die Firma beruft", auftrag.rechtsgrundlage),
        ("Projekt", auftrag.projekt),
        ("Vergabeeinheit", auftrag.vergabeeinheit),
    ):
        if wert.strip():
            teile.append(f"{kopf}: {wert.strip()}")

    if auftrag.punkte:
        teile += ["", "Die Punkte der Firma:"]
        teile += [f"  {p}" for p in auftrag.punkte]
    if auftrag.lv_positionen:
        teile += [
            "",
            "LV-Positionen, die die Firma nennt: "
            + ", ".join(auftrag.lv_positionen),
        ]
    if auftrag.bauzeit.strip():
        teile += ["", f"Zur Bauzeit schreibt die Firma: {auftrag.bauzeit.strip()}"]

    if anzeigetext.strip():
        teile += [
            "",
            "Wortlaut der Anzeige (die einzige Tatsachenquelle neben den "
            "Stichpunkten):",
            "---",
            anzeigetext.strip(),
            "---",
        ]

    teile += [
        "",
        "## Haltung des Büros",
        "",
        HALTUNG_TEXT.get(auftrag.haltung, HALTUNG_TEXT["kenntnisnahme"]),
        "",
        "## Die Stichpunkte des Mitarbeiters",
        "",
        "Das ist die Vorgabe. Formuliere genau das aus — nicht mehr:",
        "---",
        stichpunkte.strip(),
        "---",
    ]
    return "\n".join(teile), hinweise


def _kuerze(text: str, grenze: int) -> tuple[str, bool]:
    sauber = dokumenttext.xml_sicher(text or "")
    if len(sauber) <= grenze:
        return sauber, False
    return sauber[:grenze], True


# ─────────────────────────────────────────────────────────────────────────────
# Antwort auswerten
# ─────────────────────────────────────────────────────────────────────────────


def zu_infofeld(absaetze: list[tuple[str, bool]]) -> str:
    """Absätze in die Schreibweise des Infofelds übersetzen.

    Das Infofeld ist die einzige Schnittstelle zum Erzeuger, und der liest es
    nach festen Regeln (siehe ``mehrkostenanzeige_generation._stellungnahme_bloecke``):
    Leerzeile trennt Absätze, eine Zeile "Auszug LV:" rückt das Folgende ein,
    und die nächste Leerzeile beendet den Einzug.

    Genau diese Schreibweise entsteht hier — nicht ein zweites Format, das der
    Erzeuger auch noch verstehen müsste.
    """
    zeilen: list[str] = []
    vorher_zitat = False

    for text, zitat in absaetze:
        sauber = " ".join(text.split()) if not zitat else text.strip()
        if not sauber:
            continue

        if zitat:
            # Innerhalb eines Zitatblocks keine Leerzeile — sonst endet der
            # Einzug nach der ersten Zeile.
            zeilen.append(sauber)
            vorher_zitat = True
            continue

        if vorher_zitat:
            zeilen.append("")
            vorher_zitat = False

        zeilen.append(sauber)
        # Nach einer Zitat-Einleitung darf keine Leerzeile stehen, sonst ist
        # der Block zu Ende, bevor er beginnt.
        if not _ist_zitatmarke(sauber):
            zeilen.append("")

    while zeilen and not zeilen[-1]:
        zeilen.pop()
    return "\n".join(zeilen)


def _ist_zitatmarke(zeile: str) -> bool:
    from app.services.mehrkostenanzeige_generation import ZITAT_MARKEN

    schlicht = zeile.strip().lower()
    return schlicht in ZITAT_MARKEN or schlicht.rstrip(":") + ":" in ZITAT_MARKEN


def _aus_antwort(roh: dict) -> tuple[list[tuple[str, bool]], list[str]]:
    """Die Modellantwort in saubere Absätze und offene Fragen."""
    absaetze: list[tuple[str, bool]] = []
    for eintrag in roh.get("absaetze") or []:
        if not isinstance(eintrag, dict):
            continue
        text = dokumenttext.xml_sicher(str(eintrag.get("text") or "")).strip()
        if text:
            absaetze.append((text, bool(eintrag.get("zitat"))))

    fragen: list[str] = []
    for frage in roh.get("offene_fragen") or []:
        sauber = dokumenttext.einzeilig(str(frage))
        if sauber and sauber not in fragen:
            fragen.append(sauber)
    return absaetze, fragen


# ─────────────────────────────────────────────────────────────────────────────
# Der Aufruf
# ─────────────────────────────────────────────────────────────────────────────


def _client():
    """Der Zugang zur Schnittstelle — mit Zeitgrenze und ohne Eigenleben.

    Beides ist nachgemessen und kein Vorsichtsschnörkel:

    ``timeout`` — ohne Angabe wartet das Paket zehn Minuten. Im Büronetz ist
    api.anthropic.com je nach Firewall gar nicht erreichbar; dann stünde die
    Oberfläche zehn Minuten auf "Wird formuliert…" und niemand wüsste, warum.
    Eine Minute und ein klarer Satz sind besser als zehn Minuten Warten.

    ``max_retries=0`` — das Paket wiederholt von sich aus zweimal, und
    ``schnittstelle.mit_wiederholung`` wiederholt außen dreimal. Zusammen sind
    das neun Anfragen und im schlechtesten Fall eine Viertelstunde. Wiederholt
    wird deshalb nur außen, wo die Wartezeiten hinterlegt sind.
    """
    import anthropic

    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=ZEITGRENZE_SEKUNDEN,
        max_retries=0,
    )


def _werkzeug_antwort(antwort, name: str) -> dict:
    for block in antwort.content:
        if block.type == "tool_use" and block.name == name:
            return dict(block.input or {})
    return {}


async def formuliere(auftrag: Auftrag) -> Ergebnis:
    """Aus den Stichpunkten die Absätze der Stellungnahme machen."""
    if not ist_verfuegbar():
        raise FormulierungFehler(warum_nicht())
    if not auftrag.stichpunkte.strip():
        raise FormulierungFehler(
            "Ohne Stichpunkte gibt es nichts zu formulieren. Bitte ins "
            "Infofeld schreiben, was in der Antwort stehen soll — Stichworte "
            "genügen."
        )

    text, hinweise = baue_anfrage(auftrag)
    client = _client()

    def ruf():
        return client.messages.create(
            model=CLAUDE_MODELL,
            max_tokens=MAX_TOKENS,
            system=ANWEISUNG,
            tools=[WERKZEUG],
            tool_choice={"type": "tool", "name": WERKZEUG["name"]},
            messages=[{"role": "user", "content": text}],
        )

    try:
        antwort = await schnittstelle.mit_wiederholung(ruf)
    except Exception as fehler:
        raise FormulierungFehler(schnittstelle.fehlertext(fehler)) from fehler

    if antwort is None:
        raise FormulierungFehler(
            "Die Schnittstelle hat nicht geantwortet. Bitte noch einmal "
            "versuchen — die Stichpunkte bleiben im Feld stehen."
        )

    absaetze, fragen = _aus_antwort(
        _werkzeug_antwort(antwort, WERKZEUG["name"])
    )
    if not absaetze:
        raise FormulierungFehler(
            "Es kam kein verwertbarer Text zurück. Bitte die Stichpunkte "
            "etwas ausführlicher fassen und noch einmal versuchen."
        )

    return Ergebnis(
        stellungnahme=zu_infofeld(absaetze),
        offene_fragen=fragen,
        hinweise=hinweise,
    )
