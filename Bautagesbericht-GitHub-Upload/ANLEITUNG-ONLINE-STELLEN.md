# Bautagesbericht online stellen — Schritt für Schritt (nur Browser)

Diese Anleitung bringt die App ins Internet, **ohne dass dein PC laufen muss**
und **ohne dass du irgendetwas installierst** — alles passiert im Browser.

Du brauchst drei kostenlose Konten (keine Kreditkarte). Zwei davon meldest du
bequem „mit GitHub" an, damit du dir nur ein Passwort merken musst:

1. **GitHub** — hier liegt der Programmcode.
2. **Neon** — die Datenbank (Projekte, Empfänger, Berichte).
3. **Render** — betreibt die App und liefert den Link für die Kollegen.

Plane rund **30 Minuten** ein (davon ~10 Minuten reine Wartezeit beim ersten
Aufbau). Du kannst jederzeit pausieren.

> **Zwei Websites, ein Programm, eine Datenbank.** Seit September 2026 gibt es
> die App online in zwei getrennten Ausgaben:
>
> | Adresse | Wofür | Was zu sehen ist |
> |---|---|---|
> | `bautagesbericht.onrender.com` | **Baustelle** | Dashboard, Baufotos hochladen, Fotosätze, Stammdaten · Projekte |
> | `hpp-baumanagement-buero.onrender.com` | **Büro** | zusätzlich Mängelberichte, Baubesprechungen, Bautagesberichte, Monatsberichte und Schreiben |
>
> Getrennt sind **Adresse und Funktionsumfang** — die **Datenbank ist
> dieselbe**. Was auf der Baustelle hochgeladen wird, steht sofort im Büro zur
> Verfügung, und Projekte werden nur an einer Stelle gepflegt. Beide Dienste
> stehen in derselben `render.yaml` und werden aus derselben `Dockerfile`
> gebaut; der einzige Unterschied ist die Umgebungsvariable `APP_UMFANG`
> (`fotos` bzw. `voll`).
>
> Das **Windows-Paket** für den Bürorechner bleibt davon völlig unberührt und
> kann weiterhin alles — es ist keine der beiden Websites und braucht kein
> Internet.

> **Was ist mit meinem bisherigen PC-Betrieb?** Der bleibt unangetastet: Das
> Skript `Start-Bautagesbericht.ps1` funktioniert weiter als Notlösung. Sobald
> das Online-Deployment steht, brauchst du es aber nicht mehr.

---

## Teil A — Code zu GitHub hochladen

### A1. GitHub-Konto anlegen
1. Öffne **https://github.com/signup**
2. E-Mail eingeben, Passwort wählen, Benutzername wählen, E-Mail bestätigen.
   Mehr ist nicht nötig (der kostenlose Tarif reicht vollständig).

### A2. Neues Repository anlegen
1. Oben rechts auf das **+** → **New repository**.
2. **Repository name:** z. B. `bautagesbericht`
3. **Private** auswählen (nur du siehst den Code).
4. Unten auf **Create repository**.

### A3. Dateien hochladen (Drag & Drop)
Ich habe dir einen **sauberen Upload-Ordner** vorbereitet, der genau die
richtigen Dateien enthält (ohne die riesigen Zwischenordner, die den Upload
sonst blockieren würden):

```
C:\Users\ben.gagelmann\Desktop\Bautagesbericht-GitHub-Upload
```

So lädst du ihn hoch:
1. Auf der frischen Repository-Seite den Link **„uploading an existing file"**
   anklicken (oder Knopf **Add file → Upload files**).
2. Den Ordner oben öffnen, **alles darin markieren** (Strg+A) und die
   Markierung mit der Maus in das Browser-Fenster **ziehen und loslassen**.
   GitHub übernimmt die Unterordner (`backend`, `frontend`) automatisch mit.
3. Warten, bis alle Dateien als hochgeladen angezeigt werden.
4. Unten grün **Commit changes** klicken.

> **Wenn GitHub meckert, es seien zu viele Dateien:** in zwei Runden hochladen —
> erst `backend` hineinziehen und committen, dann `frontend` und die restlichen
> Dateien hineinziehen und nochmal committen. Reihenfolge egal.

