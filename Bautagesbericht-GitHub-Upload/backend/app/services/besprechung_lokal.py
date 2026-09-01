"""tl;dv-Text auswerten — ohne Internet, ohne Schlüssel, ohne Kosten.

WARUM ES DIESE ZWEITE AUSWERTUNG GIBT
=====================================
Die Auswertung über Claude (``besprechung_analyse``) braucht einen
Anthropic-Schlüssel. Wer keinen hat, stand bisher vor einer Funktion, die
nicht funktioniert — und musste jede Zeile von Hand tippen, obwohl der Text
aus tl;dv längst im Formular stand.

Dieses Modul macht die Arbeit ohne Modell: Es liest die tl;dv-Notizen als
das, was sie sind — eine Liste von Stichpunkten — und macht daraus
Themenvorschläge. Fristen, Zuständige und die Zuordnung zu laufenden Themen
holt es mit Regeln aus dem Text.

WAS ES KANN UND WAS NICHT
=========================
Es kann, was mechanisch entscheidbar ist:

  * Stichpunkte der tl;dv-Notizen als einzelne Themen trennen.
  * Fristen erkennen — "KW 36'26", "31.08.26", "bis 15.09.2026".
  * Zuständige erkennen, wenn ein Kürzel, ein Firmenname oder ein
    Ansprechpartner aus den Projektbeteiligten im Satz vorkommt.
  * Einen Punkt einem **laufenden Thema** zuordnen, wenn sich die Wortwahl
    deutlich überschneidet. Das ist die wichtigste Aufgabe überhaupt: Ohne
    sie wächst die Themenliste bei jeder Sitzung um Dubletten.
  * Sprecher aus dem Transkript als Teilnehmer vorschlagen.

Es kann nicht, was Sprachverständnis braucht:

  * Aus zehn Sätzen Gerede einen knappen Protokollsatz formulieren. Der
    Vorschlag ist der Stichpunkt, so wie tl;dv ihn geschrieben hat.
  * Ironie, Nebensätze oder "das machen wir doch nicht" erkennen.
  * Aus einem reinen Wortprotokoll ohne Notizen saubere Themen ziehen. Dafür
    ist der Text zu roh; das Modul sagt das dann auch.

Deshalb gilt hier dieselbe Regel wie überall in diesem Modul: Es **schlägt
vor**. Jede Zeile geht ungeprüft in die Prüfansicht und muss von einem
Menschen bestätigt werden, bevor sie in ein Dokument darf.

WARUM REGELN UND KEIN KLEINES MODELL
====================================
Ein lokales Sprachmodell wäre mehrere Gigabyte groß, müsste ins Windows-Paket
und würde auf einem Bürorechner ohne Grafikkarte Minuten je Besprechung
brauchen. Für eine Aufgabe, deren Ergebnis ohnehin Zeile für Zeile geprüft
wird, ist das nicht angemessen. Regeln sind hier ehrlicher: Sie sind schnell,
nachvollziehbar, und wo sie nichts wissen, behaupten sie nichts.
"""

from __future__ import annotations

import re
import unicodedata

from app.services.besprechung_analyse import (
    AnalyseErgebnis,
    BeteiligterInfo,
    KapitelInfo,
    OffenesThema,
    TeilnehmerVorschlag,
    ThemenVorschlag,
)

# ─────────────────────────────────────────────────────────────────────────────
# Wortschatz
# ─────────────────────────────────────────────────────────────────────────────

