# HPP Baumanagement auf den Rechner bringen

Zwei Wege, dieselbe App. Der Unterschied ist nur, **wo die Daten liegen**.

| | Paket (empfohlen zum Ausprobieren) | Fern (empfohlen fürs Team) |
|---|---|---|
| Was man verteilt | Ordner `HPP-Baumanagement-App` (199 MB) bzw. das ZIP (68 MB) | nur `HPP-Baumanagement.exe` (41 KB) |
| Braucht Internet | nein | ja |
| Braucht Deployment | nein | ja (Render, siehe ANLEITUNG-ONLINE-STELLEN.md) |
| Datenstand | je Rechner eigener — außer man trägt eine zentrale Datenbank ein | für alle derselbe |

Die `.exe` erkennt selbst, welcher Fall vorliegt: Liegt ein Ordner `laufzeit`
daneben, startet sie die mitgelieferte App; sonst öffnet sie die Adresse aus
`app-url.txt`.

Über die Seitenleiste erreichbar sind drei Arbeitsbereiche:

| Bereich | Was man dort tut |
|---|---|
| **Baufotos** | Fotos hochladen — sie werden nach der Büroregel umbenannt (`{JJMMTT}_{Kategorie}_{Nr}.jpg`), auf 1600 px verkleinert und als `{Datum}_{Projekt}_{Kategorie}.zip` zum Ablegen bereitgestellt. Ersetzt das lokale Baustellenfotos-Tool. Versand per E-Mail mit dem ZIP im Anhang, per Teams-Meldung oder als reiner Download. |
| **Mängelberichte** | Mängel auf der Baustelle erfassen, Fristen und Nachfristen verwalten, Plan-Markierung setzen, Mängelliste als Word-Dokument exportieren. Und die **Mängelanzeige** an die Firma: Anschreiben mit Fristsetzung gem. § 4 Abs. 7 VOB/B plus Fotoanlage, im HPP-Briefbogen. |
| **Bautagesberichte** | Berichte der Firmen einreichen; Wetterdaten und Word-Erzeugung laufen im Hintergrund. |

Darüber liegt ein **Dashboard** mit dem Zustand des gewählten Projekts, darunter
die **Stammdaten** (Projekte, Firmen, Pläne, Empfänger, Wertelisten).

---

## Weg 1: Das Paket — App auf dem Rechner, ohne alles

```powershell
.\paket\erstellen.ps1 -Zip
```

