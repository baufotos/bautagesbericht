"use client";

/**
 * Mangel auf der Baustelle erfassen.
 *
 * Reihenfolge und Umfang der Felder sind auf die Situation vor Ort abgestimmt:
 * oben das Wenige, das immer eingegeben wird (Firma, Kurzbezeichnung,
 * Beschreibung, Fotos), darunter Zusammengeklapptes für Ort, Frist und Mail.
 *
 * Ablauf beim Speichern — bewusst in Schritten, weil die Verbindung jederzeit
 * abbrechen kann:
 *   1. Mangel anlegen (kleiner JSON-Aufruf) — ab hier sind die Daten sicher.
 *   2. Fotos einzeln hochladen, mit Fortschrittsanzeige und Wiederholung.
 *   3. Plan-Markierung setzen, falls im Plan getippt wurde.
 * Scheitert Schritt 2 oder 3, ist der Mangel trotzdem angelegt; die Ansicht
 * sagt, was noch fehlt, und man kann es im Detail nachtragen.
 */

import { AlertTriangle, Loader2, Save } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { ladeFotosHoch } from "@/lib/fotoupload";
import type {
  Gewerk,
  MangelStammdaten,
  Prioritaet,
  ProjektPlan,
} from "@/lib/types";
import {
  Bereichstitel,
  Button,
  Card,
  Field,
  Input,
  Meldung,
  Section,
  Select,
  Textarea,
  formatDatum,
  heuteIso,
  isoPlusTage,
} from "@/components/ui";
import { FotoAuswahl } from "./FotoAufnahme";
import { PlanMarkierungFeld, type MarkierungsWert } from "./PlanMarkierung";

/** Vorschlag für die erste Frist: zwei Wochen, wie im Büro üblich. */
const FRIST_VORSCHLAG_TAGE = 14;

