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

## Teil D — Ausprobieren

1. Öffne die Render-Adresse im Browser.
2. Lege ein **Projekt** an (mit Adresse — daraus kommen die Wetterdaten).
3. Lege einen **Empfänger** an (E-Mail-Adresse).
4. Reiche einen **Bericht** ein: Projekt und Empfänger wählen, PDF hochladen,
   absenden.
5. Nach kurzer Verarbeitung steht das **Word-Dokument zum Download** bereit —
   und geht (falls SMTP eingerichtet ist) zusätzlich **per E-Mail** an den
   Empfänger.

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
- **Kein dauerhafter Dateispeicher — das ist die wichtigste Einschränkung.**
  Alles, was in der **Neon-Datenbank** steht, bleibt erhalten: Projekte,
  Empfänger, Firmen, Mängel mit allen Fristen und Texten, Fotosätze mit ihren
  Angaben. **Dateien** liegen dagegen auf der Festplatte des Render-Containers
  und können bei einem Neustart verschwinden:

  | Betrifft | Was zu tun ist |
  |---|---|
  | Baufotos (Bilddateien) | ZIP-Datei nach dem Hochladen herunterladen und in den Projektordner legen — genau dafür ist sie da. |
  | Mängelfotos und Anhänge | Wichtige Mängellisten als Word-Dokument exportieren; darin sind die Fotos eingebettet. |
  | Fertige Word-Berichte | Aus der Übersicht herunterladen und ablegen. |
  | Hochgeladene Pläne | Original behalten; ein Plan lässt sich jederzeit neu hochladen. |

  Verschwindet eine Bilddatei, bleibt der Datensatz erhalten und die App sagt
  es (die ZIP-Datei enthält dann eine `FEHLT.txt`) — es entsteht also kein
  stiller Datenverlust. Wer die Fotos dauerhaft auf dem Server halten will,
  braucht einen bezahlten Render-Plan mit „Persistent Disk" oder einen
  Objektspeicher.
- **Kosten.** GitHub, Neon und Render bleiben in dieser Nutzung dauerhaft
  kostenlos. Keine Kreditkarte, kein Ablaufdatum.

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