**Kontrolle:** Nach dem Upload sollten im Repository u. a. sichtbar sein:
`Dockerfile`, `start.sh`, `render.yaml` sowie die Ordner `backend/` und
`frontend/`. Die Datei-Checkliste steht ganz unten in dieser Anleitung.

---

## Teil B — Datenbank bei Neon anlegen

1. Öffne **https://neon.tech** → **Sign up** → **Continue with GitHub** →
   Zugriff bestätigen.
2. Neues Projekt anlegen: Region z. B. **Europe (Frankfurt)**, Name egal →
   **Create**.
3. Auf dem Dashboard erscheint eine **Connection string** (Verbindungs-URL).
   Auf **Copy** / kopieren.
4. **Wichtig — ein Wort ändern.** Die App braucht am Anfang der URL das Wort
   `postgresql+psycopg` statt nur `postgresql`. Füge also `+psycopg` ein:

   | | |
   |---|---|
   | Neon liefert | `postgresql://…` |
   | Du brauchst  | `postgresql+psycopg://…` |

   Der Rest der URL bleibt **exakt** gleich. Beispiel:
   `postgresql+psycopg://user:pw@ep-cool-name.eu-central-1.aws.neon.tech/neondb?sslmode=require`

5. Diese angepasste URL kurz zwischenspeichern (z. B. in einer leeren
   Notiz) — du fügst sie gleich bei Render ein.

---

## Teil C — App bei Render starten

1. Öffne **https://render.com** → **Get Started** → **GitHub** → Zugriff auf
   dein `bautagesbericht`-Repository erlauben.
2. Im Render-Dashboard: **New +** → **Blueprint**.
3. Dein Repository **`bautagesbericht`** auswählen → **Connect**.
   Render liest automatisch die Datei `render.yaml` und zeigt einen Dienst
   namens **`bautagesbericht`** an.
4. Render fragt jetzt nach den Werten, die nicht im Code stehen dürfen
   (Datenbank, E-Mail-Zugang). Trage sie ein — **was du nicht hast, lässt du
   einfach leer**:

   | Feld (Key) | Was hineingehört |
   |---|---|
   | `BTB_DATABASE_URL` | Die angepasste Neon-URL aus Teil B (mit `+psycopg`). **Pflicht.** |
   | `BTB_SEITEN_PASSWORT` | **Dringend empfohlen** — das gemeinsame Passwort, mit dem sich die Kollegen an der Weboberfläche anmelden. Ohne dieses Feld kann jeder mit dem Link Baufotos hochladen und alle Daten sehen. Wird nur bei Render gesetzt, nie lokal. |
   | `BTB_ABHOL_TOKEN` | **Pflicht, sobald oben ein Passwort steht.** Frei wählbares Losungswort für die Foto-Abholung der Bürorechner. Derselbe Wert muss auf jedem Abhol-PC in `einstellungen.txt` beim Feld `token =` stehen. Fehlt er, holt kein Bürorechner mehr Fotos ab (401). |
   | `BTB_SMTP_HOST` | Mailserver, z. B. `smtp.office365.com`. Nur nötig für „Baufotos direkt senden" — ohne diesen Wert bietet die App weiterhin den Outlook-Entwurf an. |
   | `BTB_SMTP_USER` | Das Absender-Postfach, z. B. `bautagesbericht@hpp.com`. |
   | `BTB_SMTP_PASSWORT` | Das **App-Passwort** dieses Postfachs (nicht das normale Login-Passwort). `BTB_SMTP_PASSWORD` gilt genauso. |
   | `BTB_SMTP_ABSENDER` | Dieselbe Absenderadresse wie oben. `BTB_SMTP_FROM` gilt genauso. |
   | `BTB_ANTHROPIC_API_KEY` | **Optional.** Nur nötig, um eingescannte Berichte automatisch auszulesen. Ohne Key leer lassen. |

   `BTB_SMTP_PORT` ist bereits mit `587` vorbelegt — nichts tun. `BACKEND_URL`
   setzt sich automatisch — nichts eintragen.
5. **Apply** / **Create** klicken. Jetzt baut Render die App. Der **erste
   Aufbau dauert ca. 5–10 Minuten** (danach viel schneller). Du kannst der
   Ausgabe beim „Live"-Werden zusehen.
6. Wenn der Dienst **„Live"** (grün) ist, steht oben die Adresse, etwa:
   **`https://bautagesbericht.onrender.com`** — **das ist der Link für die
   Kollegen.**

