r"""Die Musterordner-Struktur eines McDonald's-Standorts — als Liste im Code.

WOHER DIESE LISTE KOMMT
=======================
Ausgelesen aus dem Musterordner des Büros

    M:\HAM-226010\STANDORTE\x_CODE_NAME (Muster) [leer]

am 10.09.2026: 163 Ordner, 5 Dateien. Erzeugt, nicht getippt —
die Reihenfolge ist die sortierte Pfadliste.

WARUM ES DIE LISTE ÜBERHAUPT GIBT, OBWOHL ES DEN ORDNER GIBT
============================================================
Der Musterordner ist die Wahrheit, solange er erreichbar ist: Ändert das Büro
ihn, soll der nächste Standort die neue Struktur bekommen, ohne dass jemand
Programmcode anfasst. Genau deshalb kopiert ``mcdonalds_ordner`` bevorzugt den
echten Ordner.

Das Laufwerk ist aber nicht immer da — beim Einrichten, beim Ausprobieren am
Rechner ohne Netz, und auf dem Server im Internet grundsätzlich nicht. Ohne
diese Liste könnte die App dann gar keinen Standort anlegen. Mit ihr entsteht
dieselbe Struktur, nur ohne die beiden PDF-Vorlagen (die stecken naturgemäß
nicht in einer Liste von Namen).

``test_mcdonalds.py`` vergleicht die Liste mit dem Musterordner, wenn er
erreichbar ist. Läuft der Vergleich auf einen Unterschied, ist entweder die
Liste veraltet oder im Musterordner hat jemand etwas verschoben — beides will
man wissen, bevor fünfzig Standorte falsch angelegt sind.

NEU ERZEUGEN
============
Nicht von Hand pflegen. Bei einer Änderung am Musterordner:

    python -c "from pathlib import Path; p=Path(r'<Musterordner>');       print(chr(10).join(sorted(q.relative_to(p).as_posix()       for q in p.rglob('*') if q.is_dir())))"

und das Ergebnis unten einsetzen.

PLATZHALTERNAMEN BLEIBEN STEHEN
===============================
``JJMMTT_Bauantrag``, ``0XX_Sachverhalt xy``, ``Firma A`` und
``_0XX_Fachbereich_Subplaner`` sind keine Fehler, sondern die Schreibvorgabe
des Büros für den Tag, an dem es diesen Vorgang wirklich gibt. Sie werden
deshalb unverändert übernommen — ein beim Anlegen eingesetztes Datum wäre
geraten und stünde für immer falsch im Pfad.
"""

#: Name des Musterordners in ``STANDORTE``. Steht hier, weil ihn zwei Stellen
#: brauchen: der Kopierweg (als Quelle) und die Prüfung im Test.
MUSTERORDNER_NAME = "x_CODE_NAME (Muster) [leer]"

