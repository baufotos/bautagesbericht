"use client";

/**
 * Die Subplaner einer Phase beauftragen — mit Vorschau vor dem Erzeugen.
 *
 * DER ABLAUF IN DREI SCHRITTEN
 * ============================
 * 1. **Phase wählen** (1, 2 oder 3). Welche Firmen dazugehören, steht in den
 *    Stammdaten — in Phase 1 sind es Kocks und RKA. Die Auswahl ist der
 *    Einstieg, nicht ein Feld unter vielen: Von ihr hängt alles Weitere ab.
 * 2. **Termine prüfen.** Alle sind vorbelegt (aus der SLS-Anfrage und den
 *    Regeln) und alle sind überschreibbar. Es sind Termine in einem Vertrag.
 * 3. **Vorschau lesen, dann erzeugen.** Für jede Firma steht der vollständige
 *    Wortlaut da, wie ihn der Subplaner bekommt. Erst danach entstehen die
 *    Entwürfe — bei Phase 1 also zwei, in einem Zug.
 *
 * WARUM DIE VORSCHAU NICHT ÜBERSPRUNGEN WERDEN KANN
 * =================================================
 * Weil hier Vertragsschreiben entstehen, deren Termine aus einer Regel
 * kommen. Ein Knopf „direkt losschicken" würde genau die Prüfung einsparen,
 * die den Unterschied zwischen einem Entwurf und einem Fehler macht. Die
 * Entwürfe gehen ohnehin nur nach Outlook — abgeschickt werden sie von einem
 * Menschen.
 */

