# Projektbericht (Monatsbericht)

Erzeugt den monatlichen Projektbericht als `.docx` — und, wo Word erreichbar
ist, zusätzlich als PDF. Vorbild ist `BoB- Projektbericht Nr.3 20260731`.

## Die Dateien

| Datei | Aufgabe |
| --- | --- |
| `app/services/projektbericht_gliederung.py` | Kapitelgerüst und Nummerierung. Reine Funktionen, keine Word-Abhängigkeit. |
| `app/services/projektbericht_generation.py` | Baut das Word-Dokument: Kopf, Fuß, Verzeichnis, Kapitel, Tabellen, Fotos. |
| `app/services/word_pdf.py` | Wandelt ein fertiges `.docx` über Word nach PDF. |
| `app/routers/projektberichte.py` | Endpunkte: anlegen, ändern, Fotos, Vorschau, erzeugen. |
| `frontend/src/components/projektberichte/` | Liste und Formular. |

## Neues Standardkapitel ergänzen

Einen Eintrag in `GLIEDERUNG` (in `projektbericht_gliederung.py`) hinzufügen —
mehr ist nicht nötig. Formular, Verzeichnis, Nummerierung und Dokument lesen
alle dieselbe Liste.

Ein Unterkapitel, hier unter „Ausführung“:

```python
Hauptkapitel(
    "ausfuehrung", "Ausführung",
    unterkapitel=(
        ...
        Unterkapitel("aus_maengel", "Mängel"),
        Unterkapitel("aus_abnahmen", "Abnahmen"),      # ← neu
    ),
),
```

Ein Hauptkapitel ohne Unterpunkte:

```python
Hauptkapitel("nachtraege", "Nachträge"),
```

Nach dem Neustart des Backends steht das Feld im Formular, an der Stelle, an
der es in `GLIEDERUNG` steht.

### Was der `schluessel` bedeutet

Der `schluessel` ist der bleibende Name. Unter ihm liegt der Text in der
Datenbank (`projektberichte.kapitel`, JSON). Titel und Reihenfolge dürfen sich
jederzeit ändern; **den Schlüssel eines bestehenden Kapitels nicht umbenennen**
— sonst finden alte Berichte ihren Text nicht mehr. Ein Kapitel entfernen ist
unkritisch: Der Text bleibt in der Datenbank stehen und wird nur nicht mehr
gedruckt.

### Andere Kapitelarten

`art=` bestimmt, was das Kapitel aufnimmt und wie das Formular es anzeigt:

| `art` | Inhalt | Feld im Formular |
| --- | --- | --- |
| `ART_TEXT` (Vorgabe) | Fließtext | mehrzeiliges Textfeld |
| `ART_BAUBEGEHUNGEN` | Datum, Teilnehmer, Firma | Zeilenliste |
| `ART_BESPRECHUNGEN` | Bezeichnung, Rhythmus, Uhrzeit | Zeilenliste |
| `ART_SOLLIST` | Bezeichnung, SOLL, IST, Verzug | Tabelle |
| `ART_FOTOS` | Fotos mit Bildunterschrift | Upload mit Sortierung |

Die vier Listenarten liegen in eigenen Spalten (nicht im `kapitel`-JSON), weil
sie strukturiert sind. Eine **neue** Art zu erfinden heißt deshalb: Spalte im
Modell, Feld im Schema, Zweig in `_inhalt` (Erzeuger) und ein Fall in
`KapitelFeld` (Formular). Für gewöhnliche Kapitel reicht `ART_TEXT`.

### `immer_zeigen`

Setzt aus, dass leere Kapitel entfallen. Nur für 1.1–1.4 gedacht: Diese vier
Punkte stehen im Original auch dann im Bericht, wenn nichts darunter steht.
Bei allen anderen Kapiteln bitte weglassen — sonst wächst der Bericht wieder um
leere Überschriften, was der ganze Anlass dieser Umsetzung war.

## Die Nummerierungsregel

`nummeriere(inhalte)` entscheidet einmal, welche Kapitel erscheinen; Text
**und** Inhaltsverzeichnis lesen anschließend dieselbe Liste.

1. Ein Unterkapitel erscheint, wenn es Inhalt hat — oder `immer_zeigen` trägt.
2. Ein Hauptkapitel erscheint, wenn es eigenen Inhalt hat oder mindestens ein
   Unterkapitel erscheint.
3. Nummeriert wird **nach** dem Weglassen, fortlaufend ab 1.

Genau daran scheitert die Word-Vorlage: Im Referenzbericht sagt das Verzeichnis
„2.2 Fortschritt“, der Text „2.2 Verzögerungen“; am Ende „7 Fotos / 8 Anlagen“
gegen „6 Fotos / 7 Anlagen“. Wer von Hand löscht, nummeriert an einer Stelle
nach und an der anderen nicht.

Kapitel 1 („Zusammenfassende Bewertung“) trägt keine eigene Überschrift, zählt
aber als Nummer 1 mit und steht nicht im Verzeichnis — es ist der Inhalt der
ersten Seite.

## Rote Zeilen

Eine Zeile, die mit `!` beginnt, wird im Dokument rot gesetzt (im Original
„Voraussichtlich im Oktober 2026“). Das Ausrufezeichen selbst wird nicht
gedruckt. Konstante `ROT_MARKE` in `projektbericht_generation.py`.

## PDF

Die PDF entsteht über eine Word-Instanz (`word_pdf.py`, per PowerShell — im
portablen Laufzeit-Python gibt es kein `pywin32`). Ohne Word antwortet der
Endpunkt mit 503 und einer klaren Meldung; das `.docx` geht immer. Die
Oberfläche blendet den PDF-Knopf aus, wenn die Vorschau `pdf_moeglich: false`
meldet.

## Tests

Die Testdateien liegen in `backend/tests/` und brauchen kein installiertes
Python — das portable aus dem Paket genügt:

```bash
desktop/HPP-Baumanagement-App/laufzeit/python/python.exe backend/tests/test_projektbericht.py
```

Geprüft werden (a) die Nummerierung samt entfallender Kapitel, (b) Kopf, Fuß,
Dateiname und Seitenzahlfelder im erzeugten Dokument, (c) der Abgleich mit dem
Referenzbericht und (d) die Endpunkte. Ein neues Kapitel in `GLIEDERUNG` bricht
keinen dieser Tests — sie prüfen die Regel, nicht die Liste.

Jeder Test legt seine Datenbank im Temp-Ordner an; `storage/` und der
Datenordner des Pakets bleiben unberührt. Daneben liegen die Suiten der übrigen
Bereiche (`test_api`, `test_baufotos`, `test_fotomail`, `test_maengelanzeige`,
`test_migration`), die sich genauso aufrufen lassen.