#: Wörter, die für den Vergleich zweier Themen nichts beitragen. Ohne diese
#: Liste gelten zwei Sätze schon als gleich, weil beide "wird" und "werden"
#: enthalten.
STOPPWOERTER = {
    "aber", "alle", "allen", "aller", "alles", "als", "also", "am", "an",
    "auch", "auf", "aus", "bei", "beim", "bereits", "bis", "bitte", "da",
    "damit", "dann", "das", "dass", "dem", "den", "denen", "der", "des",
    "dessen", "die", "dies", "diese", "diesem", "diesen", "dieser", "dieses",
    "doch", "dort", "durch", "ein", "eine", "einem", "einen", "einer",
    "eines", "er", "es", "etwa", "fuer", "ganz", "gegen", "gemaess", "hat",
    "hier", "ihr", "ihre", "im", "in", "ist", "ja", "je", "kann", "kein",
    "keine", "man", "mehr", "mit", "muss", "nach", "neue", "neuen", "nicht",
    "noch", "nur", "ob", "oder", "ohne", "schon", "sein", "seine", "sich",
    "sie", "sind", "so", "soll", "sollen", "sowie", "um", "und", "uns",
    "unter", "vom", "von", "vor", "war", "wenn", "werden", "wie", "wird",
    "wir", "zu", "zum", "zur", "zwei",
}

#: Endungen, die beim Vergleich abgeschnitten werden. Sehr grob, aber genau
#: das, was gebraucht wird: "Musterflaeche" und "Musterflaechen" sollen sich
#: treffen, ohne dass ein Wörterbuch im Paket liegen muss.
ENDUNGEN = ("ungen", "enden", "erung", "ungs", "ende", "chen", "lein", "isch",
            "ung", "en", "er", "es", "em", "et", "st", "te", "n", "e", "s")

#: Ein Punkt gilt als erledigt, wenn eines dieser Wörter darin steht.
WOERTER_ERLEDIGT = (
    "erledigt", "abgeschlossen", "abgenommen", "fertiggestellt", "behoben",
    "geliefert wurde", "ist eingebaut", "wurde umgesetzt", "wurde montiert",
    "wurde freigegeben", "wurde abgenommen",
)

#: … und als kritisch bei diesen.
WOERTER_KRITISCH = (
    "kritisch", "dringend", "gefaehrdet", "verzug", "eskalation", "stillstand",
    "behinderung", "baustopp", "sofort",
)

#: … und als reine Information, wenn nichts zu tun ist.
WOERTER_INFO = (
    "zur information", "zur kenntnis", "hinweis", "findet statt", "im turnus",
    "regelmaessig", "wie bisher", "unveraendert", "informativ",
)

#: Überschriften, die tl;dv über seine Abschnitte setzt. Sie sind selbst kein
#: Thema und fliegen raus.
UEBERSCHRIFTEN = (
    "zusammenfassung", "summary", "uebersicht", "wichtigste punkte",
    "wichtige punkte", "key points", "kernpunkte", "aufgaben", "action items",
    "to do", "todos", "naechste schritte", "next steps", "entscheidungen",
    "decisions", "teilnehmer", "participants", "agenda", "themen", "notizen",
    "meeting notes", "protokoll", "offene punkte", "beschluesse",
)

#: Zeilenanfänge, die einen Stichpunkt kennzeichnen.
AUFZAEHLUNG = re.compile(r"^\s*(?:[-*•·–—▪●○]|\d+[.)]|[a-z][.)])\s+")

#: Fristen, wie sie im Protokoll vorkommen. Reihenfolge = Vorrang.
FRIST_MUSTER = (
    # KW 35'26, KW35/26, KW 35 2026
    re.compile(r"\bKW\s*(\d{1,2})\s*['/\s]\s*(\d{2,4})\b", re.I),
    re.compile(r"\bKW\s*(\d{1,2})\b", re.I),
    # 31.08.26 / 31.08.2026
    re.compile(r"\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b"),
    # 31.08.
    re.compile(r"\b(\d{1,2}\.\d{1,2}\.)(?!\d)"),
)

#: Sprecherzeile eines tl;dv-Transkripts:
#:   [00:02:11] Katharina Blanck (HPP): Text
#:   00:02 Katharina Blanck: Text
#:   Katharina Blanck: Text
SPRECHER = re.compile(
    r"^\s*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*)?"      # Zeitstempel, optional
    r"([A-ZÄÖÜ][\wÄÖÜäöüß.\-]*(?:\s+[A-ZÄÖÜ][\wÄÖÜäöüß.\-]*){0,3})"  # Name
    r"\s*(?:\(([^)]{1,40})\))?\s*:\s+"                 # (Firma), Doppelpunkt
)