**Kurztest, dass das Innenleben läuft:** hänge `/api/health` an die Adresse an,
also `https://bautagesbericht.onrender.com/api/health`. Es sollte
`{"status":"ok"}` erscheinen.

---

## Teil C2 — Die zweite Website für das Büro

Die `render.yaml` beschreibt **zwei** Dienste. Beim ersten Blueprint-Lauf legt
Render beide auf einmal an; steht der Baustellen-Dienst schon, erscheint der
zweite beim nächsten Abgleich (Dashboard → **Blueprints** → dein Blueprint →
**Sync**).

1. Render zeigt den neuen Dienst **`hpp-baumanagement-buero`** an und fragt
   nach denselben Geheimwerten wie beim ersten Mal.
2. **Trage dieselben Werte ein wie beim Dienst `bautagesbericht`** — vor allem:

   | Feld | Wert |
   |---|---|
   | `BTB_DATABASE_URL` | **Exakt dieselbe** Neon-URL. Steht hier eine andere, sind es zwei getrennte Datenbestände und die Baustellenfotos fehlen im Büro. |
   | `BTB_SEITEN_PASSWORT` | Dasselbe Passwort wie bei der Baustellen-Seite. |
   | `BTB_ABHOL_TOKEN` | Dasselbe Losungswort. |
   | `BTB_ANTHROPIC_API_KEY` | Hier besonders wichtig — siehe Teil G. |
   | `BTB_SMTP_*` | Nur nötig, wenn die App selbst Mails verschicken soll. |

   `APP_UMFANG` ist bereits auf `voll` vorbelegt und darf **nicht** geändert
   werden — daran hängt sowohl die vollständige Oberfläche als auch der
   PDF-Export.
3. Der erste Aufbau dieses Dienstes dauert **länger als beim ersten** (rund
   10–15 Minuten): Er installiert zusätzlich LibreOffice für die PDF-Ausgabe.
4. Kurztest, sobald der Dienst grün ist:

   ```
   https://hpp-baumanagement-buero.onrender.com/api/health
   https://hpp-baumanagement-buero.onrender.com/api/health/dokumente
   ```

   Der erste muss `{"status":"ok"}` liefern. Der zweite sagt in Klartext, was
   dieser Dienst kann — dort sollte stehen:

   ```json
   { "umfang": "voll", "pdf_moeglich": true, "pdf_weg": "libreoffice",
     "scan_erkennung": true }
   ```

   Steht dort `"pdf_weg": "keins"`, fehlt LibreOffice im Image; steht
   `"scan_erkennung": false`, fehlt der Anthropic-Schlüssel (Teil G).
   Beide Auskünfte sind absichtlich **ohne Anmeldung** abrufbar, damit man
   beim Einrichten nicht im Dunkeln tappt — sie verraten nichts über Projekte
   oder Daten.

> **Warum die Werte doppelt eingetragen werden müssen.** Render kann Felder
> mit `sync: false` (also die Geheimwerte) nicht von einem Dienst zum anderen
> weiterreichen. Sie in eine gemeinsame Gruppe zu verschieben wäre bequemer,
> würde sie aber beim nächsten Blueprint-Abgleich dem bereits laufenden ersten
> Dienst wegnehmen. Einmal abtippen ist der sichere Weg.

---

## Teil D — Ausprobieren

1. Öffne die Render-Adresse im Browser.
2. Lege unter **Stammdaten · Projekte** ein **Projekt** an (mit Adresse). Trag
   dort auch den **Fotoordner** im Netzlaufwerk ein — dorthin legt der
   Bürorechner die Bilder später ab.
3. Wähle das Projekt oben in der Kopfzeile aus.
4. Klick auf dem **Dashboard** in das große Feld **„Fotos hochladen"** (oder
   links im Menü, am Handy über die drei Striche oben links).
5. Kategorie und Bautag eingeben, Fotos aufnehmen oder aus der Galerie wählen,
   **hochladen**. Der Name des Archivs steht schon vorher da.
6. Unter **Fotosätze** ist der Satz danach zu sehen — mit Vorschaubildern,
   ZIP-Download und der Möglichkeit, ihn per E-Mail weiterzugeben.
7. Auf dem Dashboard zeigt die Kachel **„Abholung ins Büro"**, wie viele Sätze
   noch auf einen Bürorechner warten.