export function MangelErfassung({
  projektId,
  projektName,
  gewerke,
  plaene,
  stammdaten,
  onGespeichert,
  onAbbrechen,
}: {
  projektId: number;
  projektName: string;
  gewerke: Gewerk[];
  plaene: ProjektPlan[];
  stammdaten: MangelStammdaten | null;
  /** hinweis: was nach dem Anlegen noch offen blieb (Fotos, Markierung, Mail). */
  onGespeichert: (mangelId: number, hinweis?: string) => void;
  onAbbrechen: () => void;
}) {
  const [gewerkId, setGewerkId] = useState<string>("");
  const [typ, setTyp] = useState(stammdaten?.typen[0]?.bezeichnung || "Mangel");
  const [kurzbezeichnung, setKurzbezeichnung] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [prioritaet, setPrioritaet] = useState<Prioritaet>("mittel");
  const [raumnummer, setRaumnummer] = useState("");
  const [hinweisOrt, setHinweisOrt] = useState("");
  const [erstelltAm, setErstelltAm] = useState(heuteIso());
  const [fristBis, setFristBis] = useState(isoPlusTage(FRIST_VORSCHLAG_TAGE));
  const [aufgenommenVon, setAufgenommenVon] = useState("HPP Architekten GmbH");
  const [userId, setUserId] = useState<string>("");
  const [interneBemerkung, setInterneBemerkung] = useState("");
  const [farbmarkierung, setFarbmarkierung] = useState("");
  const [autosend, setAutosend] = useState(false);

  const [fotos, setFotos] = useState<File[]>([]);
  const [markierung, setMarkierung] = useState<MarkierungsWert | null>(null);

  const [speichert, setSpeichert] = useState(false);
  const [fortschritt, setFortschritt] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const gewaehltesGewerk = gewerke.find((g) => g.id === Number(gewerkId));
  const fehltMail = gewaehltesGewerk !== undefined && !gewaehltesGewerk.email;
  const kannSpeichern = kurzbezeichnung.trim().length > 0 && !speichert;

  async function speichern() {
    if (!kannSpeichern) return;
    setSpeichert(true);
    setFehler(null);

    try {
      // Schritt 1: Datensatz sichern.
      setFortschritt("Mangel wird angelegt…");
      const mangel = await api.maengel.create({
        projekt_id: projektId,
        kurzbezeichnung: kurzbezeichnung.trim(),
        typ,
        gewerk_id: gewerkId ? Number(gewerkId) : null,
        raumnummer: raumnummer.trim() || null,
        hinweis_ort: hinweisOrt.trim(),
        prioritaet,
        beschreibung: beschreibung.trim(),
        interne_bemerkung: interneBemerkung.trim(),
        farbmarkierung,
        erstellt_am: erstelltAm || null,
        erste_frist_bis: fristBis || null,
        aufgenommen_von: aufgenommenVon.trim() || "HPP Architekten GmbH",
        zustaendiger_user_id: userId ? Number(userId) : null,
        mail_autosend: autosend,
        mail_versendemodus: autosend ? "automatisch" : "manuell",
      });

      const offeneHinweise: string[] = [];

      // Schritt 2: Fotos einzeln nachschicken.
      if (fotos.length > 0) {
        const ergebnis = await ladeFotosHoch(mangel.id, fotos, (stand) =>
          setFortschritt(
            `Foto ${stand.aktuell} von ${stand.gesamt} wird übertragen…`
          )
        );
        if (ergebnis.fehlgeschlagen.length > 0) {
          offeneHinweise.push(
            `${ergebnis.fehlgeschlagen.length} von ${fotos.length} Foto(s) ` +
              "konnten nicht übertragen werden — im Mangel unter „Fotos“ erneut versuchen."
          );
        }
      }

      // Schritt 3: Plan-Markierung.
      if (markierung) {
        setFortschritt("Plan-Markierung wird gesetzt…");
        try {
          await api.maengel.setzeMarkierung(mangel.id, markierung);
        } catch {
          offeneHinweise.push(
            "Die Plan-Markierung wurde nicht gespeichert — im Mangel unter „Markierung“ nachtragen."
          );
        }
      }

      if (mangel.mail_fehler) {
        offeneHinweise.push(mangel.mail_fehler);
      }

      // Hinweise wandern mit in die Detailansicht — dort lässt sich das
      // Fehlende sofort nachtragen.
      onGespeichert(
        mangel.id,
        offeneHinweise.length > 0 ? offeneHinweise.join(" ") : undefined
      );
    } catch (err) {
      setFehler(
        err instanceof Error
          ? err.message
          : "Speichern fehlgeschlagen. Bitte erneut versuchen."
      );
    } finally {
      setSpeichert(false);
      setFortschritt(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Bereichstitel>Mangel erfassen · {projektName}</Bereichstitel>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {/* Das Wesentliche: ohne Klappen erreichbar. */}
      <Card className="flex flex-col gap-4 p-4">
        <Field
          label="Zuständige Firma / Büro"
          hinweis={
            gewerke.length === 0
              ? "Noch keine Firmen für dieses Projekt hinterlegt — unter „Stammdaten → Firmen“ anlegen."
              : undefined
          }
          fehler={
            fehltMail
              ? "Für diese Firma ist keine E-Mail-Adresse hinterlegt — Versand nur manuell möglich."
              : undefined
          }
        >
          <Select value={gewerkId} onChange={(e) => setGewerkId(e.target.value)}>
            <option value="">— Firma wählen —</option>
            {gewerke.map((g) => (
              <option key={g.id} value={g.id}>
                {g.anzeige_name}
              </option>
            ))}
          </Select>
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Typ">
            <Select value={typ} onChange={(e) => setTyp(e.target.value)}>
              {(stammdaten?.typen || []).map((t) => (
                <option key={t.id} value={t.bezeichnung}>
                  {t.sortierung} {t.bezeichnung}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Priorität">
            <Select
              value={prioritaet}
              onChange={(e) => setPrioritaet(e.target.value as Prioritaet)}
            >
              {(stammdaten?.prioritaeten || ["hoch", "mittel", "niedrig"]).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field label="Kurzbezeichnung (Pflicht)">
          <Input
            value={kurzbezeichnung}
            onChange={(e) => setKurzbezeichnung(e.target.value)}
            placeholder="z. B. Stahlbeton"
            autoFocus
          />
        </Field>

        <Field
          label="Beschreibung"
          hinweis="So genau, dass die Firma die Stelle ohne Rückfrage findet — das ist die Grundlage der Mängelrüge."
        >
          <Textarea
            value={beschreibung}
            onChange={(e) => setBeschreibung(e.target.value)}
            placeholder="Was ist zu beanstanden, wo genau, was ist zu tun?"
          />
        </Field>

        <FotoAuswahl dateien={fotos} onChange={setFotos} />
      </Card>

      <Section titel="Ort" offenStart={false} zusatz={[raumnummer, hinweisOrt].filter(Boolean).join(" · ")}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Raumnummer"
            hinweis="Freitext; später aus der Raumliste des Projekts wählbar."
          >
            <Input
              value={raumnummer}
              onChange={(e) => setRaumnummer(e.target.value)}
              placeholder="z. B. E.014"
            />
          </Field>
          <Field label="Hinweis Ort">
            <Input
              value={hinweisOrt}
              onChange={(e) => setHinweisOrt(e.target.value)}
              placeholder="z. B. EG"
            />
          </Field>
        </div>
      </Section>

      <Section
        titel="Markierung im Plan"
        offenStart={false}
        zusatz={markierung ? "Position gesetzt" : "keine Markierung"}
      >
        <PlanMarkierungFeld
          plaene={plaene}
          wert={markierung}
          onWert={setMarkierung}
        />
      </Section>

      <Section
        titel="Termine"
        offenStart={false}
        zusatz={fristBis ? `Frist ${formatDatum(fristBis)}` : ""}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Erstellt / 1. Frist gesetzt">
            <Input
              type="date"
              value={erstelltAm}
              onChange={(e) => setErstelltAm(e.target.value)}
            />
          </Field>
          <Field label="1. Frist bis">
            <Input
              type="date"
              value={fristBis}
              onChange={(e) => setFristBis(e.target.value)}
            />
          </Field>
          <Field label="Aufgenommen von">
            <Input
              value={aufgenommenVon}
              onChange={(e) => setAufgenommenVon(e.target.value)}
            />
          </Field>
          <Field label="User">
            <Select value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">— nicht zugeordnet —</option>
              {(stammdaten?.bearbeiter || []).map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </Section>

      <Section titel="Intern und Mail" offenStart={false}>
        <div className="flex flex-col gap-4">
          <Field
            label="Interne Bemerkung"
            hinweis="Nur intern sichtbar — steht nie in einer Fassung für die Firma."
          >
            <Textarea
              value={interneBemerkung}
              onChange={(e) => setInterneBemerkung(e.target.value)}
            />
          </Field>
          <Field label="Farbmarkierung" hinweis="Optionaler Farbcode für die Übersicht.">
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={farbmarkierung || "#B45309"}
                onChange={(e) => setFarbmarkierung(e.target.value)}
                className="size-9 cursor-pointer rounded-ui-sm border border-ui-line bg-ui-surface"
                aria-label="Farbe wählen"
              />
              {farbmarkierung && (
                <Button variante="still" onClick={() => setFarbmarkierung("")}>
                  Farbe entfernen
                </Button>
              )}
            </div>
          </Field>
          <label className="flex items-start gap-2.5 text-[13.5px]">
            <input
              type="checkbox"
              checked={autosend}
              disabled={fehltMail || !gewerkId}
              onChange={(e) => setAutosend(e.target.checked)}
              className="mt-0.5 size-4 accent-ui-accent"
            />
            <span className={fehltMail || !gewerkId ? "text-ui-text-faint" : ""}>
              Mängelrüge direkt nach dem Speichern an die Firma melden
              (Autosend).
              {(fehltMail || !gewerkId) && (
                <span className="mt-0.5 flex items-center gap-1 text-ui-danger">
                  <AlertTriangle size={13} />
                  {fehltMail
                    ? "Fehler! Firma/Büro hat keine Email-Adresse"
                    : "Erst eine Firma wählen"}
                </span>
              )}
            </span>
          </label>
        </div>
      </Section>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          onClick={speichern}
          disabled={!kannSpeichern}
          icon={speichert ? undefined : Save}
        >
          {speichert ? (
            <>
              <Loader2 size={15} className="animate-spin" />
              {fortschritt || "Wird gespeichert…"}
            </>
          ) : (
            "Mangel speichern"
          )}
        </Button>
        <Button variante="still" onClick={onAbbrechen} disabled={speichert}>
          Abbrechen
        </Button>
        {kurzbezeichnung.trim() === "" && (
          <span className="text-[12px] text-ui-text-muted">
            Die Kurzbezeichnung genügt — alles andere lässt sich später ergänzen.
          </span>
        )}
      </div>
    </div>
  );
}