#: Wörter, die wie ein Name aussehen, aber keiner sind.
KEIN_NAME = {
    "sprecher", "speaker", "teilnehmer", "unbekannt", "unknown", "system",
    "zusammenfassung", "summary", "agenda", "notizen", "protokoll", "thema",
    "aufgabe", "hinweis", "frage", "antwort", "anmerkung", "kw", "uhr",
}

#: Ab dieser Übereinstimmung gilt ein Punkt als Fortschreibung eines
#: laufenden Themas. Bewusst nicht niedriger: Eine falsche Zusammenführung
#: verliert eine Zeile, eine verpasste erzeugt nur eine Dublette, die beim
#: Prüfen auffällt.
SCHWELLE = 0.5
#: … und mindestens so viele inhaltliche Wörter müssen sich überschneiden.
MIND_TREFFER = 2

#: Ausnahme für kurze Themen. Viele laufende Themen heißen nur
#: "Gerüstaufstockung" oder "Baumschutz" — ein einziges inhaltliches Wort.
#: Mit MIND_TREFFER = 2 wären die nie wiederzufinden, und die Liste bekäme
#: bei jeder Sitzung eine Dublette. Ein einzelnes Wort reicht deshalb, wenn
#: es lang genug ist, um kennzeichnend zu sein (deutsche Komposita sind das),
#: und die kurze Seite vollständig darin aufgeht.
EINWORT_LAENGE = 8
EINWORT_SCHWELLE = 0.9

#: Kürzeste bzw. längste Länge eines brauchbaren Stichpunkts.
MIN_LAENGE = 12
MAX_LAENGE = 1500


# ─────────────────────────────────────────────────────────────────────────────
# Text zerlegen und vergleichen
# ─────────────────────────────────────────────────────────────────────────────


def _ohne_umlaute(text: str) -> str:
    ersatz = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
              "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"}
    for a, b in ersatz.items():
        text = text.replace(a, b)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def _stamm(wort: str) -> str:
    """Grobe Grundform: schneidet die häufigsten Endungen ab."""
    for endung in ENDUNGEN:
        if len(wort) > len(endung) + 3 and wort.endswith(endung):
            return wort[: -len(endung)]
    return wort


def merkmale(text: str) -> set[str]:
    """Die inhaltlichen Wörter eines Textes, vergleichbar gemacht."""
    roh = _ohne_umlaute(str(text or "")).lower()
    woerter = re.findall(r"[a-z0-9]+", roh)
    return {
        _stamm(w)
        for w in woerter
        if len(w) >= 4 and w not in STOPPWOERTER
    }


def aehnlichkeit(a: set[str], b: set[str]) -> tuple[float, int]:
    """Überlappung zweier Wortmengen, plus die Zahl gemeinsamer Wörter.

    Bewusst der Überlappungskoeffizient und nicht Jaccard: Ein kurzer
    Stichpunkt ("Terminplan liefern") soll ein langes, ausformuliertes Thema
    treffen dürfen, ohne dass dessen Länge ihn bestraft.
    """
    if not a or not b:
        return 0.0, 0
    gemeinsam = a & b
    return len(gemeinsam) / min(len(a), len(b)), len(gemeinsam)


def passt_zusammen(eigene: set[str], andere: set[str]) -> tuple[bool, float]:
    """Gilt der Punkt als Fortschreibung dieses Themas?"""
    wert, treffer = aehnlichkeit(eigene, andere)
    if treffer >= MIND_TREFFER and wert >= SCHWELLE:
        return True, wert
    # Einwort-Themen: ein langes gemeinsames Wort genügt, wenn die kurze
    # Seite darin vollständig aufgeht.
    if treffer == 1 and wert >= EINWORT_SCHWELLE:
        gemeinsam = next(iter(eigene & andere))
        if len(gemeinsam) >= EINWORT_LAENGE:
            return True, wert
    return False, wert