import {
  AlertTriangle,
  Building2,
  CalendarClock,
  Download,
  Eye,
  Loader2,
  Send,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { dateiSpeichern } from "@/lib/dateien";
import type {
  BeauftragungAnfrage,
  BeauftragungVorschau,
  McdFaehigkeiten,
  McdStandort,
  Subplaner,
} from "@/lib/types";
import { Karte, KarteInhalt, KarteKopf, Plakette } from "@/components/dashboard";
import { Button, Chip, ChipLeiste, Field, Input, Meldung } from "@/components/ui";

const PHASEN = [1, 2, 3];

/** ISO-Datum von heute — für die Vorbelegung des Beauftragungsdatums. */
function heute(): string {
  return new Date().toISOString().slice(0, 10);
}

export function BeauftragungErstellen({
  standort,
  subplaner,
  faehigkeiten,
  onFertig,
  onAbbrechen,
}: {
  standort: McdStandort;
  subplaner: Subplaner[];
  faehigkeiten: McdFaehigkeiten | null;
  onFertig: () => void;
  onAbbrechen: () => void;
}) {
  const [phase, setPhase] = useState<number>(standort.phase ?? 1);
  const [beauftragungAm, setBeauftragungAm] = useState(heute());
  const [beginn, setBeginn] = useState(standort.leistungsbeginn ?? "");
  const [abgabe, setAbgabe] = useState(standort.abgabetermin ?? "");
  const [projektplanung, setProjektplanung] = useState(
    standort.abgabetermin ?? ""
  );
  const [klaerung, setKlaerung] = useState("");
  const [vorschau, setVorschau] = useState<BeauftragungVorschau[] | null>(null);
  const [laeuft, setLaeuft] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);

  const derPhase = subplaner.filter((s) => s.phase === phase);
  const ohneAdresse = derPhase.filter((s) => s.emails.length === 0);

  const anfrage = useCallback(
    (): BeauftragungAnfrage => ({
      phase,
      beauftragung_am: beauftragungAm || null,
      leistungsbeginn: beginn || null,
      projektplanung: projektplanung || null,
      klaerung: klaerung || null,
      abgabe: abgabe || null,
    }),
    [phase, beauftragungAm, beginn, projektplanung, klaerung, abgabe]
  );

  /* Die Vorschau kommt vom Server, damit im Entwurf garantiert derselbe Text
     steht wie hier — die Vorlagen liegen im Backend, nicht doppelt. */
  const ladeVorschau = useCallback(async () => {
    setLaeuft("vorschau");
    setFehler(null);
    try {
      setVorschau(await api.mcdonalds.vorschau(standort.id, anfrage()));
    } catch (err) {
      setVorschau(null);
      setFehler(err instanceof Error ? err.message : "Vorschau nicht möglich.");
    } finally {
      setLaeuft("");
    }
  }, [standort.id, anfrage]);

  // Beim Öffnen und bei jeder Änderung neu — man soll sehen, was ein anderes
  // Datum am Wortlaut ändert, ohne einen Knopf dafür zu suchen.
  useEffect(() => {
    void ladeVorschau();
  }, [ladeVorschau]);

  async function erzeugen() {
    setLaeuft("erzeugen");
    setFehler(null);
    setMeldung(null);
    try {
      const { blob, dateiname } = await api.mcdonalds.beauftragen(
        standort.id,
        anfrage()
      );
      dateiSpeichern(blob, dateiname || "beauftragungen.zip");
      setMeldung(
        derPhase.length > 1
          ? `${derPhase.length} Entwürfe wurden als ZIP heruntergeladen. Entpacken, ` +
            "je Datei doppelklicken — Outlook öffnet sie als Entwurf mit " +
            "Empfänger und Text."
          : "Der Entwurf wurde heruntergeladen. Doppelklick öffnet ihn in Outlook."
      );
      onFertig();
    } catch (err) {
      setFehler(
        err instanceof Error ? err.message : "Erzeugen fehlgeschlagen."
      );
    } finally {
      setLaeuft("");
    }
  }

  const bereit =
    vorschau !== null && vorschau.length > 0 && vorschau.every((v) => v.bereit);

  return (
    <Karte>
      <KarteKopf
        titel="Subplaner beauftragen"
        icon={Send}
        unterzeile={
          standort.ordner_name
            ? `Standort ${standort.ordner_name}`
            : "Standort noch ohne Ordnernamen"
        }
      />
      <KarteInhalt className="flex flex-col gap-4">
        {fehler && <Meldung art="fehler">{fehler}</Meldung>}
        {meldung && <Meldung art="erfolg">{meldung}</Meldung>}

        {/* ── 1. Phase ── */}
        <div>
          <span className="font-mono text-[10.5px] tracking-[0.1em] uppercase text-app-text-leise">
            1 · Phase
          </span>
          <div className="mt-1.5">
            <ChipLeiste>
              {PHASEN.map((p) => {
                const anzahl = subplaner.filter((s) => s.phase === p).length;
                return (
                  <Chip key={p} aktiv={phase === p} onClick={() => setPhase(p)}>
                    Phase {p} ({anzahl})
                  </Chip>
                );
              })}
            </ChipLeiste>
          </div>
        </div>

        {derPhase.length === 0 ? (
          <Meldung art="hinweis">
            Für Phase {phase} sind keine Subplaner hinterlegt. Sie stehen unter
            „Stammdaten → Subplaner“ — dort lassen sich Firmen je Phase mit
            ihren E-Mail-Adressen pflegen.
          </Meldung>
        ) : (
          <>
            {ohneAdresse.length > 0 && (
              <Meldung art="hinweis">
                {ohneAdresse.map((s) => s.name).join(" und ")}{" "}
                {ohneAdresse.length === 1 ? "hat" : "haben"} noch keine
                E-Mail-Adresse. Sie {ohneAdresse.length === 1 ? "gehört" : "gehören"}{" "}
                in die Stammdaten unter „Subplaner“ — vorher lässt sich kein
                Entwurf erzeugen.
              </Meldung>
            )}

            {/* ── 2. Termine ── */}
            <div>
              <div className="flex items-center gap-1.5">
                <CalendarClock size={13} className="text-app-text-leise" />
                <span className="font-mono text-[10.5px] tracking-[0.1em] uppercase text-app-text-leise">
                  2 · Termine
                </span>
              </div>
              <p className="mt-0.5 text-[12px] text-app-text-still">
                Vorbelegt aus der SLS-Anfrage. „Klären der
                Aufgabenstellung/Bauordnungsrecht“ rechnet die App aus dem
                Beauftragungsdatum — leer lassen heißt: Vorschlag übernehmen.
              </p>
              <div className="mt-2 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <Field label="Beauftragung (steht im Betreff)">
                  <Input
                    type="date"
                    value={beauftragungAm}
                    onChange={(e) => setBeauftragungAm(e.target.value)}
                  />
                </Field>
                <Field label="Leistungsbeginn">
                  <Input
                    type="date"
                    value={beginn}
                    onChange={(e) => setBeginn(e.target.value)}
                  />
                </Field>
                <Field label="Abgabe Phase">
                  <Input
                    type="date"
                    value={abgabe}
                    onChange={(e) => setAbgabe(e.target.value)}
                  />
                </Field>
                <Field
                  label="Erstellung der Projektplanung"
                  hinweis="Nur in der Kocks-Fassung."
                >
                  <Input
                    type="date"
                    value={projektplanung}
                    onChange={(e) => setProjektplanung(e.target.value)}
                  />
                </Field>
                <Field
                  label="Klären Aufgabenstellung"
                  hinweis="Leer = Beauftragung + 3 Tage."
                >
                  <Input
                    type="date"
                    value={klaerung}
                    onChange={(e) => setKlaerung(e.target.value)}
                  />
                </Field>
              </div>
            </div>

            {/* ── 3. Vorschau ── */}
            <div>
              <div className="flex items-center gap-1.5">
                <Eye size={13} className="text-app-text-leise" />
                <span className="font-mono text-[10.5px] tracking-[0.1em] uppercase text-app-text-leise">
                  3 · Vorschau — so bekommt es der Subplaner
                </span>
                {laeuft === "vorschau" && (
                  <Loader2 size={13} className="animate-spin text-app-text-leise" />
                )}
              </div>

              <div className="mt-2 flex flex-col gap-3">
                {(vorschau ?? []).map((v) => (
                  <div
                    key={v.subplaner_id}
                    className="rounded-app-sm border border-app-linie bg-app-flaeche-still"
                  >
                    <div className="flex flex-wrap items-center gap-2 border-b border-app-linie px-3 py-2">
                      <Building2 size={13} className="shrink-0 text-app-text-leise" />
                      <span className="text-[12.5px] font-semibold text-app-text">
                        {v.subplaner_name}
                      </span>
                      {v.bereit ? (
                        <Plakette art="ok">bereit</Plakette>
                      ) : (
                        <Plakette art="gefahr">fehlt</Plakette>
                      )}
                      <span className="ml-auto truncate font-mono text-[11px] text-app-text-still">
                        {v.ablage}
                      </span>
                    </div>
                    <div className="flex flex-col gap-2 px-3 py-2.5">
                      {!v.bereit && (
                        <div className="inline-flex items-start gap-1.5 text-[12px] text-app-gefahr">
                          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                          {v.hindernis}
                        </div>
                      )}
                      <div className="text-[12px] text-app-text-still">
                        An: {v.empfaenger.join(", ") || "—"}
                      </div>
                      <div className="font-mono text-[12px] break-all text-app-text">
                        {v.betreff}
                      </div>
                      <pre className="max-h-64 overflow-auto rounded-app-sm border border-app-linie bg-app-flaeche p-2.5 text-[11.5px] leading-relaxed whitespace-pre-wrap text-app-text">
                        {v.text}
                      </pre>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* ── Aktionen ── */}
            <div className="flex flex-wrap gap-2 border-t border-app-linie pt-3">
              <Button
                onClick={erzeugen}
                disabled={laeuft !== "" || !bereit}
                icon={laeuft === "erzeugen" ? Loader2 : Download}
              >
                {laeuft === "erzeugen"
                  ? "Wird erzeugt…"
                  : derPhase.length > 1
                  ? `${derPhase.length} Entwürfe erzeugen`
                  : "Entwurf erzeugen"}
              </Button>
              <Button variante="still" icon={X} onClick={onAbbrechen}>
                Abbrechen
              </Button>
            </div>

            <p className="text-[12px] leading-relaxed text-app-text-still">
              Die Entwürfe werden heruntergeladen und zugleich im Ordner
              <span className="font-mono"> 02_Vertrag</span> der jeweiligen
              Firma abgelegt
              {faehigkeiten && !faehigkeiten.ordner_laufwerk
                ? " — sobald der Standortordner auf dem Projektlaufwerk angelegt ist. Von hier aus gibt es darauf keinen Zugriff, die Ablage steht dann noch aus."
                : "."}{" "}
              Abgeschickt werden sie von Outlook, nicht von der App.
            </p>
          </>
        )}
      </KarteInhalt>
    </Karte>
  );
}