Beim allerersten Aufruf nach einer Pause kann es 30–60 Sekunden dauern (siehe
Teil F).

---

## Teil E — Link an die Kollegen geben

Die Render-Adresse bleibt **dauerhaft gleich**. Weitergeben kannst du sie so:
- Als **Lesezeichen** im Browser speichern.
- Am Handy über **„Zum Startbildschirm hinzufügen"** ablegen — dann sieht es
  aus und startet wie eine App, ganz ohne Installation.

---

## Teil F — Ehrlich: Grenzen der kostenlosen Stufe

- **Aufwachzeit.** Wird die App 15 Minuten nicht benutzt, „schläft" sie. Der
  nächste Aufruf dauert dann **30–60 Sekunden**, danach läuft alles normal.
  Für ein Werkzeug, das ein paar Mal am Tag benutzt wird, gut vertretbar.
- **Dateispeicher — gelöst, aber mit Verfallsdatum.** Das Dateisystem des
  Containers ist flüchtig: Es startet bei jedem Deploy und nach jedem
  Einschlafen leer. Deshalb steht bei **beiden** Diensten
  `BTB_FOTOSPEICHER=db` — hochgeladene Fotos liegen in der Neon-Datenbank und
  überstehen einen Neustart. Nachprüfen lässt sich das ohne Anmeldung unter
  `…/api/health/speicher`; dort muss `"dauerhaft": true` stehen.

  Die Datenbank ist dabei ein **Durchgang, kein Archiv**:

  | | |
  |---|---|
  | Noch nicht abgeholt | bleibt unter allen Umständen liegen |
  | Abgeholt | Bilddaten werden nach **2 Tagen** freigegeben (`BTB_FOTOS_AUFBEWAHREN_TAGE`) |
  | Über **300 MB** gesamt | zusätzlich werden die ältesten abgeholten Sätze geleert (`BTB_FOTOS_MAX_MB`) |

  Das dauerhafte Archiv ist und bleibt der **Projektordner im Netzlaufwerk** —
  dorthin holt der Bürorechner die Sätze ab. Ist ein Bild freigegeben, bleibt
  der Datensatz mit Name, Größe und Zielordner erhalten, und die App sagt
  ausdrücklich „Bilddatei nicht mehr auf dem Server". Es gibt also **keinen
  stillen Verlust** — aber wer einen Satz nie abholt und nach Wochen die
  Vorschaubilder sucht, sollte wissen, warum sie fehlen.

  Andere Dateien (fertige Word-Dokumente, hochgeladene Pläne) liegen weiterhin
  im flüchtigen Dateisystem. Sie lassen sich jederzeit neu erzeugen bzw. neu
  hochladen — trotzdem gilt: heruntergeladen und im Projektordner abgelegt ist
  sicher, auf dem Server liegengelassen ist es nicht.

- **Kosten.** GitHub, Neon und Render bleiben in dieser Nutzung dauerhaft
  kostenlos. Keine Kreditkarte, kein Ablaufdatum.

---

## Teil G — Zwei Dinge, die online anders sind als auf dem Bürorechner

Beides betrifft nur die **Büro-Website**; die Baustellen-Seite kennt diese
Funktionen gar nicht.

### 1. Texterkennung eingescannter Bautagesberichte

Auf dem Bürorechner liest die App gedruckte Formblätter mit der **Windows-
eigenen Texterkennung** — kostenlos, offline, ohne Schlüssel. Die gibt es im
Linux-Container **nicht**. Online führt deshalb nur ein Weg zum Ziel: der
**Anthropic-Schlüssel** (`BTB_ANTHROPIC_API_KEY`).

| | Bürorechner (Windows-Paket) | Büro-Website |
|---|---|---|
| PDF **mit** Textebene | geht immer, ohne Schlüssel | geht immer, ohne Schlüssel |
| Gedruckter **Scan** | Windows-Texterkennung | **nur mit Schlüssel** |
| **Handschrift** | nur mit Schlüssel | **nur mit Schlüssel** |

Ohne Schlüssel kann online also **gar kein** Scan gelesen werden. Das geht
nicht still verloren: Die Oberfläche schreibt es hin
(`erkennung_beschreibung()` in `backend/app/services/pdf_extraction.py`), und
`…/api/health/dokumente` meldet `"scan_erkennung": false`. Die Angaben müssen
dann von Hand eingetippt werden.