# ─────────────────────────────────────────────────────────────────────────────
# Stichpunkte aus den tl;dv-Notizen
# ─────────────────────────────────────────────────────────────────────────────


def _ist_ueberschrift(zeile: str) -> bool:
    schlank = _ohne_umlaute(zeile).strip().strip("#*_ :").lower()
    if not schlank:
        return True
    if schlank in UEBERSCHRIFTEN:
        return True
    # "## Aufgaben", "**Wichtigste Punkte:**"
    if zeile.strip().startswith("#"):
        return True
    if len(schlank) <= 30 and zeile.rstrip().endswith(":"):
        return True
    return False


def stichpunkte(notizen: str) -> list[str]:
    """Zerlegt die tl;dv-Notizen in einzelne Punkte.

    tl;dv schreibt seine Notizen als Aufzählung unter Überschriften. Genau
    diese Struktur wird hier genutzt: Jeder Aufzählungspunkt ist ein Thema.
    Eingerückte Unterpunkte gehören zum Punkt darüber und bleiben als
    Zeilenumbruch erhalten — im Protokoll steht das genauso.
    """
    punkte: list[str] = []
    aktuell: list[str] = []
    fliesstext: list[str] = []
    #: Sobald irgendwo eine Aufzählung steht, IST die Aufzählung die Liste der
    #: Themen. Der Absatz unter "Zusammenfassung" ist dann nur noch Beiwerk und
    #: würde als Thema "Baubesprechung Nr. 17 auf dem Baufeld" im Protokoll
    #: landen. Deshalb wird Fließtext nur genommen, wenn es gar keine
    #: Aufzählung gibt.
    hat_aufzaehlung = False

    def abschliessen():
        if not aktuell:
            return
        text = "\n".join(z.rstrip() for z in aktuell).strip()
        if MIN_LAENGE <= len(text) <= MAX_LAENGE:
            punkte.append(text)
        aktuell.clear()

    for rohzeile in str(notizen or "").splitlines():
        zeile = rohzeile.rstrip()
        if not zeile.strip():
            abschliessen()
            continue
        if _ist_ueberschrift(zeile):
            abschliessen()
            continue

        treffer = AUFZAEHLUNG.match(zeile)
        if treffer:
            hat_aufzaehlung = True
            eingerueckt = len(zeile) - len(zeile.lstrip())
            inhalt = zeile[treffer.end():].strip()
            if eingerueckt >= 2 and aktuell:
                # Unterpunkt: gehört zum Punkt darüber.
                aktuell.append(f"- {inhalt}")
            else:
                abschliessen()
                aktuell.append(inhalt)
        elif aktuell:
            # Fortsetzung eines umgebrochenen Punktes.
            aktuell.append(zeile.strip())
        else:
            satz = zeile.strip()
            if len(satz) >= MIN_LAENGE and not satz.endswith(":"):
                fliesstext.append(satz)

    abschliessen()
    if not hat_aufzaehlung:
        punkte.extend(fliesstext)
    return punkte


def saetze_aus_transkript(transkript: str) -> list[str]:
    """Notlösung, wenn nur ein Wortprotokoll da ist.

    Aus dem Gerede werden nur Sätze genommen, die nach einer Festlegung
    aussehen: mit Frist, oder mit einem Verb der Verbindlichkeit. Alles
    andere wäre Rauschen und macht die Prüfung mehr Arbeit als das
    Abtippen.
    """
    verben = ("liefert", "liefern", "uebermittelt", "uebermitteln", "erstellt",
              "erstellen", "prueft", "pruefen", "klaert", "klaeren", "stellt",
              "meldet", "melden", "sendet", "senden", "baut", "montiert",
              "beauftragt", "bestellt", "vereinbart", "beschlossen",
              "zugesagt", "abgestimmt", "wird geliefert", "wird erstellt")
    treffer: list[str] = []
    gesehen: set[str] = set()

    for rohzeile in str(transkript or "").splitlines():
        zeile = SPRECHER.sub("", rohzeile).strip()
        if len(zeile) < MIN_LAENGE:
            continue
        for satz in re.split(r"(?<=[.!?])\s+", zeile):
            satz = satz.strip()
            if not (MIN_LAENGE <= len(satz) <= 300):
                continue
            flach = _ohne_umlaute(satz).lower()
            hat_frist = any(m.search(satz) for m in FRIST_MUSTER)
            hat_verb = any(v in flach for v in verben)
            if not (hat_frist or hat_verb):
                continue
            schluessel = " ".join(sorted(merkmale(satz)))
            if not schluessel or schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            treffer.append(satz)
    return treffer


