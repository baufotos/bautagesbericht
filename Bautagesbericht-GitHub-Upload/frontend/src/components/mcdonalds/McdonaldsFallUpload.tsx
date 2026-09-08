"use client";

/**
 * Eine Beauftragung in die App bringen — auf zwei Wegen.
 *
 * ZWEI WEGE, WEIL DAS BÜRO SO BEAUFTRAGT WIRD
 * ===========================================
 * Der Regelfall ist die Mail: Der Bauleiter exportiert sie in Outlook als
 * ``.eml`` und lädt sie hier hoch. Der zweite Fall steht auf dem
 * Konzeptblatt und ist keine Ausnahme, sondern Alltag — "bei telefonischer
 * Beauftragung Eingabe der Daten in die App". Deshalb sind es zwei
 * gleichwertige Umschalter und kein versteckter Zusatzknopf.
 *
 * WAS HIER NICHT PASSIERT
 * =======================
 * Es wird nicht gewartet. Der Projektordner entsteht im Hintergrund; diese
 * Ansicht springt nach dem Anlegen in die Detailansicht, wo der Status steht.
 * Und die Hinweise des Servers werden gezeigt, nicht verschluckt: Ohne
 * Anthropic-Schlüssel bleiben die Felder leer, und dann muss dastehen, dass
 * sie nachzutragen sind.
 */

import { Loader2, Phone, Plus, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { api } from "@/lib/api";
import type { McdonaldsFaehigkeiten, McdonaldsFall } from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  Plakette,
} from "@/components/dashboard";
import {
  Button,
  ChipLeiste,
  Chip,
  Field,
  Input,
  Meldung,
  Select,
  Textarea,
} from "@/components/ui";

/** Die Leistungsphasen zur Auswahl. 6–9 stehen vorn — sie sind der Alltag. */
const PHASEN = [6, 7, 8, 9, 1, 2, 3, 4, 5];

type Weg = "eml" | "telefon";

/** Eine Zeile des Abschnitts „weitere Eckdaten“. */
interface EckdatenZeile {
  bezeichnung: string;
  wert: string;
}

