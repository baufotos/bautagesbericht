"use client";

/**
 * Bautagesbericht einreichen.
 *
 * Fachlich unverändert gegenüber der ersten Fassung der App: Man lädt die
 * Berichte der Firmen als PDF oder Foto hoch, das Backend liest sie aus, holt
 * die Wetterdaten zum Projektstandort und erzeugt das Word-Dokument.
 *
 * Neu ist nur die Darstellung — und eine Karte, die den Ablauf danach erklärt.
 * Das ist kein Beiwerk: Die Verarbeitung läuft im Hintergrund, und ohne diesen
 * Hinweis wartet man vor einem scheinbar untätigen Formular.
 */

import { ClipboardList, FileText, Info, Loader2, Upload, X } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { formatDatumIso, heuteIso, relativeZeit } from "@/lib/formate";
import type { Einreichung, Empfaenger, Projekt } from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  LeerHinweis,
  ListenZeile,
  Plakette,
} from "@/components/dashboard";
import { Button, Field, Meldung, Select, Textarea, Input } from "@/components/ui";
import { WocheEinreichen } from "@/components/bautagesberichte/WocheEinreichen";

const MAX_DATEIEN = 20;

/** Status-Plakette passend zum Verarbeitungsstand. */
export function BerichtStatus({ status }: { status: string }) {
  if (status === "abgeschlossen") return <Plakette art="ok">fertig</Plakette>;
  if (status === "fehlgeschlagen") return <Plakette art="gefahr">fehlgeschlagen</Plakette>;
  if (status === "wartet_auf_bestaetigung")
    return <Plakette art="warn">Prüfung nötig</Plakette>;
  return <Plakette art="info">{status.replace(/_/g, " ")}</Plakette>;
}

