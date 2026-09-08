"use client";

/**
 * Angebot zur Beauftragung eines Fachplaners erfassen.
 *
 * DREI TEILE, DIE ZUSAMMENGEHÖREN
 * ===============================
 * 1. **Kernangaben** — Betreff und Leistungsphase stehen fest, alles Weitere
 *    ist heute eine freie Zeilenliste. Das ist Absicht und kein Provisorium
 *    zweiter Klasse: Die Angebotsvorlage des Büros liegt noch nicht vor
 *    (siehe TODO McDonald's in backend/app/services/
 *    mcdonalds_angebot_generation), und bis dahin soll niemand auf Felder
 *    warten müssen.
 * 2. **Mehrleistungen** — beliebig viele Zeilen, Betrag darf fehlen. Am
 *    Telefon steht oft erst die Leistung fest.
 * 3. **Fachplaner** — aus den Stammdaten, mit „Neu anlegen“ direkt hier.
 *    Wer mitten im Angebot merkt, dass das Büro noch fehlt, soll nicht in die
 *    Stammdaten wechseln und das Formular verlieren.
 *
 * Der letzte Knopf macht beides in einem Zug: Dokument erzeugen und
 * Outlook-Entwurf herunterladen. Das ist der Ablauf des Konzeptblatts
 * („Automatischer Outlook-Entwurf mit passendem Dokument“) — zwei Klicks
 * dafür wären zwei Gelegenheiten, den zweiten zu vergessen.
 */