Das baut `HPP-Baumanagement-App\` und `HPP-Baumanagement-App.zip` (mit
`-NurAnwendung` nur Anwendung, Oberfläche und Startprogramm — Python, Pakete
und **Daten** bleiben stehen). Der Ordner
enthält alles: portables Python, die Anwendung, die Oberfläche, das
Startprogramm. Auf dem Zielrechner ist **keine Installation** nötig — kein
Python, kein Node.js, keine Administratorrechte.

**Für die Kollegen:** ZIP auspacken, `HPP-Baumanagement.exe` doppelklicken.
Fertig. Die Kurzanleitung liegt als `Zuerst-lesen.txt` daneben.

Beim Start passiert dies: Das Programm startet den mitgelieferten Server im
Hintergrund, wartet, bis er antwortet, und öffnet das App-Fenster. Wird das
Fenster geschlossen, wird der Server wieder beendet.

> **Warum knapp 200 MB und kein halbes Gigabyte?** Die Oberfläche ist statisch
> exportiert (`NEXT_EXPORT=1`) und wird von FastAPI mit ausgeliefert. Dadurch
> läuft alles in **einem** Prozess und das Paket braucht kein Node.js. Der Rest
> ist portables Python (~100 MB) und die Bibliotheken (~95 MB) — gezippt 68 MB.

### Was beim Bauen geprüft wird

Nach dem Installieren der Bibliotheken lädt das Skript einmal wirklich
`app.main` — denselben Weg, den uvicorn beim Start nimmt
([`paket/importe_pruefen.py`](paket/importe_pruefen.py)). Schlägt das fehl,
bricht der Bau ab, und es entsteht **kein** ZIP.

Der Grund ist eine echte Panne: `pip install --target` hinterlässt bei einem
Abbruch einen Ordner, der vollständig aussieht — `fastapi` lag da, nur zwei
seiner Abhängigkeiten (`annotated_doc`, `anyio`) fehlten. Das Paket ließ sich
bauen und zippen, und erst beim Doppelklick kam `ModuleNotFoundError`. Seitdem
fällt das beim Bauen auf und nicht beim Kollegen.

Nachprüfen lässt sich das jederzeit auch von Hand:

```powershell
.\HPP-Baumanagement.exe --pruefen
```

### Daten des Pakets

Standardmäßig im Ordner `daten` neben dem Programm:

```
daten\hpp-baumanagement.db   Datenbank
daten\uploads                Fotos, Pläne, hochgeladene Berichte
daten\output                 erzeugte Word-Dokumente
daten\protokoll.txt          erste Anlaufstelle bei Störungen
```

**Diesen Ordner in die Sicherung aufnehmen** — er enthält die ganze Arbeit. Das
Verteil-ZIP enthält ihn absichtlich nicht.

### Baufotos per E-Mail

Auf jeder Fotosatz-Karte steht **Per Mail**. Der Dialog schlägt Betreff und
Text vor (Projekt, Kategorie, Anzahl, alle Dateinamen), die Empfänger kommen
aus den Stammdaten — Empfänger *und* Firmen mit Adresse — plus ein Freitextfeld
für Bauherr oder Sachverständigen.

| Weg | Voraussetzung | Was passiert |
|---|---|---|
| **Outlook-Entwurf** | keine | Die App baut die vollständige Mail samt ZIP als `.eml`. Doppelklick → das klassische Outlook öffnet sie als Entwurf, in dem nur noch *Senden* fehlt. Absender bleibt frei, damit Outlook das eigene Konto nimmt. |
| **Direkt senden** | Postausgangsserver in `einstellungen.txt` | Die Mail geht ohne Outlook los. |
| **Mailfenster + ZIP** | keine | Der Notausgang für das neue Outlook und die Browserfassung, die `.eml` nicht öffnen: `mailto:` mit Betreff und Text, ZIP daneben laden und selbst anhängen. |

Die Grenze liegt bei **15 MB pro ZIP** — Base64 macht daraus rund 20 MB Mail,
und mehr nehmen die meisten Postfächer nicht an. Darüber sagt die App das
vorher, statt eine Mail losschicken zu lassen, die beim Empfänger abprallt.

Auf der Karte steht danach, wann der Satz an wen ging. Dabei wird unterschieden:
**gemailt** heißt, die App hat verschickt; **Entwurf** heißt, Outlook hat die
fertige Mail bekommen — abgeschickt hat sie dann jemand von Hand.

### Mängelanzeige: zwei Word-Dateien, nach dem Briefbogen des Büros

*Mängelberichte → Mängelanzeige.* Firma wählen, Mängel ankreuzen, Termine
prüfen — heraus kommen **immer zwei getrennte Dateien**, so wie das Büro sie
verschickt:

| Datei | Inhalt |
|---|---|
| `{JJMMTT}_{Kürzel}.docx` | Anschreiben: Briefbogen, Adressblock, Datumszeile, Betreff, Fristsetzung gem. § 4 Abs. 7 VOB/B, Grußformel, Fußzeile mit Seitenzahl |
| `{JJMMTT}_Anlage_{Kürzel}.docx` | Fotoanlage: je Bereich eine fette Überschrift, darunter ein oder zwei Fotos nebeneinander, unter jedem Foto seine Bildunterschrift |

Zusammengeführt wird nichts. „Beide erzeugen“ lädt ein ZIP mit den zwei
Dateien; wer nur eine braucht, holt sie einzeln.

**Woher die Angaben kommen.** Bereichsüberschriften aus dem Ort am Mangel
(„Ostfassade“), Bildunterschriften aus der Bildunterschrift des Fotos oder
sonst der Kurzbezeichnung des Mangels, Anschrift und Vergabeeinheit aus den
Firmen-Stammdaten, Fristvorschlag aus der frühesten am Mangel gesetzten Frist.
Jedes Feld bleibt änderbar. Mängel **ohne Foto** kommen nicht in die Anlage —
die Vorschau nennt sie, und im ZIP liegt eine `HINWEISE.txt` dazu.

**Wie genau das Layout stimmt.** Die Maße sind an den beiden Referenz-PDFs des
Büros ausgemessen (Zeichenpositionen aus dem PDF gelesen, nicht geschätzt) und
das Ergebnis wurde gegengeprüft: aus Word nach PDF exportiert und Zeile für
Zeile mit dem Original verglichen. 27 gemessene Positionen stimmen auf ±1 pt,
das Anschreiben passt auf eine Seite, die Anlage bricht wie das Original um.

Der Briefkopf ist **eine Grafik** — im Original steht rechts kein Text.
Ändern sich Adresse oder Partnerliste, tauscht man die Datei:

```
backend/templates/marke/hpp_briefkopf.png             Anschreiben (alles)
backend/templates/marke/hpp_briefkopf_folgeseite.png  Anlage (nur Logo)
```

Die festen Textbausteine (§-4-Absatz, Konsequenztext, Abnahmehinweis) stehen
gesammelt in [`maengelanzeige_generation.py`](../backend/app/services/maengelanzeige_generation.py)
— einmal, nicht in jeder View.

### Gemeinsam arbeiten mit dem Paket

In `einstellungen.txt` eine zentrale Datenbank **und** einen gemeinsamen
Datenordner eintragen:

```
datenbank=postgresql+psycopg://…@…neon.tech/hpp?sslmode=require
datenordner=\\hpp-server\Baumanagement\Daten
```

Beides zusammen — nur die Datenbank allein würde bedeuten: gleiche Mängel und
Fristen, aber jeder sieht nur seine eigenen Fotos.

---

## Weg 2: Fern — eine 41-KB-Datei, ein gemeinsamer Datenstand

Läuft die App auf Render, genügt `HPP-Baumanagement.exe` allein. Sie liest die
Adresse aus `app-url.txt` (eine Zeile) und öffnet sie im App-Fenster. Ohne
`app-url.txt` gilt die eingebaute Standardadresse — eine einzeln kopierte Datei
funktioniert also auch.

Das ist der beste Weg fürs Team: ein Datenstand, ein Update für alle, und die
Kollegen bekommen nur eine winzige Datei.

---

## Beide Wege: gut zu wissen

**Beim ersten Start meldet Windows „Unbekannter Herausgeber".** *Weitere
Informationen* → *Trotzdem ausführen*. Grund: keine kostenpflichtige Signatur.
Der Quellcode liegt in [`quelle/HppBaumanagement.cs`](quelle/HppBaumanagement.cs)
und lässt sich mit `quelle\bauen.ps1` selbst übersetzen — das ist der
Vertrauensanker, wenn eine `.exe` von einem Kollegen kommt.

**Selbsttest bei Störungen:**

```powershell
.\HPP-Baumanagement.exe --pruefen
```

Zeigt Betriebsart, Adresse, gefundenen Browser, Port und ob der Server startet.
Im Paketmodus startet er dafür kurz einen Testserver und beendet ihn wieder.

**Weitere Aufrufe**

| Aufruf | Wirkung |
|---|---|
| `--verknuepfung` | Verknüpfung auf dem Desktop anlegen |
| `--url <adresse>` | einmalig eine andere Adresse öffnen (erzwingt den Fernmodus) |
| `--port 9000` | anderer Port im Paketmodus |

**Eigenes Browserprofil.** Das App-Fenster nutzt ein eigenes Profil unter
`%LOCALAPPDATA%\HPP-Baumanagement`. So verschwindet es nicht zwischen den
privaten Tabs, und der Offline-Speicher bleibt erhalten. Ist die App schon
offen und man startet erneut, öffnet sich ein zweites Fenster auf dieselbe
laufende App — es wird kein zweiter Server gestartet.

---

## Auf dem Handy und Tablet

Die App ist zusätzlich eine PWA (das braucht Weg 2, also die Adresse im Netz):

* **Android (Chrome/Edge):** Adresse öffnen → Menü „…" → *App installieren*.
* **iPhone/iPad (Safari):** Adresse öffnen → *Teilen* → *Zum Home-Bildschirm*.

Danach Symbol auf dem Home-Bildschirm, Start im Vollbild, untere
Navigationsleiste. **Im Funkloch** startet die App weiter und zeigt den letzten
geladenen Stand samt Fotos; neue Mängel und Uploads brauchen Empfang — die App
sagt es deutlich, statt still zu scheitern.

---

## Warum es kein Programm mit eigener Datenbank *für alle* gibt

Eine Mängelliste wird gemeinsam abgearbeitet: Einer nimmt den Mangel auf der
Baustelle auf, ein anderer setzt die Nachfrist, ein Dritter exportiert die Liste
für die Firma. Mit getrennten lokalen Datenbanken sähe niemand die Arbeit der
anderen, und beim Zusammenführen ginge zwangsläufig etwas verloren.

Deshalb gibt es beides: das **Paket** zum Ausprobieren und für den Einzelplatz
(oder mit zentraler Datenbank auch fürs Team) und die **Fernvariante** als
schlanken Weg, wenn die App ohnehin im Netz läuft.

---

## Marke und Symbole

Verbindlich ist **eine** Datei: `frontend/public/marke/hpp-wortmarke.svg` — die
HPP-Wortmarke als Vektor. Alles andere entsteht daraus:

```powershell
python .\_marke-symbole-erzeugen.py
```

Das schreibt die PWA-Symbole (`frontend/public/icons/`), das Symbol im
Fenstertitel (`frontend/src/app/favicon.ico`) und das Programmsymbol
(`hpp-app.ico`). Danach `quelle\bauen.ps1`, damit die `.exe` das neue Symbol
trägt.

Das Symbol trägt die **Logofarben**: dunkle Wortmarke auf Weiß, wie im
Briefkopf. Eine farbige Kachel wäre ein eigener Entwurf und nicht das Logo —
die Akzentfarbe der App gehört in die Oberfläche, nicht ins Firmenzeichen. Für
dunkle Untergründe entsteht zusätzlich `icons/icon-dunkel-512.png` mit
vertauschten Rollen.

Die ICO enthält sieben Größen, und **jede wird einzeln gezeichnet**: Ein 256er
Bild auf 16 px herunterzurechnen ergibt einen Fleck, weil die Striche der drei
Buchstaben unter ein Pixel fallen. Deshalb füllt die Wortmarke bei 16 px 86 %
der Breite und bei 256 px nur 60 % (`ANTEIL_JE_KANTE` im Skript). Größen bis
48 px liegen als BMP in der Datei — die Fassung, die auch ältere
Windows-Dialoge zuverlässig zeichnen —, ab 64 px als PNG, das hält die Datei
klein.

Dass das Ergebnis wirklich in der `.exe` steckt, lässt sich nachrechnen: Die
Bildblöcke der ICO müssen sich Byte für Byte in der `.exe` wiederfinden, und
`[System.Drawing.Icon]::ExtractAssociatedIcon` muss die Wortmarke liefern —
das ist derselbe Weg, den Explorer und Taskleiste nehmen.

In der Oberfläche steckt die Marke als
[`frontend/src/components/HppLogo.tsx`](../frontend/src/components/HppLogo.tsx).
Sie färbt sich über `currentColor` — weiß in der dunklen Seitenleiste, dunkel
auf hellem Grund, ohne zweite Datei.

**Herkunft:** nachgezeichnet aus dem Logo der Word-Vorlage
(`backend/templates/Bautagesbericht_HPP_leer.docx`), wo es nur als Rasterbild
mit 205 × 80 Pixeln vorliegt — mit Marching Squares auf den Grauwerten, also
subpixelgenau statt hochskaliert.

> **Wenn die echte Vektordatei vorliegt** (SVG oder EPS aus dem
> Markenhandbuch), ist der Austausch klein: `hpp-wortmarke.svg` ersetzen (ein
> `<path>` mit `fill="currentColor"`, am Tintenrahmen ausgerichtet), denselben
> Pfad in `HppLogo.tsx` eintragen, Skript laufen lassen. Dann ist die Marke
> überall in Originalqualität.