export function BerichtEinreichen({
  projekte,
  empfaenger,
  projektId,
  einreichungen,
  onEingereicht,
}: {
  projekte: Projekt[];
  empfaenger: Empfaenger[];
  /** Kommt aus der Kopfzeile — das Projekt gilt für die ganze App. */
  projektId: number | null;
  einreichungen: Einreichung[];
  onEingereicht: () => void;
}) {
  const [modus, setModus] = useState<"tag" | "woche">("tag");
  const [datum, setDatum] = useState(heuteIso());
  const [ergaenzendeAngaben, setErgaenzendeAngaben] = useState("");
  const [empfaengerId, setEmpfaengerId] = useState("");
  const [dateien, setDateien] = useState<File[]>([]);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [erfolg, setErfolg] = useState(false);

  const projekt = projekte.find((p) => p.id === projektId) ?? null;
  const gewaehlterEmpfaenger = empfaenger.find((e) => e.id === Number(empfaengerId));
  const kannEinreichen =
    projekt !== null && empfaengerId !== "" && datum !== "" && dateien.length > 0 && !laeuft;

  function dateienHinzufuegen(event: React.ChangeEvent<HTMLInputElement>) {
    const neue = Array.from(event.target.files || []);
    setDateien((alt) => [...alt, ...neue].slice(0, MAX_DATEIEN));
    event.target.value = "";
  }

  async function einreichen() {
    if (!kannEinreichen || projekt === null) return;
    setLaeuft(true);
    setFehler(null);
    try {
      const formular = new FormData();
      formular.append("projekt_id", String(projekt.id));
      formular.append("empfaenger_id", empfaengerId);
      formular.append("datum", datum);
      formular.append("ergaenzende_angaben", ergaenzendeAngaben);
      dateien.forEach((datei) => formular.append("dateien", datei));

      await api.einreichungen.submit(formular);
      setDateien([]);
      setErgaenzendeAngaben("");
      setErfolg(true);
      onEingereicht();
      // Die Erfolgsmeldung verschwindet von selbst — sie ist eine Bestätigung,
      // keine Aufgabe.
      setTimeout(() => setErfolg(false), 6000);
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Einreichen fehlgeschlagen.");
    } finally {
      setLaeuft(false);
    }
  }

  if (projekt === null) {
    return (
      <LeerHinweis>
        Für einen Bautagesbericht wird ein Projekt gebraucht. Bitte oben in der
        Kopfzeile ein Projekt wählen — oder unter „Stammdaten → Projekte“ eins
        anlegen.
      </LeerHinweis>
    );
  }

  const letzte = einreichungen
    .filter((e) => e.projekt_id === projekt.id)
    .slice(0, 5);

  /* Ein Tag oder eine ganze Woche. Beide Fassungen teilen sich Projekt,
     Empfängerliste und die Spalte rechts; der Rest ist verschieden genug,
     dass ein früher Ausstieg lesbarer bleibt als Bedingungen im Baum. */
  const umschalter = (
    <div className="flex gap-1.5 rounded-full border border-app-linie bg-app-flaeche p-1">
      {(
        [
          ["tag", "Einzelner Tag"],
          ["woche", "Ganze Woche"],
        ] as const
      ).map(([wert, beschriftung]) => (
        <button
          key={wert}
          type="button"
          onClick={() => setModus(wert)}
          aria-pressed={modus === wert}
          className={`flex-1 cursor-pointer rounded-full px-4 py-2 text-[13px] font-medium transition-colors ${
            modus === wert
              ? "bg-ui-accent text-ui-accent-text"
              : "text-app-text-still hover:text-app-text"
          }`}
        >
          {beschriftung}
        </button>
      ))}
    </div>
  );

  const zuletzt =
    letzte.length === 0 ? null : (
      <Karte>
        <KarteKopf titel="Zuletzt für dieses Projekt" menue />
        <div>
          {letzte.map((e) => (
            <ListenZeile
              key={e.id}
              titel={formatDatumIso(e.datum)}
              unterzeile={`${e.empfaenger_label} · eingereicht ${relativeZeit(
                e.eingereicht_am
              )}`}
              rechts={<BerichtStatus status={e.status} />}
            />
          ))}
        </div>
      </Karte>
    );

  if (modus === "woche") {
    return (
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <div className="flex flex-col gap-3 xl:col-span-2">
          {umschalter}
          <WocheEinreichen
            projekt={projekt}
            empfaenger={empfaenger}
            onEingereicht={onEingereicht}
          />
        </div>
        <div className="flex flex-col gap-3">{zuletzt}</div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
      <div className="flex flex-col gap-3 xl:col-span-2">
        {umschalter}
        <Karte>
          <KarteKopf
            titel="Bericht"
            unterzeile={projekt.name}
            icon={ClipboardList}
          />
          <KarteInhalt className="flex flex-col gap-4">
            {fehler && <Meldung art="fehler">{fehler}</Meldung>}
            {erfolg && (
              <Meldung art="erfolg">
                Eingereicht. Die Verarbeitung läuft im Hintergrund — den fertigen
                Bericht findest du danach unter „Bautagesberichte → Übersicht“.
              </Meldung>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Datum">
                <Input
                  type="date"
                  value={datum}
                  onChange={(e) => setDatum(e.target.value)}
                />
              </Field>
              <Field
                label="Empfänger"
                hinweis={
                  empfaenger.length === 0
                    ? "Noch keine Empfänger hinterlegt — unter „Stammdaten → Empfänger“ anlegen."
                    : gewaehlterEmpfaenger?.teams_webhook_url
                    ? "Wird zusätzlich per Teams gemeldet."
                    : undefined
                }
              >
                <Select
                  value={empfaengerId}
                  onChange={(e) => setEmpfaengerId(e.target.value)}
                >
                  <option value="">— Empfänger wählen —</option>
                  {empfaenger.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.label} ({e.email})
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            <div>
              <label
                htmlFor="btb-dateien"
                className="flex cursor-pointer items-center justify-center gap-2 rounded-app-sm border border-dashed border-app-akzent px-3.5 py-5 text-[13px] text-app-akzent transition-colors hover:bg-app-akzent-sanft"
              >
                <Upload size={16} /> Berichte der Unternehmen hochladen (PDF oder
                Foto, mehrere möglich)
              </label>
              <input
                id="btb-dateien"
                type="file"
                multiple
                accept=".pdf,image/*,.heic,.heif,.avif,.tif,.tiff"
                className="hidden"
                onChange={dateienHinzufuegen}
              />

              {dateien.length > 0 && (
                <div className="mt-2 flex flex-col gap-1.5">
                  {dateien.map((datei, i) => (
                    <div
                      key={`${datei.name}-${i}`}
                      className="flex items-center justify-between gap-2 rounded-app-sm border border-app-linie px-2.5 py-2 text-[12.5px]"
                    >
                      <span className="flex min-w-0 items-center gap-1.5">
                        <FileText size={14} className="shrink-0 text-app-text-still" />
                        <span className="truncate">{datei.name}</span>
                      </span>
                      <button
                        type="button"
                        onClick={() =>
                          setDateien((alt) => alt.filter((_, j) => j !== i))
                        }
                        aria-label={`${datei.name} entfernen`}
                        className="shrink-0 cursor-pointer text-app-text-leise transition-colors hover:text-app-gefahr"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <Field
              label="Ergänzende Angaben"
              hinweis="Landen als Haupteintrag im Bericht."
            >
              <Textarea
                value={ergaenzendeAngaben}
                onChange={(e) => setErgaenzendeAngaben(e.target.value)}
                placeholder="Zusätzliche Hinweise zum Tag…"
              />
            </Field>

            <div className="flex flex-wrap items-center gap-2 border-t border-app-linie pt-3">
              <Button
                onClick={einreichen}
                disabled={!kannEinreichen}
                icon={laeuft ? undefined : ClipboardList}
              >
                {laeuft ? (
                  <>
                    <Loader2 size={15} className="animate-spin" /> Wird eingereicht…
                  </>
                ) : (
                  "Einreichen"
                )}
              </Button>
              {!kannEinreichen && !laeuft && (
                <span className="text-[12px] text-app-text-still">
                  Empfänger und mindestens eine Datei werden gebraucht.
                </span>
              )}
            </div>
          </KarteInhalt>
        </Karte>

        {zuletzt}
      </div>

      {/* Ablauf-Erklärung: Die Verarbeitung passiert unsichtbar im Hintergrund. */}
      <div>
        <Karte>
          <KarteKopf titel="Was danach passiert" icon={Info} />
          <KarteInhalt>
            <ol className="flex flex-col gap-3">
              {[
                [
                  "Berichte auslesen",
                  "Aus den hochgeladenen PDF oder Fotos werden Firma, Personenzahl und Leistung übernommen.",
                ],
                [
                  "Wetter holen",
                  `Zum Standort ${
                    projekt.adresse || "des Projekts"
                  } werden die Wetterdaten des Tages abgerufen.`,
                ],
                [
                  "Word erzeugen",
                  "Der Bericht entsteht in der HPP-Vorlage und steht in der Übersicht zum Download.",
                ],
              ].map(([titel, text], i) => (
                <li key={titel} className="flex gap-2.5">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-app-akzent-sanft text-[11px] font-semibold text-app-akzent">
                    {i + 1}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[12.5px] font-medium text-app-text">
                      {titel}
                    </span>
                    <span className="block text-[12px] leading-relaxed text-app-text-still">
                      {text}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
            <p className="mt-3 border-t border-app-linie pt-3 text-[12px] leading-relaxed text-app-text-still">
              Gibt es beim Auslesen Unklarheiten, wartet der Bericht auf eine
              Bestätigung — er erscheint dann in der Übersicht mit dem Vermerk
              „Prüfung nötig“.
            </p>
          </KarteInhalt>
        </Karte>
      </div>
    </div>
  );
}
