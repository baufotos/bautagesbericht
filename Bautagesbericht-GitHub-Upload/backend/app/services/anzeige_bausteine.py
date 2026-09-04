"""Textbausteine und Glätten — die Stellungnahme ohne Sprachmodell schreiben.

WOZU ES DAS GIBT
================
Das Ausformulieren aus freien Notizen (``anzeige_formulierung``) braucht einen
Anthropic-Schlüssel. Den gibt es im Büro nicht überall. Dieses Modul ist der
Weg ohne: Es *versteht* nichts, aber es kann zwei Dinge, die im Alltag den
größten Teil der Arbeit sind.

    Bausteine   Die Standardsätze des Büros anklickbar. Neun von zehn
                Beanstandungen laufen auf dieselbe Handvoll Sätze hinaus —
                "im LV enthalten und mit den EP's abgegolten", "dies ist eine
                Zusatzleistung, Abrechnung über Pos. ...". Die tippt niemand
                gern zum vierzigsten Mal.
    Glätten     Aus Stichworten werden Sätze der Form, nicht des Inhalts:
                Aufzählungszeichen werden zu "1)", Abkürzungen bekommen ihre
                Schreibweise ("lv" -> "LV", "pos 3.11" -> "Pos. 3.11"), Zeilen
                fangen groß an und enden mit einem Punkt.

WAS GLÄTTEN NICHT TUT
=====================
Es erfindet keinen Inhalt und formuliert nichts um. Aus "EP abgegolten" wird
"EP abgegolten." — ein Satz wird daraus erst, wenn ein Baustein daneben steht.
Diese Grenze ist wichtig: Wer glaubt, das Glätten schreibe den Brief, schickt
Stichworte an eine Baufirma. Deshalb heißt der Knopf in der Oberfläche
"Stichworte glätten" und nicht "ausformulieren".

WOHER DIE SÄTZE KOMMEN
======================
Aus den acht echten Antwortschreiben des Büros von 2020 bis 2026. Wo eine
Angabe von Fall zu Fall wechselt, steht eine Lücke ``___``, die im Formular
gefüllt wird. Nichts hier ist ausgedacht — es sind die Formulierungen, die das
Büro selbst benutzt. Wer sie ändert, ändert sie hier, an einer Stelle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services import dokumenttext

#: Die Lücke in einem Baustein. Genau drei Unterstriche — kurz genug, um im
#: Satz nicht zu störren, lang genug, um beim Gegenlesen aufzufallen.
LUECKE = "___"


@dataclass
class Baustein:
    """Ein Satz des Büros, fertig zum Einsetzen."""

    kennung: str
    #: Kurze Beschriftung für den Knopf.
    titel: str
    #: Der Satz selbst. ``___`` markiert eine auszufüllende Stelle.
    text: str
    #: Für welche Haltung er passt — leer heißt: für jede.
    haltungen: tuple[str, ...] = ()
    #: Eingerückt einsetzen (LV-Zitat).
    zitat: bool = False


@dataclass
class Gruppe:
    """Bausteine, die zum selben Anlass gehören."""

    kennung: str
    titel: str
    bausteine: list[Baustein] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Der Katalog
#
# Reihenfolge nach Häufigkeit im Büro: erst das Vertragssoll, dann Zusatz-
# leistungen, dann Bauzeit, dann Behinderung, dann Prüfung, dann der Schluss.
# ─────────────────────────────────────────────────────────────────────────────

KATALOG: tuple[Gruppe, ...] = (
    Gruppe(
        kennung="vertragssoll",
        titel="Vertragssoll — Leistung ist geschuldet",
        bausteine=[
            Baustein(
                "kein_anspruch", "Kein Mehrvergütungsanspruch",
                "Wir sehen hier keinen Mehrvergütungsanspruch. In der "
                "Ausschreibung bzw. in Ihrem Auftrags-LV ist Ihr Vertragssoll "
                "dargelegt.",
                haltungen=("ablehnung", "teilweise"),
            ),
            Baustein(
                "im_lv_enthalten", "Im LV enthalten, mit EP's abgegolten",
                "Diese Leistungen sind im Leistungsverzeichnis enthalten und "
                "mit den Einheitspreisen abgegolten.",
                haltungen=("ablehnung", "teilweise"),
            ),
            Baustein(
                "hauptauftrag", "Im Hauptauftrag enthalten",
                "Diese Leistung ist im Hauptauftrag enthalten. Hier wird keine "
                "Mehrleistung anerkannt.",
                haltungen=("ablehnung", "teilweise"),
            ),
            Baustein(
                "erkennbar", "War bei Angebotslegung erkennbar",
                f"Aufgrund des Eingriffs in den Bestand war Ihnen bereits zur "
                f"Angebotslegung bekannt, dass {LUECKE}. Hierauf wurde im LV "
                f"ausdrücklich hingewiesen.",
                haltungen=("ablehnung", "teilweise"),
            ),
            Baustein(
                "planunterlagen", "Aus Planunterlagen ersichtlich",
                "Die Einbausituation gemäß Planunterlagen und technischem "
                "Vergabegespräch war für Sie klar ersichtlich.",
                haltungen=("ablehnung", "teilweise"),
            ),
            Baustein(
                "unterbrechungen", "Unterbrechungen einzukalkulieren",
                "Zeitliche Unterbrechungen sind einzukalkulieren und mit den "
                "EP's abgegolten.",
                haltungen=("ablehnung", "teilweise"),
            ),
            Baustein(
                "be_kosten", "BE-Kosten und Anfahrten abgegolten",
                "Sämtliche BE-Kosten und zusätzlichen Anfahrten sind "
                "einzukalkulieren und mit den Einheitspreisen abgegolten.",
                haltungen=("ablehnung", "teilweise"),
            ),
            Baustein(
                "nebenleistung", "Nebenleistung, nicht gesondert vergütet",
                f"Die {LUECKE} gilt als Nebenleistung und wird nicht gesondert "
                f"vergütet.",
                haltungen=("ablehnung", "teilweise"),
            ),
            Baustein(
                "nach_abruf", "Leistung erfolgt nach Abruf",
                "Die Leistung erfolgt nach Abruf durch die Objektüberwachung "
                "und ist mit keinem vertraglich fixierten Termin verbunden.",
                haltungen=("ablehnung", "teilweise", "kenntnisnahme"),
            ),
            Baustein(
                "pos_vorhanden", "Es gibt eine Position im LV",
                f"Hier können wir Ihren Ausführungen nicht folgen, da es im LV "
                f"mit Pos. {LUECKE} eine Position gibt, über die diese Leistung "
                f"abgerechnet werden kann.",
                haltungen=("ablehnung", "teilweise"),
            ),
        ],
    ),
    Gruppe(
        kennung="zusatzleistung",
        titel="Zusatzleistung — Leistung wird anerkannt",
        bausteine=[
            Baustein(
                "ist_zusatz", "Dies ist eine Zusatzleistung",
                f"Dies ist eine Zusatzleistung. Die Abrechnung erfolgt über "
                f"Pos. {LUECKE} im LV.",
                haltungen=("anerkennung", "teilweise"),
            ),
            Baustein(
                "preislich_bewerten", "Preislich zu bewerten",
                f"Die {LUECKE} sehen wir als zusätzliche Leistung; sie ist "
                f"preislich zu bewerten.",
                haltungen=("anerkennung", "teilweise"),
            ),
            Baustein(
                "nachtragsangebot", "Prüffähiges Nachtragsangebot vorlegen",
                "Wir bitten um Vorlage eines prüffähigen Nachtragsangebots auf "
                "Grundlage der vertraglichen Preise.",
                haltungen=("anerkennung", "teilweise", "pruefung"),
            ),
            Baustein(
                "minderkosten", "Minderkosten angeben",
                f"Da {LUECKE} entfällt, bitten wir hier um Angabe der "
                f"Minderkosten.",
                haltungen=("anerkennung", "teilweise"),
            ),
        ],
    ),
    Gruppe(
        kennung="bauzeit",
        titel="Bauzeit und Termine",
        bausteine=[
            Baustein(
                "bauzeit_ab", "Bauzeitverlängerung abgelehnt",
                "Die hieraus resultierende Bauzeitverlängerung kann seitens AG "
                "nicht akzeptiert werden und wird vollumfänglich abgelehnt.",
                haltungen=("ablehnung", "teilweise"),
            ),
            Baustein(
                "kein_endtermin", "Keine Auswirkung auf den Endtermin",
                "Eine Auswirkung auf den Gesamtfertigstellungstermin haben die "
                "vorstehend aufgeführten Arbeiten nicht.",
                haltungen=(),
            ),
            Baustein(
                "kritischer_weg", "Nicht auf dem kritischen Weg",
                f"Wir weisen erneut darauf hin, dass sich die {LUECKE} nicht auf "
                f"dem kritischen Weg befinden.",
                haltungen=("ablehnung", "teilweise"),
            ),
            Baustein(
                "abgestimmt", "Arbeiten waren angekündigt und abgestimmt",
                f"Die Arbeiten wurden gemäß Punkt {LUECKE} der Baubesprechung "
                f"vom {LUECKE} angekündigt und mit Ihnen abgestimmt.",
                haltungen=(),
            ),
            Baustein(
                "schlechtwetter", "Schlechtwettertage kompensieren",
                f"Wir gehen davon aus, dass die vertraglich zugesicherten und in "
                f"der Ausführungszeit enthaltenen {LUECKE} Schlechtwettertage "
                f"durch geeignete Maßnahmen kompensiert werden, um den "
                f"vertraglich fixierten Endtermin einzuhalten.",
                haltungen=("ablehnung", "teilweise"),
            ),
        ],
    ),
    Gruppe(
        kennung="behinderung",
        titel="Behinderung",
        bausteine=[
            Baustein(
                "zuwegung", "Zuwegung war nicht betroffen",
                "Die Zuwegung zur Baustelle war während der Ausführung der "
                "Arbeiten nicht betroffen.",
                haltungen=("ablehnung", "teilweise"),
            ),
            Baustein(
                "haette_koennen", "Ausführung wäre möglich gewesen",
                f"Die Arbeiten hätten, wie in der Baubesprechung vom {LUECKE} "
                f"angekündigt, ab dem {LUECKE} durchgeführt werden können.",
                haltungen=("ablehnung", "teilweise"),
            ),
            Baustein(
                "wiederaufnahme", "Wiederaufnahme erwartet",
                f"Wir gehen davon aus, dass Sie die Arbeiten ab dem {LUECKE} "
                f"wieder aufnehmen und es keine Auswirkungen auf die Zeitschiene "
                f"gibt.",
                haltungen=(),
            ),
            Baustein(
                "beh_ablehnung", "Behinderungsanzeige abgelehnt",
                "Aus den vorgenannten Gründen lehnen wir Ihre "
                "Behinderungsanzeige ab.",
                haltungen=("ablehnung",),
            ),
        ],
    ),
    Gruppe(
        kennung="pruefung",
        titel="Prüfung und Nachweise",
        bausteine=[
            Baustein(
                "in_pruefung", "Noch in Prüfung",
                "Ihre Anzeige befindet sich derzeit in Prüfung. Wir kommen "
                "hierauf unaufgefordert zurück.",
                haltungen=("pruefung",),
            ),
            Baustein(
                "nachweis", "Nachweis nachreichen",
                f"Im Zuge Ihrer Eigenüberwachung bitten wir um Vorlage der "
                f"Nachweise {LUECKE}.",
                haltungen=("pruefung", "teilweise", "ablehnung"),
            ),
            Baustein(
                "abstimmung", "Abstimmung bis zu einem Termin",
                f"Die Abstimmung zwischen HPP und {LUECKE} erfolgt bis zum "
                f"{LUECKE}.",
                haltungen=("pruefung", "teilweise"),
            ),
            Baustein(
                "fortfuehren", "Leistungen weiter ausführen",
                "Bis dahin bitten wir, die Leistungen vertragsgemäß "
                "fortzuführen.",
                haltungen=("pruefung",),
            ),
        ],
    ),
    Gruppe(
        kennung="lv",
        titel="LV-Auszug zitieren",
        bausteine=[
            Baustein(
                "lv_marke", "Auszug LV: (Einleitung)",
                "Auszug LV:",
                haltungen=(),
            ),
            Baustein(
                "lv_zeile", "Zitatzeile (eingerückt)",
                LUECKE,
                haltungen=(),
                zitat=True,
            ),
        ],
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Auswahl
# ─────────────────────────────────────────────────────────────────────────────


def fuer_haltung(haltung: str = "") -> list[Gruppe]:
    """Die Bausteine, die zur gewählten Haltung passen.

    Gefiltert, nicht sortiert: Ein Baustein, der zur Ablehnung nicht passt,
    soll bei einer Ablehnung gar nicht angeboten werden. Wer eine Anzeige
    ablehnt, braucht "Dies ist eine Zusatzleistung" nicht in der Liste — und
    ein Fehlklick dorthin wäre ein Satz, der das Gegenteil des Gemeinten sagt.

    Ohne Angabe kommt der ganze Katalog.
    """
    if not haltung:
        return [Gruppe(g.kennung, g.titel, list(g.bausteine)) for g in KATALOG]

    gefiltert: list[Gruppe] = []
    for gruppe in KATALOG:
        passend = [
            b for b in gruppe.bausteine
            if not b.haltungen or haltung in b.haltungen
        ]
        if passend:
            gefiltert.append(Gruppe(gruppe.kennung, gruppe.titel, passend))
    return gefiltert


# ─────────────────────────────────────────────────────────────────────────────
# Glätten
# ─────────────────────────────────────────────────────────────────────────────

#: Abkürzungen des Büros mit ihrer richtigen Schreibweise. Ersetzt wird nur
#: das ganze Wort, nie ein Wortteil — sonst würde aus "Lage" ein "LAge".
SCHREIBWEISEN: tuple[tuple[str, str], ...] = (
    (r"lv", "LV"),
    (r"lvs", "LV"),
    (r"ag", "AG"),
    (r"an", "AN"),          # nur als eigenes Wort, siehe _WORTGRENZE
    (r"ep", "EP"),
    (r"eps", "EP's"),
    (r"ep's", "EP's"),
    (r"be", "BE"),
    (r"bzp", "BZP"),
    (r"ztv", "ZTV"),
    (r"din", "DIN"),
    (r"vob", "VOB"),
    (r"kw", "KW"),
    (r"og", "OG"),
    (r"ug", "UG"),
    (r"eg", "EG"),
    (r"kmf", "KMF"),
    (r"gk", "GK"),
    (r"hpp", "HPP"),
)

#: Wörter, die nach dem Glätten NICHT großgeschrieben werden dürfen, obwohl
#: sie in ``SCHREIBWEISEN`` stehen: "an" und "be" sind auch gewöhnliche
#: deutsche Wörter. Sie werden nur ersetzt, wenn sie allein oder mit Bindestrich
#: stehen ("BE-Kosten", "der AN").
_NUR_MIT_KONTEXT = {"an", "be"}

_LUECKENFUELLER = re.compile(r"_{2,}")


def glaette(text: str) -> tuple[str, list[str]]:
    """Stichworte in Briefform bringen — Form, nicht Inhalt.

    Was passiert:

        "- pos 3.11 ausgeschrieben, ep abgegolten"
        ->  "1) Pos. 3.11 ausgeschrieben, EP abgegolten."

    Was **nicht** passiert: Es entsteht kein Satz, wo keiner war. "EP
    abgegolten" bleibt "EP abgegolten." — für ganze Sätze sind die Bausteine
    da. Zurückgegeben wird zusätzlich, was auffiel: offene Lücken, sehr kurze
    Zeilen.
    """
    zeilen = dokumenttext.zeilen(text)
    if not zeilen:
        return "", []

    hinweise: list[str] = []
    raus: list[str] = []
    nummer = 0
    im_zitat = False

    for rohzeile in zeilen:
        zeile = rohzeile.strip()
        if not zeile:
            # Nur eine Leerzeile beginnt eine neue Aufzählung. Ein Satz
            # zwischen zwei Punkten tut das nicht — sonst stünde nach einem
            # eingesetzten Baustein wieder "1)" und der Brief hätte zwei
            # Punkte mit derselben Nummer.
            raus.append("")
            im_zitat = False
            nummer = 0
            continue

        if _ist_zitatmarke(zeile):
            raus.append(_satzform(zeile, punkt=False))
            im_zitat = True
            continue

        if im_zitat:
            # Zitate bleiben, wie sie sind: Ein Auszug aus dem LV wird nicht
            # geglättet, sonst stimmt das Zitat nicht mehr.
            raus.append(zeile)
            continue

        aufzaehlung = re.match(r"^\s*(?:[-–•*]|\d{1,2}[.)])\s+(.*)$", zeile)
        if aufzaehlung:
            nummer += 1
            rest = _satzform(_abkuerzungen(aufzaehlung.group(1)))
            raus.append(f"{nummer}) {rest}")
            continue

        raus.append(_satzform(_abkuerzungen(zeile)))

    ergebnis = "\n".join(raus).strip("\n")

    if _LUECKENFUELLER.search(ergebnis):
        hinweise.append(
            f"Im Text stehen noch Lücken „{LUECKE}“ — bitte ausfüllen, bevor "
            f"das Schreiben erzeugt wird."
        )
    kurze = [z for z in raus if z and len(z.split()) <= 3 and not _ist_zitatmarke(z)]
    if kurze:
        hinweise.append(
            "Sehr kurze Zeilen sind noch Stichworte, keine Sätze: "
            + "; ".join(f"„{z}“" for z in kurze[:3])
            + ". Ein passender Textbaustein macht daraus einen Satz."
        )
    if _viel_kleingeschrieben(ergebnis):
        # Die Grenze dieses Moduls, offen ausgesprochen: Ob "anspruch" ein
        # Substantiv ist, weiß nur ein Wörterbuch. Eine halb richtige
        # Großschreibung wäre schlimmer als keine — deshalb wird sie nicht
        # geraten, sondern gemeldet.
        hinweise.append(
            "Die Großschreibung der Substantive bitte selbst prüfen — geglättet "
            "werden nur Aufzählung, Abkürzungen und Satzzeichen, nicht die "
            "Rechtschreibung."
        )
    return ergebnis, hinweise


def _viel_kleingeschrieben(text: str) -> bool:
    """Ist der Text offenkundig durchgehend klein getippt?

    Gemessen wird an den Wörtern, die nicht am Satzanfang stehen: Sind davon
    fast alle klein, hat jemand ohne Umschalttaste getippt.
    """
    woerter = re.findall(r"(?<![.!?:]\s)\b[A-Za-zÄÖÜäöüß]{4,}\b", text)
    if len(woerter) < 6:
        return False
    gross = sum(1 for w in woerter if w[0].isupper())
    return gross / len(woerter) < 0.15


def _ist_zitatmarke(zeile: str) -> bool:
    from app.services.mehrkostenanzeige_generation import ZITAT_MARKEN

    schlicht = zeile.strip().lower()
    return schlicht in ZITAT_MARKEN or schlicht.rstrip(":") + ":" in ZITAT_MARKEN


def _abkuerzungen(text: str) -> str:
    """Abkürzungen in die Schreibweise des Büros bringen."""

    def ersetze(treffer: re.Match) -> str:
        wort = treffer.group(0)
        klein = wort.lower()
        for muster, richtig in SCHREIBWEISEN:
            if klein != muster:
                continue
            if klein in _NUR_MIT_KONTEXT:
                # "an" und "be" sind auch gewöhnliche Wörter. Ersetzt wird nur,
                # was schon groß geschrieben war oder an einem Bindestrich
                # klebt ("BE-Kosten") — sonst würde aus "an der Wand" ein
                # "AN der Wand".
                folgt = treffer.string[treffer.end(): treffer.end() + 1]
                if not (wort.isupper() or folgt == "-"):
                    return wort
            return richtig
        return wort

    gerade = re.sub(r"[A-Za-zÄÖÜäöüß']+", ersetze, text)

    # "pos 3.11" / "position 3.11" -> "Pos. 3.11"
    gerade = re.sub(
        r"\b(?:pos|position)\.?\s*(?=[\d])", "Pos. ", gerade, flags=re.IGNORECASE
    )
    # "§2 abs 6 vob/b" -> "§ 2 Abs. 6 VOB/B"
    gerade = re.sub(r"§\s*(\d)", r"§ \1", gerade)
    gerade = re.sub(
        r"\babs\.?\s*(?=\d)", "Abs. ", gerade, flags=re.IGNORECASE
    )
    gerade = re.sub(r"\bVOB\s*/\s*([abAB])\b",
                    lambda m: "VOB/" + m.group(1).upper(), gerade)

    # Nach einer Abkürzung mit Bindestrich steht im Deutschen ein Substantiv:
    # "BE-Kosten", "KMF-Sanierung", "GK-Ständerwand". Ohne diesen Schritt
    # entstünde "BE-kosten" — halb geändert sieht schlimmer aus als gar nicht.
    gerade = re.sub(
        r"\b([A-ZÄÖÜ]{2,}(?:'s)?)-([a-zäöü])",
        lambda m: f"{m.group(1)}-{m.group(2).upper()}",
        gerade,
    )
    return re.sub(r"\s{2,}", " ", gerade).strip()


def _satzform(text: str, *, punkt: bool = True) -> str:
    """Satzanfänge groß, am Ende ein Satzzeichen.

    Großgeschrieben wird jeder Satzanfang, nicht nur der Zeilenanfang: Wer
    zwei Sätze in eine Zeile tippt, soll nicht den zweiten von Hand
    nachbessern müssen. Substantive bleiben unangetastet — siehe
    ``_viel_kleingeschrieben``.
    """
    sauber = text.strip()
    if not sauber:
        return ""
    if sauber[0].islower():
        sauber = sauber[0].upper() + sauber[1:]
    sauber = re.sub(
        r"([.!?]\s+)([a-zäöüß])",
        lambda m: m.group(1) + m.group(2).upper(),
        sauber,
    )
    if punkt and sauber[-1] not in ".!?:;":
        sauber += "."
    return sauber