# ─────────────────────────────────────────────────────────────────────────────
# Einzelne Angaben aus einem Punkt ziehen
# ─────────────────────────────────────────────────────────────────────────────


def frist_aus(text: str) -> str:
    """Die erste Frist im Text, geschrieben wie im Protokoll."""
    for i, muster in enumerate(FRIST_MUSTER):
        treffer = muster.search(text)
        if not treffer:
            continue
        if i == 0:
            woche, jahr = treffer.group(1), treffer.group(2)
            return f"KW {int(woche)}'{jahr[-2:]}"
        if i == 1:
            return f"KW {int(treffer.group(1))}"
        return treffer.group(1)
    return ""


#: Anreden und Titel, die vor einem Namen stehen und selbst keiner sind.
ANREDEN = {"herr", "frau", "hr", "fr", "dr", "prof", "dipl", "ing"}


def _nachname(ansprechpartner: str) -> str:
    """"Frau R. Stark" -> "Stark".

    Kurze Bruchstücke ("R.") und Anreden fallen weg. Unter vier Zeichen wird
    nichts zurückgegeben — "Bau" oder "Ott" würden sonst in halben Sätzen
    zufällig treffen und einen falschen Zuständigen ins Protokoll schreiben.
    """
    teile = [t.strip(" .,") for t in str(ansprechpartner or "").split()]
    for teil in reversed(teile):
        flach = _ohne_umlaute(teil).lower()
        if len(teil) >= 4 and flach not in ANREDEN and not teil.endswith("."):
            return teil
    return ""


def zustaendige_aus(text: str, beteiligte: list[BeteiligterInfo]) -> str:
    """Kürzel der Beteiligten, die in diesem Punkt vorkommen.

    Erkannt wird auf drei Wegen — Kürzel, Firmenname, Ansprechpartner —, denn
    in tl;dv-Notizen steht mal "ROL", mal "Rolfes Bau", mal "Frau Stark".
    Geraten wird nichts: Wer nicht in den Projektbeteiligten steht, taucht
    auch nicht als Zuständiger auf.
    """
    flach = _ohne_umlaute(text).lower()
    gefunden: list[str] = []

    for b in beteiligte:
        kuerzel = (b.kuerzel or "").strip()
        if not kuerzel:
            continue
        wege = [kuerzel]
        if b.name:
            wege.append(b.name)
        ansprechpartner = getattr(b, "ansprechpartner", "") or ""
        if ansprechpartner:
            wege.append(ansprechpartner)
            # Zusätzlich der blosse Nachname: In den Stammdaten steht
            # "Frau R. Stark", in den Notizen aber "Frau Stark" oder nur
            # "Stark". Ohne diesen Weg bliebe die Zeile ohne Zuständigen.
            nachname = _nachname(ansprechpartner)
            if nachname:
                wege.append(nachname)

        for weg in wege:
            begriff = _ohne_umlaute(str(weg)).lower().strip()
            if len(begriff) < 2:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(begriff)}(?![a-z0-9])", flach):
                if kuerzel.upper() not in gefunden:
                    gefunden.append(kuerzel.upper())
                break

    # "alle" / "ALL" steht im Protokoll für alle Beteiligten.
    if not gefunden and re.search(r"(?<![a-z])(alle|all)(?![a-z])", flach):
        gefunden.append("ALL")

    if not gefunden:
        return ""
    if len(gefunden) == 1:
        return gefunden[0]
    return "\n".join(f"{k}/" for k in gefunden[:-1]) + f"\n{gefunden[-1]}"


