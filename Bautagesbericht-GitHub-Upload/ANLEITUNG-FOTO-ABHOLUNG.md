# Baufotos vom Handy bis ins Projektverzeichnis

Was am Ende passiert, in einem Satz:

> Auf der Baustelle Fotos hochladen — und sie liegen kurz darauf fertig
> benannt und verkleinert in `L:\Bauleitung-Hamburg\<Projekt>\01 FOTOS\`.

Dieses Dokument beschreibt, was dafür **einmalig** einzurichten ist.

---

## Der Weg im Überblick

```
Handy auf der Baustelle
        │  bautagesbericht.onrender.com
        │  Projekt · Tätigkeit · Datum · Fotos
        ▼
Server (Render)                        ← liegt im Internet
        │  benennt um: 260819_Baustellenbegehung_1.jpg
        │  verkleinert: längste Kante 1600 px, Qualität 70
        │  legt ab in Cloudflare R2     ← überlebt jeden Neustart
        ▼
Abholskript auf einem Bürorechner      ← alle 15 Minuten
        │
        ▼
L:\Bauleitung-Hamburg\K30159 Kita Nord\01 FOTOS\260819_Baustellenbegehung\
```

**Warum das Skript im Büro und nicht auf dem Server?** `L:` ist ein Laufwerk
im Bürolan. Ein Server im Internet kommt dort nicht hinein — daran lässt sich
nichts programmieren. Also holt das Büro ab.

Benennung und Bildgröße sind dieselben wie im bisherigen
Baustellenfotos-Werkzeug. Es ändert sich nur, woher die Fotos kommen.

---

## Schritt 1 — Fotospeicher einrichten (einmal, 10 Minuten)

**Das ist der wichtigste Schritt.** Ohne ihn gehen hochgeladene Fotos
verloren, sobald der Server neu startet: Render legt den Container nach 15
Minuten ohne Zugriff schlafen, und beim Aufwachen ist seine Festplatte leer.
Fotos, die vormittags hochgeladen und erst abends abgeholt werden, wären dann
weg — während in der Datenbank noch ihre Verweise stehen.

Cloudflare R2 löst das. Bis 10 GB kostenlos; das reicht für Jahre
Baustellenfotos, zumal jeder Satz nach dem Abholen gelöscht werden kann.

1. Auf **dash.cloudflare.com** anmelden (kostenloses Konto genügt).
2. Links **R2 Object Storage** → **Create bucket**.
   Name z. B. `hpp-baustellenfotos`, Region `Automatic`.
3. Im Bucket oben rechts die **S3 API**-Adresse notieren. Sie sieht so aus:
   `https://<lange-kontonummer>.r2.cloudflarestorage.com`
4. Zurück auf der R2-Übersicht: **Manage API Tokens** → **Create API Token**
   → Recht **Object Read & Write**, beschränkt auf diesen einen Bucket.
   Danach werden **Access Key ID** und **Secret Access Key** angezeigt —
   das Secret nur dieses eine Mal. Kopieren.
5. Auf **dashboard.render.com** den Dienst `bautagesbericht` öffnen →
   **Environment** → vier Werte anlegen:

   | Schlüssel         | Wert                                            |
   |-------------------|-------------------------------------------------|
   | `BTB_R2_ENDPOINT` | `https://<kontonummer>.r2.cloudflarestorage.com` |
   | `BTB_R2_BUCKET`   | `hpp-baustellenfotos`                            |
   | `BTB_R2_KEY_ID`   | die Access Key ID                                |
   | `BTB_R2_SECRET`   | das Secret                                       |

6. Speichern. Render startet den Dienst neu — danach überstehen Fotos jeden
   Neustart.

> Ohne diese vier Werte läuft alles Übrige trotzdem. Nur muss dann jeder
> Fotosatz abgeholt werden, bevor der Server einschläft.

---

## Schritt 2 — Zielordner der Projekte pflegen

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

## Schritt 3 — Abholskript auf den Bürorechnern

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

## Optional: Abholung mit Losungswort

Die Abholrouten sind offen wie der Rest der App. Wer sie schützen will,
setzt auf Render `BTB_ABHOL_TOKEN` auf ein selbst gewähltes Wort und trägt
dasselbe Wort in die `einstellungen.txt` jedes Bürorechners ein. Ohne
passendes Wort antwortet der Server dann mit 401.