**Kosten:** Der Schlüssel wird nur beim Einlesen eines Scans benutzt, nicht im
laufenden Betrieb. Er ist bei Render unter *Environment* einzutragen und taucht
nirgends im Code auf.

### 2. „Als PDF"

Das **Word-Dokument ist und bleibt die verbindliche Ausgabe** — das PDF ist die
Zugabe. Erzeugen kann es nur ein Textprogramm mit Umbruch-Algorithmus:

| | Womit | Stand |
|---|---|---|
| Windows-Paket | Microsoft Word über PowerShell | unverändert wie bisher |
| Büro-Website | **LibreOffice Writer, kopflos** | seit September 2026 |
| Baustellen-Seite | — | kennt keine PDF-Funktion |

LibreOffice steckt nur im Image der Büro-Website (rund 400 MB, deshalb dauert
deren erster Aufbau länger). Seitenzahlen und Verzeichnis stimmen, weil die
Dokumente auf „Felder beim Öffnen aktualisieren" gestellt sind und LibreOffice
das beim Laden auswertet.

**Bekannte Restunterschiede:** LibreOffice ist nicht Word. Bei sehr eng
gesetzten Vorlagen können Umbrüche um eine Zeile abweichen. Wo das Layout auf
den Millimeter zählt, bleibt der verlässliche Weg: Word-Dokument herunterladen
und auf dem Bürorechner als PDF speichern. Der erste PDF-Aufruf nach dem
Aufwachen des Dienstes dauert einige Sekunden länger, weil LibreOffice sein
Benutzerprofil anlegt.

---

## Hinweis zum E-Mail-Versand über Microsoft 365

Microsoft sperrt den SMTP-Versand (`smtp.office365.com`) für Postfächer
**standardmäßig ab**. Damit der automatische Versand funktioniert, muss eure
**IT einmalig „Authenticated SMTP" (SMTP AUTH)** für das Absender-Postfach
freischalten und ein **App-Passwort** erzeugen. Ist das nicht möglich, lass die
`BTB_SMTP_*`-Felder bei Render einfach leer: Die App erzeugt den Bericht dann
trotzdem, nur ohne automatischen Mailversand — herunterladen geht immer.

Für **Baufotos per E-Mail** gilt dasselbe, aber es gibt einen Weg ohne SMTP:
Die App baut die fertige Mail mit dem ZIP im Anhang als `.eml`-Datei, und
Outlook öffnet sie als Entwurf, in dem nur noch *Senden* fehlt. Der Weg braucht
keine Freischaltung und funktioniert auch auf dem kostenlosen Render-Plan, auf
dem ausgehendes SMTP ohnehin gesperrt ist.

---

## Anhang — Datei-Checkliste für den Upload

Der vorbereitete Ordner `Bautagesbericht-GitHub-Upload` enthält **genau** diese
Dinge. Falls du doch von Hand aus dem Projektordner hochlädst, achte darauf:

**Hochladen (nötig):**
- Im Hauptverzeichnis: `Dockerfile`, `start.sh`, `render.yaml`,
  `.dockerignore`, `.gitignore`, `.gitattributes`
- Ordner `backend/` mit: `app/` (der ganze Ordner), `templates/` (die
  Word-Vorlage), `pyproject.toml`, `uv.lock`
- Ordner `frontend/` mit: `src/` (der ganze Ordner), `public/`,
  `package.json`, `package-lock.json`, `next.config.ts`, `tsconfig.json`,
  `postcss.config.mjs`

**NICHT hochladen (unnötig/zu groß — verlangsamt oder blockiert den Upload):**
- `node_modules/`  (Frontend-Bibliotheken — Render lädt sie selbst)
- `.next/`  (Frontend-Build — entsteht bei Render neu)
- `.venv/` bzw. `backend/.venv/`  (Python-Umgebung — Render baut sie neu)
- `__pycache__/`  (Python-Zwischendateien)
- `backend/storage/`  (lokale Datenbank & Uploads von deinem PC)
- alle `.env`- und `.env.local`-Dateien  (Zugangsdaten — die trägst du direkt
  bei Render ein)
- `tools/` (der Cloudflare-Tunnel, nur für den lokalen Betrieb)