def status_aus(text: str, ist_fortschreibung: bool, hat_aufgabe: bool) -> str:
    flach = _ohne_umlaute(text).lower()
    if any(w in flach for w in WOERTER_KRITISCH):
        return "k"
    if any(w in flach for w in WOERTER_ERLEDIGT):
        return "e"
    if any(w in flach for w in WOERTER_INFO) and not hat_aufgabe:
        return "i"
    if ist_fortschreibung:
        return "b"
    return "n"


# ─────────────────────────────────────────────────────────────────────────────
# Teilnehmer aus dem Transkript
# ─────────────────────────────────────────────────────────────────────────────


def sprecher_aus(transkript: str,
                 beteiligte: list[BeteiligterInfo]) -> list[TeilnehmerVorschlag]:
    """Wer im Transkript gesprochen hat.

    tl;dv stellt jeder Zeile den Namen voran. Genau der wird gelesen — nicht
    geraten, wer sonst noch dabei gewesen sein könnte.
    """
    kuerzel_zu = {(b.kuerzel or "").upper(): b for b in beteiligte if b.kuerzel}
    gefunden: dict[str, TeilnehmerVorschlag] = {}

    for zeile in str(transkript or "").splitlines():
        treffer = SPRECHER.match(zeile)
        if not treffer:
            continue
        name = " ".join(treffer.group(1).split()).strip(" .-")
        if not name or len(name) < 3 or len(name) > 60:
            continue
        if _ohne_umlaute(name).lower() in KEIN_NAME:
            continue
        if not re.search(r"[A-ZÄÖÜ]", name):
            continue

        firma = ""
        klammer = (treffer.group(2) or "").strip().upper()
        if klammer in kuerzel_zu:
            firma = klammer
        else:
            # Ohne Klammer: über den Ansprechpartner der Projektbeteiligten.
            flach = _ohne_umlaute(name).lower()
            for b in beteiligte:
                ap = _ohne_umlaute(getattr(b, "ansprechpartner", "") or "").lower()
                nachname = flach.split()[-1] if flach.split() else ""
                if ap and nachname and len(nachname) >= 3 and nachname in ap:
                    firma = (b.kuerzel or "").upper()
                    break

        schluessel = _ohne_umlaute(name).lower()
        if schluessel not in gefunden:
            gefunden[schluessel] = TeilnehmerVorschlag(name=name, firma_kuerzel=firma)
        elif firma and not gefunden[schluessel].firma_kuerzel:
            gefunden[schluessel].firma_kuerzel = firma

    return list(gefunden.values())


# ─────────────────────────────────────────────────────────────────────────────
# Öffentliche Funktion
# ─────────────────────────────────────────────────────────────────────────────