export function McdonaldsFallUpload({
  faehigkeiten,
  onAngelegt,
}: {
  faehigkeiten: McdonaldsFaehigkeiten | null;
  onAngelegt: (fall: McdonaldsFall) => void;
}) {
  const [weg, setWeg] = useState<Weg>("eml");
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const dateiwahl = useRef<HTMLInputElement>(null);

  // Felder des telefonischen Wegs
  const [standortName, setStandortName] = useState("");
  const [adresse, setAdresse] = useState("");
  const [ort, setOrt] = useState("");
  const [auftraggeber, setAuftraggeber] = useState("");
  const [phase, setPhase] = useState("");
  const [notiz, setNotiz] = useState("");
  const [eckdaten, setEckdaten] = useState<EckdatenZeile[]>([]);

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

  async function telefonischAnlegen() {
    if (!standortName.trim()) return;
    setLaeuft(true);
    setFehler(null);
    try {
      const gesammelt: Record<string, string> = {};
      for (const zeile of eckdaten) {
        if (zeile.bezeichnung.trim() && zeile.wert.trim()) {
          gesammelt[zeile.bezeichnung.trim()] = zeile.wert.trim();
        }
      }
      onAngelegt(
        await api.mcdonalds.manuell({
          standort_name: standortName.trim(),
          standort_adresse: adresse.trim(),
          standort_ort: ort.trim(),
          auftraggeber: auftraggeber.trim(),
          leistungsphase: phase ? Number(phase) : null,
          eckdaten: gesammelt,
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
          Mail hochladen
        </Chip>
        <Chip aktiv={weg === "telefon"} onClick={() => setWeg("telefon")}>
          Telefonische Beauftragung
        </Chip>
      </ChipLeiste>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {weg === "eml" ? (
        <Karte>
          <KarteKopf
            titel="Auftragsmail hochladen"
            unterzeile="In Outlook: Datei → Speichern unter → Dateityp „.eml“."
            icon={Upload}
            aktion={
              faehigkeiten && !faehigkeiten.analyse ? (
                <Plakette art="warn">ohne KI-Analyse</Plakette>
              ) : undefined
            }
          />
          <KarteInhalt className="flex flex-col gap-3">
            {faehigkeiten && !faehigkeiten.analyse && (
              <Meldung art="hinweis">
                Es ist kein Anthropic-Schlüssel hinterlegt. Die Mail wird
                gespeichert, aber nicht automatisch ausgewertet — Standort,
                Auftraggeber und Leistungsphase sind danach von Hand
                einzutragen. Der Schlüssel steht in{" "}
                <span className="font-mono">einstellungen.txt</span> bei
                „anthropic_key=“.
              </Meldung>
            )}

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
          </KarteInhalt>
        </Karte>
      ) : (
        <Karte>
          <KarteKopf
            titel="Telefonische Beauftragung erfassen"
            unterzeile="Der Projektordner entsteht danach genauso im Hintergrund."
            icon={Phone}
          />
          <KarteInhalt className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Standort (Pflicht)"
                hinweis="Steht im Ordnernamen hinter dem UN/LOCODE."
              >
                <Input
                  value={standortName}
                  onChange={(e) => setStandortName(e.target.value)}
                  placeholder="z. B. Aachen Europaplatz"
                  autoFocus
                />
              </Field>
              <Field label="Auftraggeber">
                <Input
                  value={auftraggeber}
                  onChange={(e) => setAuftraggeber(e.target.value)}
                  placeholder="beauftragendes Unternehmen"
                />
              </Field>
              <Field label="Anschrift">
                <Input
                  value={adresse}
                  onChange={(e) => setAdresse(e.target.value)}
                  placeholder="Straße, PLZ Ort"
                />
              </Field>
              <Field
                label="Ort"
                hinweis="Leer lassen — wird aus der Anschrift abgeleitet."
              >
                <Input
                  value={ort}
                  onChange={(e) => setOrt(e.target.value)}
                  placeholder="nur bei Bedarf"
                />
              </Field>
              <Field label="Leistungsphase">
                <Select value={phase} onChange={(e) => setPhase(e.target.value)}>
                  <option value="">nicht angegeben</option>
                  {PHASEN.map((p) => (
                    <option key={p} value={p}>
                      LPH {p}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            <Field
              label="Gesprächsnotiz"
              hinweis="Worauf die Angaben beruhen — bei einem Anruf die einzige Quelle."
            >
              <Textarea
                value={notiz}
                onChange={(e) => setNotiz(e.target.value)}
                placeholder="Wer hat wann angerufen, was wurde vereinbart?"
              />
            </Field>

            <EckdatenFelder zeilen={eckdaten} onAendern={setEckdaten} />

            <div className="flex gap-2">
              <Button
                onClick={telefonischAnlegen}
                disabled={laeuft || !standortName.trim()}
                icon={laeuft ? Loader2 : Plus}
              >
                {laeuft ? "Wird angelegt…" : "Beauftragung anlegen"}
              </Button>
            </div>
          </KarteInhalt>
        </Karte>
      )}
    </div>
  );
}

/**
 * Dynamische Zeilenliste für „weitere Eckdaten“.
 *
 * Dasselbe Muster wie die Mehrleistungen im Angebotsformular: hinzufügen,
 * entfernen, beliebig viele Zeilen. Leere Zeilen werden beim Speichern
 * verworfen und nicht bemängelt — sie entstehen durch die Bedienung.
 */
function EckdatenFelder({
  zeilen,
  onAendern,
}: {
  zeilen: EckdatenZeile[];
  onAendern: (zeilen: EckdatenZeile[]) => void;
}) {
  function setze(index: number, teil: Partial<EckdatenZeile>) {
    onAendern(zeilen.map((z, i) => (i === index ? { ...z, ...teil } : z)));
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[10.5px] tracking-[0.1em] uppercase text-app-text-leise">
          Weitere Eckdaten (optional)
        </span>
        <Button
          variante="still"
          icon={Plus}
          onClick={() => onAendern([...zeilen, { bezeichnung: "", wert: "" }])}
        >
          Zeile
        </Button>
      </div>

      {zeilen.length === 0 && (
        <p className="text-[12px] text-app-text-still">
          Termine, Bestellnummern, Ansprechpartner — was am Telefon genannt
          wurde.
        </p>
      )}

      {zeilen.map((zeile, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input
            value={zeile.bezeichnung}
            onChange={(e) => setze(index, { bezeichnung: e.target.value })}
            placeholder="Bezeichnung"
            className="flex-1"
          />
          <Input
            value={zeile.wert}
            onChange={(e) => setze(index, { wert: e.target.value })}
            placeholder="Wert"
            className="flex-1"
          />
          <button
            type="button"
            onClick={() => onAendern(zeilen.filter((_, i) => i !== index))}
            aria-label={`Zeile ${index + 1} entfernen`}
            className="cursor-pointer p-2 text-app-text-leise transition-colors hover:text-app-gefahr"
          >
            <Trash2 size={15} />
          </button>
        </div>
      ))}
    </div>
  );
}
