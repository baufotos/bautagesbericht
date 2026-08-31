# Baufotos vom Handy bis ins Projektverzeichnis

Was am Ende passiert, in einem Satz:

> Auf der Baustelle Fotos hochladen — und sie liegen kurz darauf fertig
> benannt und verkleinert in `L:\Bauleitung-Hamburg\<Projekt>\01 FOTOS\`.

Dieses Dokument beschreibt, was dafür **einmalig** einzurichten ist. Es kostet
nichts und braucht kein zusätzliches Konto.

---

## Der Weg im Überblick

```
Handy auf der Baustelle
        │  bautagesbericht.onrender.com
        │  Projekt · Tätigkeit · Datum · Fotos
        ▼
Server (Render)
        │  benennt um: 260819_Baustellenbegehung_1.jpg
        │  verkleinert: längste Kante 1600 px, Qualität 70
        │  legt in der Datenbank ab       ← übersteht jeden Neustart
        ▼
Abholskript auf einem Bürorechner        ← alle 15 Minuten
        │
        ▼
L:\Bauleitung-Hamburg\K30159 Kita Nord\01 FOTOS\260819_Baustellenbegehung\
```

**Warum das Skript im Büro und nicht auf dem Server?** `L:` ist ein Laufwerk
im Büronetz. Ein Server im Internet kommt dort nicht hinein — daran lässt sich
nichts programmieren. Also holt das Büro ab.

Benennung und Bildgröße sind dieselben wie im bisherigen
Baustellenfotos-Werkzeug. Es ändert sich nur, woher die Fotos kommen.

---

## Wo die Fotos zwischenzeitlich liegen

Sie liegen in **derselben Datenbank**, in der ohnehin Projekte, Berichte und
Mängel stehen. Nichts einzurichten, nichts zu bezahlen, kein weiteres Konto.

Das musste so gelöst werden, weil das Dateisystem des Render-Containers
flüchtig ist: Der Dienst schläft nach 15 Minuten ohne Zugriff ein und startet
beim Aufwachen — wie bei jedem Deploy — leer. Vormittags hochgeladene Fotos
wären am Abend verschwunden, während in der Datenbank noch ihre Verweise
stehen.

Der übliche Weg dafür wäre ein Objektspeicher wie Cloudflare R2. Der verlangt
aber schon fürs kostenlose Kontingent eine Kreditkarte — deshalb hier nicht.
Nötig ist er auch nicht, denn:

> **Die Datenbank ist ein Durchgang, kein Archiv.** Ein Fotosatz liegt dort
> von der Baustelle bis zum Bürorechner — im Regelfall eine Viertelstunde.
> Zwei Tage nach der Abholung werden die Bilddaten wieder freigegeben; der
> Eintrag mit Name, Größe und Zielordner bleibt. Das Archiv ist `L:`.

Die zwei Tage Schonfrist gibt es, damit die Galerie in der App direkt nach dem
Termin noch Vorschaubilder zeigt. Wird es trotzdem einmal eng, leert der
Server zusätzlich die ältesten **bereits abgeholten** Sätze.

Was noch nicht abgeholt ist, wird unter keinen Umständen angetastet — auch
nicht, wenn der Platz knapp wird. Lieber eine volle Datenbank als ein
verlorener Fotosatz.

Nachsehen, ob das greift:

```bash
curl https://bautagesbericht.onrender.com/api/health/speicher
```

Dort muss `"dauerhaft": true` und `"art": "db"` stehen.

---

## Schritt 1 — Zielordner der Projekte pflegen

In der App: **Stammdaten → Projekte**. Auf jeder Projektkarte steht der
Fotoordner; ein Klick darauf macht ihn änderbar.

```
L:\Bauleitung-Hamburg\K30159 Kita Nord\01 FOTOS
```

Der Ordner `<JJMMTT>_<Tätigkeit>` wird darin angelegt.

**Warum am Projekt und nicht auf dem PC:** So gilt der Pfad für alle
Kollegen. Wer ihn einmal einträgt, hat ihn für das ganze Team eingetragen.

Bleibt das Feld leer, bildet das Abholskript den Pfad selbst:
`<basisordner>\<Projektname>\01 FOTOS`.

---

## Schritt 2 — Abholskript auf den Bürorechnern

Im App-Ordner liegt der Unterordner **`Foto-Abholung`**.

1. Diesen Ordner nach `C:\HPP-Baufotos` kopieren.
2. `einstellungen.txt` öffnen und `basisordner` prüfen.
3. Rechtsklick auf **`Aufgabe-Einrichten.ps1`** → *Mit PowerShell ausführen*.

Fertig. Die Abholung läuft ab jetzt alle 15 Minuten und zusätzlich bei jeder
Anmeldung.

**Das darf jeder im Team bekommen — es ist sogar erwünscht.** So kommen die
Fotos auch an, wenn ein einzelner Rechner aus ist. Der Server vergibt jeden
Fotosatz nur einmal: Ein Rechner beansprucht ihn, alle anderen bekommen für
diesen Satz eine Absage. Doppelte Ablage ist ausgeschlossen.

Vorher einmal gefahrlos ausprobieren:

```powershell
.\Baufotos-Abholen.ps1 -Testlauf
```

Zeigt nur an, welcher Satz in welchen Ordner käme — geschrieben wird nichts.

---

## Nachsehen, ob es läuft

* **In der App**, auf der Fotosatz-Karte: *„Im Projektordner abgelegt"* mit
  dem vollständigen Pfad.
* **Auf dem Rechner**: `C:\HPP-Baufotos\abholung.log` — dort steht jeder Lauf
  mit Uhrzeit, Zielordner und Anzahl der Dateien.

---

## Wenn ein Projekt woanders liegt

Nur für den Fall, dass ein Laufwerk auf **einem bestimmten Rechner** anders
eingebunden ist (M: statt L:) oder ein Projekt ausnahmsweise woanders liegt:
`Projekt-Ausnahmen.txt` im Abholordner.

```
K30159 Kita Nord = M:\Bauleitung-Hamburg\K30159 Kita Nord\01 FOTOS
```

Dieser Eintrag hat Vorrang vor dem Pfad aus der App und gilt nur auf diesem
Rechner.

---

## Häufige Meldungen im Protokoll

| Meldung | Bedeutung |
|---|---|
| `Uebernimmt gerade ein anderer Rechner` | Kein Fehler. Ein Kollege war schneller, der Satz ist versorgt. |
| `Laufwerk L:\ nicht erreichbar` | Netzlaufwerk nicht verbunden. Einmal im Explorer öffnen; der nächste Durchgang läuft wieder. |
| `Server antwortet nicht, zweiter Versuch` | Render schläft nach 15 Minuten ein und braucht bis zu einer Minute zum Aufwachen. Das Skript wartet von selbst. |
| `Fotos liegen im Projektordner, nur die Quittung fehlt` | Die Fotos sind da. Der Satz wird bewusst nicht erneut freigegeben, damit er nicht doppelt abgelegt wird — beim nächsten Lauf nachsehen. |

---

## Wenn die Fotomenge einmal wächst (nicht nötig, nur möglich)

Sollte irgendwann so viel gleichzeitig unterwegs sein, dass die Datenbank zu
klein wird, lässt sich ein S3-kompatibler Objektspeicher davorschalten —
Cloudflare R2, Backblaze B2 oder ein eigener MinIO-Server. Dafür auf Render
`BTB_FOTOSPEICHER=objekt` und die vier Werte `BTB_R2_ENDPOINT`,
`BTB_R2_BUCKET`, `BTB_R2_KEY_ID`, `BTB_R2_SECRET` setzen. Am Ablauf ändert
sich nichts, das Abholskript merkt davon nichts.

## Optional: Abholung mit Losungswort

Die Abholrouten sind offen wie der Rest der App. Wer sie schützen will,
setzt auf Render `BTB_ABHOL_TOKEN` auf ein selbst gewähltes Wort und trägt
dasselbe Wort in die `einstellungen.txt` jedes Bürorechners ein. Ohne
passendes Wort antwortet der Server dann mit 401.