#: Alle Unterordner eines Standorts, relativ zum Standortordner.
UNTERORDNER: list[str] = [
    "18-GP",
    "18-GP/12_Verträge",
    "18-GP/12_Verträge/01_Generalplaner",
    "18-GP/12_Verträge/01_Generalplaner/01_Angebot",
    "18-GP/12_Verträge/01_Generalplaner/02_Vertrag",
    "18-GP/12_Verträge/01_Generalplaner/03_Schriftverkehr",
    "18-GP/12_Verträge/01_Generalplaner/04_Rechnungen",
    "18-GP/12_Verträge/01_Generalplaner/05_Nachträge",
    "18-GP/12_Verträge/02_Subplaner",
    "18-GP/12_Verträge/02_Subplaner/010_OPG_ARC_RKA",
    "18-GP/12_Verträge/02_Subplaner/010_OPG_ARC_RKA/01_Angebot",
    "18-GP/12_Verträge/02_Subplaner/010_OPG_ARC_RKA/02_Vertrag",
    "18-GP/12_Verträge/02_Subplaner/010_OPG_ARC_RKA/03_Schriftverkehr",
    "18-GP/12_Verträge/02_Subplaner/010_OPG_ARC_RKA/04_Rechnungen",
    "18-GP/12_Verträge/02_Subplaner/010_OPG_ARC_RKA/05_Nachträge",
    "18-GP/12_Verträge/02_Subplaner/030_TWP_Imagine Structure",
    "18-GP/12_Verträge/02_Subplaner/030_TWP_Imagine Structure/01_Angebot",
    "18-GP/12_Verträge/02_Subplaner/030_TWP_Imagine Structure/02_Vertrag",
    "18-GP/12_Verträge/02_Subplaner/030_TWP_Imagine Structure/03_Schriftverkehr",
    "18-GP/12_Verträge/02_Subplaner/030_TWP_Imagine Structure/03_Schriftverkehr/0XX_Sachverhalt xy",
    "18-GP/12_Verträge/02_Subplaner/030_TWP_Imagine Structure/03_Schriftverkehr/0XX_Sachverhalt xy/jjmmtt_Vorgang xy",
    "18-GP/12_Verträge/02_Subplaner/030_TWP_Imagine Structure/04_Rechnungen",
    "18-GP/12_Verträge/02_Subplaner/030_TWP_Imagine Structure/05_Nachträge",
    "18-GP/12_Verträge/02_Subplaner/050_Bauphysik_Graner",
    "18-GP/12_Verträge/02_Subplaner/050_Bauphysik_Graner/01_Angebot",
    "18-GP/12_Verträge/02_Subplaner/050_Bauphysik_Graner/02_Vertrag",
    "18-GP/12_Verträge/02_Subplaner/050_Bauphysik_Graner/03_Schriftverkehr",
    "18-GP/12_Verträge/02_Subplaner/050_Bauphysik_Graner/03_Schriftverkehr/0XX_Sachverhalt xy",
    "18-GP/12_Verträge/02_Subplaner/050_Bauphysik_Graner/03_Schriftverkehr/0XX_Sachverhalt xy/jjmmtt_Vorgang xy",
    "18-GP/12_Verträge/02_Subplaner/050_Bauphysik_Graner/04_Rechnungen",
    "18-GP/12_Verträge/02_Subplaner/050_Bauphysik_Graner/05_Nachträge",
    "18-GP/12_Verträge/02_Subplaner/090_VAA_Kocks",
    "18-GP/12_Verträge/02_Subplaner/090_VAA_Kocks/01_Angebot",
    "18-GP/12_Verträge/02_Subplaner/090_VAA_Kocks/02_Vertrag",
    "18-GP/12_Verträge/02_Subplaner/090_VAA_Kocks/03_Schriftverkehr",
    "18-GP/12_Verträge/02_Subplaner/090_VAA_Kocks/03_Schriftverkehr/0XX_Sachverhalt xy",
    "18-GP/12_Verträge/02_Subplaner/090_VAA_Kocks/03_Schriftverkehr/0XX_Sachverhalt xy/jjmmtt_Vorgang xy",
    "18-GP/12_Verträge/02_Subplaner/090_VAA_Kocks/04_Rechnungen",
    "18-GP/12_Verträge/02_Subplaner/090_VAA_Kocks/05_Nachträge",
    "18-GP/12_Verträge/02_Subplaner/091_ARC_HUG Geoconsult",
    "18-GP/12_Verträge/02_Subplaner/091_ARC_HUG Geoconsult/01_Angebot",
    "18-GP/12_Verträge/02_Subplaner/091_ARC_HUG Geoconsult/02_Vertrag",
    "18-GP/12_Verträge/02_Subplaner/091_ARC_HUG Geoconsult/03_Schriftverkehr",
    "18-GP/12_Verträge/02_Subplaner/091_ARC_HUG Geoconsult/03_Schriftverkehr/0XX_Sachverhalt xy",
    "18-GP/12_Verträge/02_Subplaner/091_ARC_HUG Geoconsult/03_Schriftverkehr/0XX_Sachverhalt xy/jjmmtt_Vorgang xy",
    "18-GP/12_Verträge/02_Subplaner/091_ARC_HUG Geoconsult/04_Rechnungen",
    "18-GP/12_Verträge/02_Subplaner/091_ARC_HUG Geoconsult/05_Nachträge",
    "18-GP/12_Verträge/02_Subplaner/092_Drohnenflug_Teamwork",
    "18-GP/12_Verträge/02_Subplaner/092_Drohnenflug_Teamwork/01_Angebot",
    "18-GP/12_Verträge/02_Subplaner/092_Drohnenflug_Teamwork/02_Vertrag",
    "18-GP/12_Verträge/02_Subplaner/092_Drohnenflug_Teamwork/03_Schriftverkehr",
    "18-GP/12_Verträge/02_Subplaner/092_Drohnenflug_Teamwork/03_Schriftverkehr/0XX_Sachverhalt xy",
    "18-GP/12_Verträge/02_Subplaner/092_Drohnenflug_Teamwork/03_Schriftverkehr/0XX_Sachverhalt xy/jjmmtt_Vorgang xy",
    "18-GP/12_Verträge/02_Subplaner/092_Drohnenflug_Teamwork/04_Rechnungen",
    "18-GP/12_Verträge/02_Subplaner/092_Drohnenflug_Teamwork/05_Nachträge",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/01_Angebot",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/01_Angebot/Firma A",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/01_Angebot/Firma A/01_Versand LV",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/01_Angebot/Firma A/02_Angebot",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/01_Angebot/Firma B",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/01_Angebot/Firma B/01_Versand LV",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/01_Angebot/Firma B/02_Angebot",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/01_Angebot/Firma C",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/01_Angebot/Firma C/01_Versand LV",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/01_Angebot/Firma C/02_Angebot",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/02_Vertrag",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/03_Schriftverkehr",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/04_Rechnungen",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/05_Nachträge",
    "18-GP/12_Verträge/02_Subplaner/_0XX_Fachbereich_Subplaner",
    "18-GP/12_Verträge/02_Subplaner/_0XX_Fachbereich_Subplaner/01_Angebot",
    "18-GP/12_Verträge/02_Subplaner/_0XX_Fachbereich_Subplaner/02_Vertrag",
    "18-GP/12_Verträge/02_Subplaner/_0XX_Fachbereich_Subplaner/03_Schriftverkehr",
    "18-GP/12_Verträge/02_Subplaner/_0XX_Fachbereich_Subplaner/03_Schriftverkehr/0XX_Sachverhalt xy",
    "18-GP/12_Verträge/02_Subplaner/_0XX_Fachbereich_Subplaner/03_Schriftverkehr/0XX_Sachverhalt xy/jjmmtt_Vorgang xy",
    "18-GP/12_Verträge/02_Subplaner/_0XX_Fachbereich_Subplaner/04_Rechnungen",
    "18-GP/12_Verträge/02_Subplaner/_0XX_Fachbereich_Subplaner/05_Nachträge",
    "PHASE 0",
    "PHASE 1",
    "PHASE 1/00_SV Bauherr",
    "PHASE 1/01_Planungsgrundlagen",
    "PHASE 1/02_Checkliste, Behörde",
    "PHASE 1/02_Checkliste, Behörde/Abstimmung Behörde",
    "PHASE 1/02_Checkliste, Behörde/Checkliste",
    "PHASE 1/02_Checkliste, Behörde/Kampfmittelfreiheit",
    "PHASE 1/03_Lageplan",
    "PHASE 1/04_Einschätzung Fachplaner",
    "PHASE 1/04_Einschätzung Fachplaner/Baugrund",
    "PHASE 1/04_Einschätzung Fachplaner/Brandschutz",
    "PHASE 1/04_Einschätzung Fachplaner/Schallschutz",
    "PHASE 1/04_Einschätzung Fachplaner/Statik",
    "PHASE 1/05_Kostenermittlung",
    "PHASE 1/06_Evaluierung",
    "PHASE 1/07_Freigabe Bauherr",
    "PHASE 2",
    "PHASE 2/00_SV Bauherr",
    "PHASE 2/01_Gutachten, Netzauskunft",
    "PHASE 2/01_Gutachten, Netzauskunft/Archäologische Prüfung",
    "PHASE 2/01_Gutachten, Netzauskunft/Artenschutz",
    "PHASE 2/01_Gutachten, Netzauskunft/Baugrunduntersuchung",
    "PHASE 2/01_Gutachten, Netzauskunft/Kampfmittelfreiheit",
    "PHASE 2/01_Gutachten, Netzauskunft/Leitungsauskünfte",
    "PHASE 2/01_Gutachten, Netzauskunft/Schallschutz",
    "PHASE 2/02_Vermesser, Drohnenflug",
    "PHASE 2/02_Vermesser, Drohnenflug/00_Betretungserlaubnis",
    "PHASE 2/03_Behördenthemen",
    "PHASE 2/03_Behördenthemen/Katasterauszüge",
    "PHASE 2/04_Lageplan VAA",
    "PHASE 2/05_Lageplan TA",
    "PHASE 2/06_Visualisierung",
    "PHASE 2/07_Kostenberechnung",
    "PHASE 2/08_Architekten Dossier",
    "PHASE 2/09_Freigabe Bauherr",
    "PHASE 3",
    "PHASE 3/00_SV Bauherr",
    "PHASE 3/01_Gutachten, Statik, Pylon, Vermessung",
    "PHASE 3/01_Gutachten, Statik, Pylon, Vermessung/Brandschutzkonzept",
    "PHASE 3/01_Gutachten, Statik, Pylon, Vermessung/Pylon",
    "PHASE 3/01_Gutachten, Statik, Pylon, Vermessung/Schalltechnisches Gutachten",
    "PHASE 3/01_Gutachten, Statik, Pylon, Vermessung/Statik, Schal- & Bewerhrungsplanung Bodenplatte",
    "PHASE 3/01_Gutachten, Statik, Pylon, Vermessung/Wärmeschutznachweis GEG",
    "PHASE 3/02_Behörden",
    "PHASE 3/02_Behörden/01_Bauantrag",
    "PHASE 3/02_Behörden/01_Bauantrag/JJMMTT_Bauantrag",
    "PHASE 3/02_Behörden/01_Bauantrag/JJMMTT_Genehmigung",
    "PHASE 3/02_Behörden/01_Bauantrag/JJMMTT_Nachforderung",
    "PHASE 3/02_Behörden/01_Bauantrag/JJMMTT_Nachforderung/JJMMTT_Ausgang",
    "PHASE 3/02_Behörden/01_Bauantrag/JJMMTT_Nachforderung/JJMMTT_Eingang",
    "PHASE 3/02_Behörden/02_Werbeantrag",
    "PHASE 3/02_Behörden/02_Werbeantrag/JJMMTT_Genehmigung",
    "PHASE 3/02_Behörden/02_Werbeantrag/JJMMTT_Nachforderung",
    "PHASE 3/02_Behörden/02_Werbeantrag/JJMMTT_Nachforderung/JJMMTT_Ausgang",
    "PHASE 3/02_Behörden/02_Werbeantrag/JJMMTT_Nachforderung/JJMMTT_Eingang",
    "PHASE 3/02_Behörden/02_Werbeantrag/JJMMTT_Werbeantrag",
    "PHASE 3/02_Behörden/03_Entwässerungsantrag",
    "PHASE 3/02_Behörden/03_Entwässerungsantrag/JJMMTT_Entwässerungsantrag",
    "PHASE 3/02_Behörden/03_Entwässerungsantrag/JJMMTT_Genehmigung",
    "PHASE 3/02_Behörden/03_Entwässerungsantrag/JJMMTT_Nachforderung",
    "PHASE 3/02_Behörden/03_Entwässerungsantrag/JJMMTT_Nachforderung/JJMMTT_Ausgang",
    "PHASE 3/02_Behörden/03_Entwässerungsantrag/JJMMTT_Nachforderung/JJMMTT_Eingang",
    "PHASE 3/03_Ausführungsplanung",
    "PHASE 3/03_Ausführungsplanung/ARC",
    "PHASE 3/03_Ausführungsplanung/Lieferanten",
    "PHASE 3/03_Ausführungsplanung/Lieferanten/StaffSafe",
    "PHASE 3/03_Ausführungsplanung/TA",
    "PHASE 3/03_Ausführungsplanung/VAA",
    "PHASE 3/04_Ausschreibung",
    "PHASE 3/04_Ausschreibung/01_Ausschreibung",
    "PHASE 3/04_Ausschreibung/02_Submission",
    "PHASE 3/04_Ausschreibung/03_Angebotsauswertung",
    "PHASE 3/04_Ausschreibung/04_Vergabevorschlag",
    "PHASE 4 & 5",
    "PHASE 4 & 5/00_SV Bauherr",
    "PHASE 4 & 5/01_Werkplanung GU",
    "PHASE 4 & 5/02_Werkplanung Freigabe",
    "PHASE 4 & 5/03_Terminplan GU",
    "PHASE 4 & 5/04_Baustellenbegehungen",
    "PHASE 4 & 5/05_Schriftverkehr GU",
    "PHASE 4 & 5/06_Rechnungen GU",
    "PHASE 4 & 5/07_Abnahme",
    "PHASE 4 & 5/08_Dokumentation, Revisionsunterlagen",
    "PHASE 4 & 5/09_Gewährleistung",
]

#: Dateien, die im Musterordner liegen und mitkopiert werden, wenn er
#: erreichbar ist. Über die Liste allein lassen sie sich nicht anlegen — die
#: beiden PDF sind echte Vorlagen mit Inhalt, die drei ``Leistungsabrufe.txt``
#: sind leere Merkdateien. Die Liste dient dem Test und der Meldung an den
#: Anwender ("ohne Musterordner fehlen 2 Vorlagen").
MUSTERDATEIEN: list[str] = [
    "18-GP/12_Verträge/01_Generalplaner/02_Vertrag/Leistungsabrufe.txt",
    "18-GP/12_Verträge/02_Subplaner/010_OPG_ARC_RKA/02_Vertrag/Leistungsabrufe.txt",
    "18-GP/12_Verträge/02_Subplaner/093_Vermesser_Name Firma/02_Vertrag/Leistungsabrufe.txt",
    "PHASE 3/03_Ausführungsplanung/Lieferanten/StaffSafe/StaffSafe Auftragsbestätigung Formular - Rev 05 - 20-01-2026 - ab 01-04-2026.pdf",
    "PHASE 3/03_Ausführungsplanung/Lieferanten/StaffSafe/Staffe - Angebot Muster.pdf",
]
