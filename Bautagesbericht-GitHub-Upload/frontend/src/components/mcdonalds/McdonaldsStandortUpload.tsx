"use client";

/**
 * Einen Standort in die App bringen — aus der SLS-Anfrage oder von Hand.
 *
 * DER REGELFALL IST DIE MAIL
 * ==========================
 * McDonald's legt den Standort im eigenen System an und schickt eine Anfrage
 * ("SLS - Anfrage zur F1 Vorbereitung 56132 Nievern, Auf d. Lay"). Ricardo
 * leitet sie weiter, hier wird sie als ``.eml`` hochgeladen. Phase, Ort,
 * Straße, Abgabetermin und Leistungsbeginn liest die App **ohne KI** heraus:
 * Die Mail ist maschinenerzeugt und immer gleich aufgebaut (siehe
 * backend/app/services/mcdonalds_sls.py). Deshalb steht hier auch kein
 * Hinweis auf einen fehlenden Schlüssel — er wird für diesen Weg nicht
 * gebraucht.
 *
 * Der zweite Weg ist für den Fall, dass keine Mail vorliegt: telefonisch, aus
 * einer Besprechung, aus einer Mail in anderem Format.
 */

import { Loader2, MapPin, Plus, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { api } from "@/lib/api";
import type { McdFaehigkeiten, McdStandort } from "@/lib/types";
import { Karte, KarteInhalt, KarteKopf } from "@/components/dashboard";
import {
  Button,
  Chip,
  ChipLeiste,
  Field,
  Input,
  Meldung,
  Select,
  Textarea,
} from "@/components/ui";

const PHASEN = [1, 2, 3];

type Weg = "eml" | "manuell";

export function McdonaldsStandortUpload({
  faehigkeiten,
  onAngelegt,
}: {
  faehigkeiten: McdFaehigkeiten | null;
  onAngelegt: (standort: McdStandort) => void;
}) {
  const [weg, setWeg] = useState<Weg>("eml");
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const dateiwahl = useRef<HTMLInputElement>(null);

  const [ort, setOrt] = useState("");
  const [plz, setPlz] = useState("");
  const [strasse, setStrasse] = useState("");
  const [phase, setPhase] = useState("");
  const [abgabe, setAbgabe] = useState("");
  const [beginn, setBeginn] = useState("");
  const [notiz, setNotiz] = useState("");

  async function hochladen(dateien: FileList | null) {
    const datei = dateien?.[0];
    if (!datei) return;
    setLaeuft(true);
    setFehler(null);
    try {
      onAngelegt(await api.mcdonalds.hochladen(datei));
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Upload fehlgeschlagen.");
    } finally {
      setLaeuft(false);
      // Zurücksetzen, damit dieselbe Datei ein zweites Mal gewählt werden
      // kann — ohne das feuert onChange nicht erneut.
      if (dateiwahl.current) dateiwahl.current.value = "";
    }
  }

  async function manuellAnlegen() {
    if (!ort.trim()) return;
    setLaeuft(true);
    setFehler(null);
    try {
      onAngelegt(
        await api.mcdonalds.manuell({
          ort: ort.trim(),
          plz: plz.trim(),
          strasse: strasse.trim(),
          phase: phase ? Number(phase) : null,
          abgabetermin: abgabe || null,
          leistungsbeginn: beginn || null,
          notiz: notiz.trim(),
        })
      );
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Anlegen fehlgeschlagen.");
    } finally {
      setLaeuft(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <ChipLeiste>
        <Chip aktiv={weg === "eml"} onClick={() => setWeg("eml")}>
          SLS-Anfrage hochladen
        </Chip>
        <Chip aktiv={weg === "manuell"} onClick={() => setWeg("manuell")}>
          Von Hand erfassen
        </Chip>
      </ChipLeiste>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {weg === "eml" ? (
        <Karte>
          <KarteKopf
            titel="SLS-Anfrage hochladen"
            unterzeile="In Outlook: Datei → Speichern unter → Dateityp „.eml“."
            icon={Upload}
          />
          <KarteInhalt className="flex flex-col gap-3">
            <p className="text-[12.5px] leading-relaxed text-app-text-still">
              Aus dem Betreff liest die App Phase, Postleitzahl, Ort und
              Straße, aus dem Text den Abgabetermin und die
              SLS-Vorgangsnummer — und aus dem weitergeleiteten Kopf das Datum
              der Original­anfrage als Leistungsbeginn. Dafür ist kein
              KI-Schlüssel nötig.
            </p>

            <input
              ref={dateiwahl}
              type="file"
              accept=".eml,message/rfc822"
              onChange={(e) => void hochladen(e.target.files)}
              className="hidden"
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                icon={laeuft ? Loader2 : Upload}
                onClick={() => dateiwahl.current?.click()}
                disabled={laeuft}
              >
                {laeuft ? "Wird gelesen…" : "Mail wählen"}
              </Button>
              <span className="text-[12px] text-app-text-still">
                Anhänge bitte nicht mitexportieren — sie gehören in den
                Projektordner.
              </span>
            </div>

            {faehigkeiten && faehigkeiten.unterordner > 0 && (
              <p className="text-[12px] text-app-text-leise">
                Danach entsteht der Standortordner{" "}
                <span className="font-mono">&lt;CODE&gt;_&lt;Ort&gt;</span> mit{" "}
                {faehigkeiten.unterordner} Unterordnern
                {faehigkeiten.ordner_laufwerk
                  ? " auf dem Projektlaufwerk."
                  : " — auf dem Projektlaufwerk anzulegen von einem Rechner im Büronetz."}
              </p>
            )}
          </KarteInhalt>
        </Karte>
      ) : (
        <Karte>
          <KarteKopf
            titel="Standort von Hand erfassen"
            unterzeile="Der Ordner entsteht danach genauso."
            icon={MapPin}
          />
          <KarteInhalt className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Ort (Pflicht)"
                hinweis="Grundlage des Ortscodes und des Ordnernamens."
              >
                <Input
                  value={ort}
                  onChange={(e) => setOrt(e.target.value)}
                  placeholder="z. B. Nievern"
                  autoFocus
                />
              </Field>
              <Field label="Postleitzahl">
                <Input
                  value={plz}
                  onChange={(e) => setPlz(e.target.value)}
                  placeholder="56132"
                />
              </Field>
              <Field label="Straße">
                <Input
                  value={strasse}
                  onChange={(e) => setStrasse(e.target.value)}
                  placeholder="Auf d. Lay"
                />
              </Field>
              <Field label="Phase">
                <Select value={phase} onChange={(e) => setPhase(e.target.value)}>
                  <option value="">nicht angegeben</option>
                  {PHASEN.map((p) => (
                    <option key={p} value={p}>
                      Phase {p}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field
                label="Abgabetermin"
                hinweis="Steht im Einzelabruf als „Abgabe Phase …“."
              >
                <Input
                  type="date"
                  value={abgabe}
                  onChange={(e) => setAbgabe(e.target.value)}
                />
              </Field>
              <Field
                label="Leistungsbeginn"
                hinweis="Tag der Anfrage — steht so im Einzelabruf."
              >
                <Input
                  type="date"
                  value={beginn}
                  onChange={(e) => setBeginn(e.target.value)}
                />
              </Field>
            </div>

            <Field
              label="Notiz"
              hinweis="Worauf die Angaben beruhen — ohne Mail die einzige Quelle."
            >
              <Textarea
                value={notiz}
                onChange={(e) => setNotiz(e.target.value)}
                placeholder="Wer hat wann was mitgeteilt?"
              />
            </Field>

            <div>
              <Button
                onClick={manuellAnlegen}
                disabled={laeuft || !ort.trim()}
                icon={laeuft ? Loader2 : Plus}
              >
                {laeuft ? "Wird angelegt…" : "Standort anlegen"}
              </Button>
            </div>
          </KarteInhalt>
        </Karte>
      )}
    </div>
  );
}