def analysiere(
    *,
    transkript: str,
    notizen: str,
    offene_themen: list[OffenesThema],
    kapitel: list[KapitelInfo],
    beteiligte: list[BeteiligterInfo],
    projektname: str = "",
    besprechungsdatum: str = "",
) -> AnalyseErgebnis:
    """Wertet eine Besprechung ohne Modell aus.

    Gleiche Signatur und gleiches Ergebnis wie
    ``besprechung_analyse.analysiere`` — der Router muss nicht wissen, welcher
    Weg gerade benutzt wird.
    """
    hinweise: list[str] = []

    punkte = stichpunkte(notizen)
    aus_transkript = False
    if not punkte:
        punkte = saetze_aus_transkript(transkript)
        aus_transkript = bool(punkte)

    if not punkte:
        return AnalyseErgebnis(
            themen=[],
            teilnehmer=sprecher_aus(transkript, beteiligte),
            hinweise=[
                "Aus dem eingefügten Text ließen sich keine Themen ableiten. "
                "Am besten die tl;dv-Notizen einfügen — die stehen dort als "
                "Stichpunkte und lassen sich sauber trennen. Aus einem reinen "
                "Wortprotokoll gelingt das ohne KI nur, wenn Fristen oder "
                "klare Zusagen darin stehen."
            ],
        )

    if aus_transkript:
        hinweise.append(
            "Es lagen keine tl;dv-Notizen vor. Die Punkte stammen deshalb "
            "aus dem Wortprotokoll und sind roh — bitte die Formulierungen "
            "durchsehen und kürzen."
        )

    # Merkmale der laufenden Themen einmal vorberechnen.
    themen_merkmale = [(t, merkmale(t.text)) for t in offene_themen]

    erstes_kapitel = kapitel[0].id if kapitel else None
    vorschlaege: list[ThemenVorschlag] = []
    schon_zugeordnet: set[int] = set()
    ohne_zuordnung = 0

    for punkt in punkte:
        eigene = merkmale(punkt)

        # Bestes laufendes Thema suchen.
        bestes: OffenesThema | None = None
        bester_wert = 0.0
        for thema, thema_merkmale in themen_merkmale:
            if thema.id in schon_zugeordnet:
                continue
            passt, wert = passt_zusammen(eigene, thema_merkmale)
            if passt and wert > bester_wert:
                bestes, bester_wert = thema, wert

        frist = frist_aus(punkt)
        zustaendig = zustaendige_aus(punkt, beteiligte)
        hat_aufgabe = bool(frist or zustaendig)

        if bestes is not None:
            schon_zugeordnet.add(bestes.id)
            vorschlaege.append(ThemenVorschlag(
                thema_id=bestes.id,
                kapitel_id=None,
                text=punkt,
                zustaendig=zustaendig or bestes.zustaendig,
                bearb_bis=frist or bestes.bearb_bis,
                status=status_aus(punkt, True, hat_aufgabe),
                begruendung=(
                    f"Wortwahl stimmt zu {bester_wert * 100:.0f} % mit dem "
                    f"laufenden Thema {bestes.kennung.strip()} überein."
                ),
            ))
            continue

        if erstes_kapitel is None:
            continue

        # Neues Thema: Kapitel raten wir nicht — es landet im ersten und wird
        # beim Prüfen umgehängt. Ein falsch einsortiertes Thema faellt in der
        # Prüfansicht sofort auf, ein stillschweigend erfundenes nicht.
        ohne_zuordnung += 1
        vorschlaege.append(ThemenVorschlag(
            thema_id=None,
            kapitel_id=erstes_kapitel,
            text=punkt,
            zustaendig=zustaendig,
            bearb_bis=frist,
            status=status_aus(punkt, False, hat_aufgabe),
            begruendung=(
                "Kein laufendes Thema mit ähnlicher Wortwahl gefunden — als "
                "neu eingestuft. Bitte Kapitel prüfen."
            ),
        ))

    fortgeschrieben = sum(1 for v in vorschlaege if v.thema_id is not None)
    hinweise.insert(0, (
        f"Ohne KI ausgewertet: {len(vorschlaege)} Punkt(e) erkannt, davon "
        f"{fortgeschrieben} einem laufenden Thema zugeordnet. Die Zuordnung "
        f"beruht auf Wortübereinstimmung, nicht auf Sprachverständnis — bitte "
        f"besonders darauf achten, ob ein Punkt zum richtigen Thema gehört."
    ))
    if ohne_zuordnung and len(kapitel) > 1:
        hinweise.append(
            f"{ohne_zuordnung} neue(s) Thema/Themen liegen vorläufig in "
            f"„{kapitel[0].nummer} {kapitel[0].titel}“. Bitte in der "
            f"Prüfansicht ins richtige Kapitel umhängen."
        )
    ohne_frist = sum(1 for v in vorschlaege if not v.bearb_bis and v.status in "nbk")
    if ohne_frist:
        hinweise.append(
            f"{ohne_frist} Punkt(e) ohne erkannte Frist. Es wurde nichts "
            f"geschätzt — bitte von Hand eintragen, wo eine gilt."
        )

    return AnalyseErgebnis(
        themen=vorschlaege,
        teilnehmer=sprecher_aus(transkript, beteiligte),
        hinweise=hinweise,
    )