import { Building2, Loader2, Mail, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { dateiSpeichern } from "@/lib/dateien";
import type {
  Fachplaner,
  McdonaldsFaehigkeiten,
  McdonaldsFall,
  Mehrleistung,
} from "@/lib/types";
import { Karte, KarteInhalt, KarteKopf } from "@/components/dashboard";
import {
  Button,
  Field,
  Input,
  Meldung,
  Select,
  Textarea,
} from "@/components/ui";

const PHASEN = [6, 7, 8, 9, 1, 2, 3, 4, 5];

/** Eine Zeile der Kernangaben. */
interface AngabenZeile {
  bezeichnung: string;
  wert: string;
}

/**
 * Womit die Kernangaben starten.
 *
 * TODO McDonald's: Wird durch die echten Felder der Angebotsvorlage ersetzt,
 * sobald sie vorliegt. Bis dahin sind es Vorschläge — jede Zeile ist
 * änderbar und entfernbar, es geht keine Angabe verloren, die nicht
 * hineinpasst.
 */
const ANGABEN_VORSCHLAG: AngabenZeile[] = [
  { bezeichnung: "Honorarzone", wert: "" },
  { bezeichnung: "Anrechenbare Kosten", wert: "" },
  { bezeichnung: "Honorar", wert: "" },
];

export function AngebotErstellen({
  fall,
  fachplaner,
  faehigkeiten,
  onFertig,
  onAbbrechen,
  onFachplanerAendern,
}: {
  fall: McdonaldsFall;
  fachplaner: Fachplaner[];
  faehigkeiten: McdonaldsFaehigkeiten | null;
  onFertig: () => void;
  onAbbrechen: () => void;
  onFachplanerAendern: () => void;
}) {
  const [fachplanerId, setFachplanerId] = useState<string>(
    fachplaner.length === 1 ? String(fachplaner[0].id) : ""
  );
  const [neuOffen, setNeuOffen] = useState(false);
  const [betreff, setBetreff] = useState(
    fall.standort_name
      ? `Beauftragung ${fall.standort_name}` +
          (fall.leistungsphase ? ` — LPH ${fall.leistungsphase}` : "")
      : ""
  );
  const [phase, setPhase] = useState(
    fall.leistungsphase ? String(fall.leistungsphase) : ""
  );
  const [angaben, setAngaben] = useState<AngabenZeile[]>(ANGABEN_VORSCHLAG);
  const [mehrleistungen, setMehrleistungen] = useState<Mehrleistung[]>([]);
  const [laeuft, setLaeuft] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const gewaehlt = fachplaner.find((p) => String(p.id) === fachplanerId);
  const bereit = fachplanerId !== "";

  function gesammelteAngaben(): Record<string, string> {
    const werte: Record<string, string> = {};
    for (const zeile of angaben) {
      if (zeile.bezeichnung.trim() && zeile.wert.trim()) {
        werte[zeile.bezeichnung.trim()] = zeile.wert.trim();
      }
    }
    return werte;
  }

  /**
   * Angebot anlegen — und auf Wunsch gleich Dokument und Entwurf erzeugen.
   *
   * Der Entwurf wird nicht still übersprungen, wenn er scheitert: Das Angebot
   * ist dann angelegt (es steht in der Liste), aber die Meldung sagt, dass
   * der Entwurf fehlt. Sonst würde jemand auf eine Mail warten, die es nicht
   * gibt.
   */
  async function speichern(mitEntwurf: boolean) {
    if (!bereit) return;
    setLaeuft(mitEntwurf ? "entwurf" : "speichern");
    setFehler(null);
    try {
      const angebot = await api.mcdonalds.angebotAnlegen(fall.id, {
        fachplaner_id: Number(fachplanerId),
        betreff: betreff.trim(),
        leistungsphase: phase ? Number(phase) : null,
        angaben: gesammelteAngaben(),
        mehrleistungen: mehrleistungen.filter((m) => m.bezeichnung.trim()),
      });

      if (!mitEntwurf) {
        onFertig();
        return;
      }

      const dokument = await api.mcdonalds.dokumentErzeugen(angebot.id);
      dateiSpeichern(dokument.blob, dokument.dateiname || "angebot.docx");

      const entwurf = await api.mcdonalds.entwurf(angebot.id);
      dateiSpeichern(entwurf.blob, entwurf.dateiname || "angebot.eml");

      onFertig();
    } catch (err) {
      setFehler(
        (err instanceof Error ? err.message : "Speichern fehlgeschlagen.") +
          (mitEntwurf
            ? " Prüfe in der Angebotsliste, ob das Angebot angelegt wurde — " +
              "es kann trotzdem entstanden sein."
            : "")
      );
    } finally {
      setLaeuft("");
    }
  }

  return (
    <Karte>
      <KarteKopf
        titel="Angebot erstellen"
        icon={Building2}
        unterzeile={
          fall.standort_name
            ? `Standort ${fall.standort_name}`
            : "Standort noch nicht erfasst"
        }
      />
      <KarteInhalt className="flex flex-col gap-4">
        {fehler && <Meldung art="fehler">{fehler}</Meldung>}

        {/* ── Fachplaner ── */}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Fachplaner-Unternehmen (Pflicht)"
            hinweis={
              gewaehlt
                ? `Entwurf geht an ${gewaehlt.email}`
                : "Aus den Stammdaten — die hinterlegte Adresse wird der Empfänger."
            }
          >
            <div className="flex gap-2">
              <Select
                value={fachplanerId}
                onChange={(e) => setFachplanerId(e.target.value)}
                className="min-w-0 flex-1"
              >
                <option value="">bitte wählen</option>
                {fachplaner.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                    {p.ansprechpartner ? ` — ${p.ansprechpartner}` : ""}
                  </option>
                ))}
              </Select>
              <Button
                variante="sekundaer"
                icon={Plus}
                onClick={() => setNeuOffen((offen) => !offen)}
              >
                Neu
              </Button>
            </div>
          </Field>

          <Field label="Leistungsphase">
            <Select value={phase} onChange={(e) => setPhase(e.target.value)}>
              <option value="">wie im Fall</option>
              {PHASEN.map((p) => (
                <option key={p} value={p}>
                  LPH {p}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        {neuOffen && (
          <FachplanerAnlegen
            onFertig={(neuerId) => {
              setNeuOffen(false);
              setFachplanerId(String(neuerId));
              onFachplanerAendern();
            }}
            onAbbrechen={() => setNeuOffen(false)}
          />
        )}

        <Field
          label="Betreff"
          hinweis="Steht im Dokumentkopf und in der Betreffzeile des Entwurfs."
        >
          <Textarea
            value={betreff}
            onChange={(e) => setBetreff(e.target.value)}
            rows={2}
            placeholder="Leer lassen — dann setzt die App einen Vorschlag ein."
          />
        </Field>

        {/* ── Kernangaben ── */}
        <ZeilenListe
          titel="Kernangaben"
          hinweis="Bis die Angebotsvorlage des Büros vorliegt, sind die Felder frei wählbar."
          zeilen={angaben}
          onAendern={setAngaben}
          platzhalterLinks="Bezeichnung"
          platzhalterRechts="Wert"
          leerText="Keine Kernangaben — das Dokument zeigt dann nur Standort und Fachplaner."
        />

        {/* ── Mehrleistungen ── */}
        <MehrleistungenListe
          zeilen={mehrleistungen}
          onAendern={setMehrleistungen}
        />

        {/* ── Aktionen ── */}
        <div className="flex flex-wrap gap-2 border-t border-app-linie pt-3">
          <Button
            onClick={() => speichern(true)}
            disabled={laeuft !== "" || !bereit}
            icon={laeuft === "entwurf" ? Loader2 : Mail}
          >
            {laeuft === "entwurf"
              ? "Wird erzeugt…"
              : "Angebot erzeugen & Outlook-Entwurf"}
          </Button>
          <Button
            variante="sekundaer"
            onClick={() => speichern(false)}
            disabled={laeuft !== "" || !bereit}
          >
            {laeuft === "speichern" ? "Wird gespeichert…" : "Nur speichern"}
          </Button>
          <Button variante="still" icon={X} onClick={onAbbrechen}>
            Abbrechen
          </Button>
        </div>

        {faehigkeiten && !faehigkeiten.smtp && (
          <p className="text-[12px] text-app-text-still">
            Der Outlook-Entwurf wird als <span className="font-mono">.eml</span>{" "}
            heruntergeladen; ein Doppelklick öffnet ihn mit Empfänger, Text und
            Angebot im Anhang. Abgeschickt wird er von Outlook — die App
            verschickt selbst keine Mail, solange kein Postausgangsserver
            hinterlegt ist.
          </p>
        )}
      </KarteInhalt>
    </Karte>
  );
}

/** Fachplaner direkt aus dem Angebotsformular anlegen. */
function FachplanerAnlegen({
  onFertig,
  onAbbrechen,
}: {
  onFertig: (id: number) => void;
  onAbbrechen: () => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [ansprechpartner, setAnsprechpartner] = useState("");
  const [speichert, setSpeichert] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  const bereit = name.trim() !== "" && email.trim() !== "";

  async function anlegen() {
    if (!bereit) return;
    setSpeichert(true);
    setFehler(null);
    try {
      const neu = await api.fachplaner.create({
        name: name.trim(),
        email: email.trim(),
        ansprechpartner: ansprechpartner.trim(),
      });
      onFertig(neu.id);
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Speichern fehlgeschlagen.");
    } finally {
      setSpeichert(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-app-sm border border-app-linie bg-app-flaeche-still p-3">
      <span className="font-mono text-[10.5px] tracking-[0.1em] uppercase text-app-text-leise">
        Neuer Fachplaner
      </span>
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Unternehmen">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && anlegen()}
            autoFocus
          />
        </Field>
        <Field label="E-Mail">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && anlegen()}
          />
        </Field>
        <Field label="Ansprechpartner">
          <Input
            value={ansprechpartner}
            onChange={(e) => setAnsprechpartner(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && anlegen()}
          />
        </Field>
      </div>
      <div className="flex gap-2">
        <Button onClick={anlegen} disabled={speichert || !bereit} icon={Plus}>
          Übernehmen
        </Button>
        <Button variante="still" icon={X} onClick={onAbbrechen}>
          Abbrechen
        </Button>
      </div>
    </div>
  );
}

/** Zwei Textspalten, beliebig viele Zeilen — hinzufügen und entfernen. */
function ZeilenListe({
  titel,
  hinweis,
  zeilen,
  onAendern,
  platzhalterLinks,
  platzhalterRechts,
  leerText,
}: {
  titel: string;
  hinweis?: string;
  zeilen: AngabenZeile[];
  onAendern: (zeilen: AngabenZeile[]) => void;
  platzhalterLinks: string;
  platzhalterRechts: string;
  leerText: string;
}) {
  function setze(index: number, teil: Partial<AngabenZeile>) {
    onAendern(zeilen.map((z, i) => (i === index ? { ...z, ...teil } : z)));
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <span className="font-mono text-[10.5px] tracking-[0.1em] uppercase text-app-text-leise">
            {titel}
          </span>
          {hinweis && (
            <p className="mt-0.5 text-[12px] text-app-text-still">{hinweis}</p>
          )}
        </div>
        <Button
          variante="still"
          icon={Plus}
          onClick={() => onAendern([...zeilen, { bezeichnung: "", wert: "" }])}
        >
          Zeile
        </Button>
      </div>

      {zeilen.length === 0 && (
        <p className="text-[12px] text-app-text-still">{leerText}</p>
      )}

      {zeilen.map((zeile, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input
            value={zeile.bezeichnung}
            onChange={(e) => setze(index, { bezeichnung: e.target.value })}
            placeholder={platzhalterLinks}
            className="flex-1"
          />
          <Input
            value={zeile.wert}
            onChange={(e) => setze(index, { wert: e.target.value })}
            placeholder={platzhalterRechts}
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

/**
 * Die Mehrleistungen: Bezeichnung plus Betrag.
 *
 * Der Betrag ist ausdrücklich optional, und ein leeres Feld bleibt leer —
 * nicht 0. Eine Null im Angebot wäre eine Aussage über den Preis, und zwar
 * eine falsche.
 */
function MehrleistungenListe({
  zeilen,
  onAendern,
}: {
  zeilen: Mehrleistung[];
  onAendern: (zeilen: Mehrleistung[]) => void;
}) {
  function setze(index: number, teil: Partial<Mehrleistung>) {
    onAendern(zeilen.map((z, i) => (i === index ? { ...z, ...teil } : z)));
  }

  const summe = zeilen.reduce((s, z) => s + (z.betrag ?? 0), 0);
  const hatBetrag = zeilen.some((z) => z.betrag !== null);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <span className="font-mono text-[10.5px] tracking-[0.1em] uppercase text-app-text-leise">
            Mehrleistungen (optional)
          </span>
          <p className="mt-0.5 text-[12px] text-app-text-still">
            Der Betrag darf offen bleiben — dann steht im Angebot ein
            Gedankenstrich statt einer Null.
          </p>
        </div>
        <Button
          variante="still"
          icon={Plus}
          onClick={() => onAendern([...zeilen, { bezeichnung: "", betrag: null }])}
        >
          Zeile
        </Button>
      </div>

      {zeilen.length === 0 && (
        <p className="text-[12px] text-app-text-still">
          Keine Mehrleistungen — im Angebot steht dann „Keine Mehrleistungen
          vereinbart“.
        </p>
      )}

      {zeilen.map((zeile, index) => (
        <div key={index} className="flex items-center gap-2">
          <Input
            value={zeile.bezeichnung}
            onChange={(e) => setze(index, { bezeichnung: e.target.value })}
            placeholder="Bezeichnung der Mehrleistung"
            className="min-w-0 flex-1"
          />
          <Input
            type="number"
            step="0.01"
            min="0"
            value={zeile.betrag ?? ""}
            onChange={(e) =>
              setze(index, {
                betrag: e.target.value === "" ? null : Number(e.target.value),
              })
            }
            placeholder="Betrag €"
            className="w-32"
          />
          <button
            type="button"
            onClick={() => onAendern(zeilen.filter((_, i) => i !== index))}
            aria-label={`Mehrleistung ${index + 1} entfernen`}
            className="cursor-pointer p-2 text-app-text-leise transition-colors hover:text-app-gefahr"
          >
            <Trash2 size={15} />
          </button>
        </div>
      ))}

      {hatBetrag && (
        <div className="flex justify-end text-[12.5px] font-semibold text-app-text">
          Summe:{" "}
          {summe.toLocaleString("de-DE", {
            style: "currency",
            currency: "EUR",
          })}
        </div>
      )}
    </div>
  );
}
