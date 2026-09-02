"use client";

/**
 * Eine ganze Woche auf einmal einreichen.
 *
 * WARUM ZWEI SCHRITTE
 * ===================
 * Erst hochladen und ansehen, dann erzeugen. Das klingt nach einem Schritt zu
 * viel, ist aber genau der, auf den es ankommt: Zwischen „Datum: 05.08.2026"
 * im Kopf eines Firmenberichts und „Fertigstellung bis 30.11.2026" im
 * Fließtext kann eine Maschine sich irren, und ein vertauschter Tag fällt
 * beim Durchsehen der fertigen Berichte kaum auf. Deshalb zeigt Schritt 1, was
 * erkannt wurde, und lässt es sich in einem Feld korrigieren.
 *
 * Hochgeladen wird trotzdem nur einmal — die Dateien bleiben zwischen den
 * Schritten auf dem Server liegen (``kennung``).
 */

import {
  AlertTriangle,
  CalendarDays,
  CheckCircle2,
  Download,
  FileText,
  Layers,
  Trash2,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { dateiSpeichern } from "@/lib/dateien";
import { formatDatumIso } from "@/lib/formate";
import type {
  Einreichung,
  EinreichungFaehigkeiten,
  Empfaenger,
  Projekt,
  WochenAnalyse,
  WochenTag,
} from "@/lib/types";
import { Karte, KarteInhalt, KarteKopf, LeerHinweis } from "@/components/dashboard";
import { Button, Field, Input, Meldung, Select } from "@/components/ui";

const MAX_DATEIEN = 20;

const WOCHENTAGE = [
  "Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag",
];

/** "Mittwoch, 05.08.2026" — aus einem ISO-Datum, ohne Zeitzonen-Überraschung. */
function langesDatum(iso: string | null): string {
  if (!iso) return "";
  const [jahr, monat, tag] = iso.split("-").map(Number);
  if (!jahr || !monat || !tag) return iso;
  const wochentag = WOCHENTAGE[new Date(jahr, monat - 1, tag).getDay()];
  return `${wochentag}, ${formatDatumIso(iso)}`;
}

/** Der Montag der Woche, in der ``iso`` liegt. */
function montagVon(iso: string): string {
  const [jahr, monat, tag] = iso.split("-").map(Number);
  const d = new Date(jahr, monat - 1, tag);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  const z = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}

function heuteMontag(): string {
  const jetzt = new Date();
  const z = (n: number) => String(n).padStart(2, "0");
  return montagVon(
    `${jetzt.getFullYear()}-${z(jetzt.getMonth() + 1)}-${z(jetzt.getDate())}`
  );
}

/** ``tage`` Tage nach ``iso``. */
function plusTage(iso: string, tage: number): string {
  const [jahr, monat, tag] = iso.split("-").map(Number);
  const d = new Date(jahr, monat - 1, tag);
  d.setDate(d.getDate() + tage);
  const z = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
}

/** Anzahl Tage von ``von`` bis ``bis``, beide eingeschlossen. */
function tageImZeitraum(von: string, bis: string): number {
  if (!von || !bis) return 0;
  const zahl = (iso: string) => {
    const [j, m, t] = iso.split("-").map(Number);
    return new Date(j, m - 1, t).getTime();
  };
  return Math.round((zahl(bis) - zahl(von)) / 86400000) + 1;
}

export function WocheEinreichen({
  projekt,
  empfaenger,
  onEingereicht,
}: {
  projekt: Projekt;
  empfaenger: Empfaenger[];
  onEingereicht: () => void;
}) {
  const [von, setVon] = useState(heuteMontag());
  const [bis, setBis] = useState(() => plusTage(heuteMontag(), 1));
  const [koennen, setKoennen] = useState<EinreichungFaehigkeiten | null>(null);
  const [empfaengerId, setEmpfaengerId] = useState("");
  const [dateien, setDateien] = useState<File[]>([]);
  const [analyse, setAnalyse] = useState<WochenAnalyse | null>(null);
  const [tage, setTage] = useState<WochenTag[]>([]);
  const [ergebnis, setErgebnis] = useState<Einreichung[] | null>(null);
  const [laeuft, setLaeuft] = useState<"" | "lesen" | "erzeugen" | "zip">("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [hinweise, setHinweise] = useState<string[]>([]);

  const bereiteTage = useMemo(
    () => tage.filter((t) => t.datum && t.quellen.length > 0),
    [tage]
  );
  const doppelt = useMemo(() => {
    const gesehen = new Set<string>();
    const mehrfach = new Set<string>();
    bereiteTage.forEach((t) => {
      if (t.datum && gesehen.has(t.datum)) mehrfach.add(t.datum);
      if (t.datum) gesehen.add(t.datum);
    });
    return mehrfach;
  }, [bereiteTage]);

  // Einmal beim Öffnen fragen, ob dieser Rechner Fotos und Handschrift lesen
  // kann. Der Hinweis gehört an den Upload und nicht in den fertigen Bericht.
  useEffect(() => {
    let abgebrochen = false;
    api.einreichungen
      .faehigkeiten()
      .then((k) => {
        if (!abgebrochen) setKoennen(k);
      })
      .catch(() => {
        /* Nur ein Hinweis — ohne ihn funktioniert alles weiter. */
      });
    return () => {
      abgebrochen = true;
    };
  }, []);

  // Welche Endungen als Bild gelten, muss zu dem passen, was die Auswahl
  // oben zulässt — sonst bleibt der Hinweis zur Handschrift ausgerechnet bei
  // einem iPhone-Foto (HEIC) oder einem neueren Android-Foto (WEBP) aus.
  const hatBilder = dateien.some(
    (d) =>
      d.type.startsWith("image/") ||
      /\.(jpe?g|png|tiff?|bmp|gif|webp|heic|heif|avif)$/i.test(d.name)
  );
  const anzahlTage = tageImZeitraum(von, bis);
  const zeitraumFalsch = anzahlTage <= 0;

  function meldeFehler(err: unknown, standard: string) {
    if (err instanceof ApiError && typeof err.detail === "string") setFehler(err.detail);
    else setFehler(err instanceof Error ? err.message : standard);
  }

  function zuruecksetzen() {
    setAnalyse(null);
    setTage([]);
    setErgebnis(null);
    setHinweise([]);
  }

  function dateienHinzufuegen(event: React.ChangeEvent<HTMLInputElement>) {
    const neue = Array.from(event.target.files || []);
    setDateien((alt) => [...alt, ...neue].slice(0, MAX_DATEIEN));
    event.target.value = "";
    zuruecksetzen();
  }

  async function einlesen() {
    if (dateien.length === 0 || zeitraumFalsch) return;
    setLaeuft("lesen");
    setFehler(null);
    try {
      // Das Projekt gehört mit in die Anfrage: Der Server nimmt dann die
      // Firmen dieser Baustelle als Lesehilfe. Bei handschriftlichen
      // Berichten entscheidet das darüber, ob aus einer krakeligen Schleife
      // „Riedel Bau“ wird oder eine vierte Schreibweise.
      const gelesen = await api.einreichungen.wocheAnalysieren(
        dateien, von, bis, projekt.id
      );
      setAnalyse(gelesen);
      setHinweise(gelesen.hinweise);
      // Seiten ohne erkanntes Datum kommen als eigene Zeile mit leerem Datum
      // dazu — sichtbar, aber ohne Vorschlag. Raten wäre hier schlimmer.
      setTage([
        ...gelesen.tage,
        ...(gelesen.ohne_datum ? [gelesen.ohne_datum] : []),
      ]);
      setErgebnis(null);
    } catch (err) {
      meldeFehler(err, "Die Dateien konnten nicht gelesen werden.");
    } finally {
      setLaeuft("");
    }
  }

  async function erzeugen() {
    if (!analyse || bereiteTage.length === 0 || empfaengerId === "") return;
    setLaeuft("erzeugen");
    setFehler(null);
    try {
      const antwort = await api.einreichungen.wocheErzeugen({
        kennung: analyse.kennung,
        projekt_id: projekt.id,
        empfaenger_id: Number(empfaengerId),
        tage: bereiteTage,
      });
      setErgebnis(antwort.einreichungen);
      setHinweise(antwort.hinweise);
      setAnalyse(null);
      setTage([]);
      setDateien([]);
      onEingereicht();
    } catch (err) {
      meldeFehler(err, "Die Berichte konnten nicht erzeugt werden.");
    } finally {
      setLaeuft("");
    }
  }

  async function alleAlsZip() {
    if (!ergebnis) return;
    setLaeuft("zip");
    setFehler(null);
    try {
      const { blob, dateiname } = await api.einreichungen.dokumenteAlsZip(
        ergebnis.map((e) => e.id)
      );
      dateiSpeichern(blob, dateiname || "Bautagesberichte.zip");
    } catch (err) {
      meldeFehler(err, "Das Archiv ist noch nicht verfügbar.");
    } finally {
      setLaeuft("");
    }
  }

  function setzeTag(index: number, aenderung: Partial<WochenTag>) {
    setTage((alt) =>
      alt.map((t, i) => (i === index ? { ...t, ...aenderung } : t))
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {/* ─── Schritt 1: Paket wählen ─── */}
      <Karte>
        <KarteKopf
          titel="Ganze Woche einreichen"
          unterzeile={projekt.name}
          icon={Layers}
        />
        <KarteInhalt className="flex flex-col gap-4">
          <p className="text-[12.5px] leading-relaxed text-app-text-still">
            Die Berichte der Firmen für den ganzen Zeitraum hochladen — auch als
            ein einziges Dokument, egal ob eine Seite je Tag oder mehrere Tage
            auf einem Blatt. Die App sucht die Daten heraus, trennt die Tage und
            legt für jeden einen eigenen Bautagesbericht an, mit eigenen
            Wetterdaten.
          </p>

          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Zeitraum von">
              <Input
                type="date"
                value={von}
                onChange={(e) => {
                  const neu = e.target.value;
                  setVon(neu);
                  // Das Ende springt auf den Folgetag. So steht im zweiten
                  // Feld schon ein sinnvoller Wert und sein Kalender öffnet
                  // im richtigen Monat — man muss nur noch weiterklicken,
                  // statt sich von heute dorthin zu blättern.
                  if (neu) setBis(plusTage(neu, 1));
                  zuruecksetzen();
                }}
              />
            </Field>
            <Field
              label="bis"
              hinweis={
                zeitraumFalsch
                  ? undefined
                  : `${anzahlTage} Tag(e)`
              }
              fehler={
                zeitraumFalsch
                  ? "Das Enddatum muss auf oder nach dem Startdatum liegen."
                  : undefined
              }
            >
              <Input
                type="date"
                value={bis}
                min={von || undefined}
                onChange={(e) => {
                  setBis(e.target.value);
                  zuruecksetzen();
                }}
              />
            </Field>
            <Field
              label="Empfänger"
              hinweis={
                empfaenger.length === 0
                  ? "Noch keine Empfänger hinterlegt — unter „Stammdaten → Empfänger“ anlegen."
                  : "Gilt für alle Tage der Woche."
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
              htmlFor="woche-dateien"
              className="flex cursor-pointer items-center justify-center gap-2 rounded-app-sm border border-dashed border-app-akzent px-3.5 py-5 text-[13px] text-app-akzent transition-colors hover:bg-app-akzent-sanft"
            >
              <Upload size={16} /> Berichte der Woche hochladen (PDF oder Foto,
              mehrere möglich)
            </label>
            <input
              id="woche-dateien"
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
                      onClick={() => {
                        setDateien((alt) => alt.filter((_, j) => j !== i));
                        zuruecksetzen();
                      }}
                      aria-label={`${datei.name} entfernen`}
                      className="shrink-0 cursor-pointer text-app-text-leise transition-colors hover:text-app-gefahr"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Der Hinweis zur Handschrift gehört hierhin und nicht in den
              fertigen Bericht: Ohne Anthropic-Schlüssel bleibt ein Foto
              zwangsläufig leer, und das soll man vor dem Erzeugen wissen. */}
          {hatBilder && koennen && (
            <Meldung art={koennen.handschrift ? "hinweis" : "fehler"}>
              <span className="flex items-start gap-2">
                <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                <span>{koennen.hinweis}</span>
              </span>
            </Meldung>
          )}

          {dateien.length > 0 && !analyse && (
            <div>
              <Button
                icon={CalendarDays}
                onClick={einlesen}
                disabled={laeuft !== "" || zeitraumFalsch}
              >
                {laeuft === "lesen" ? "Wird gelesen…" : "Tage erkennen"}
              </Button>
            </div>
          )}
        </KarteInhalt>
      </Karte>

      {/* ─── Schritt 2: erkannte Tage prüfen ─── */}
      {analyse && (
        <Karte hervorgehoben>
          <KarteKopf
            titel="Erkannte Tage"
            unterzeile="Bitte kurz prüfen — hier wird entschieden, welche Arbeit in welchen Bericht kommt"
            icon={CalendarDays}
          />
          <KarteInhalt className="flex flex-col gap-3">
            {hinweise.map((h, i) => (
              <p key={i} className="text-[12.5px] text-app-text-still">
                {h}
              </p>
            ))}

            {tage.length === 0 ? (
              <LeerHinweis>
                In den Dateien wurde kein Tag gefunden. Bitte prüfen, ob die
                Berichte ein Datum enthalten — bei Scans ohne Textebene ist das
                nicht lesbar.
              </LeerHinweis>
            ) : (
              <div className="flex flex-col gap-2">
                {tage.map((tag, i) => {
                  const istDoppelt = tag.datum !== null && doppelt.has(tag.datum);
                  const fehltDatum = !tag.datum;
                  return (
                    <div
                      key={i}
                      className={`rounded-app-sm border p-3 ${
                        fehltDatum || istDoppelt
                          ? "border-app-warn bg-app-warn-sanft"
                          : "border-app-linie"
                      }`}
                    >
                      <div className="flex flex-wrap items-start gap-3">
                        <div className="w-full sm:w-48">
                          <Field label={fehltDatum ? "Tag zuordnen" : "Tag"}>
                            <Input
                              type="date"
                              value={tag.datum ?? ""}
                              onChange={(e) =>
                                setzeTag(i, { datum: e.target.value || null })
                              }
                            />
                          </Field>
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-app-text-still">
                            Quellen
                          </div>
                          <div className="mt-1.5 flex flex-col gap-0.5 text-[12px] text-app-text-still">
                            {tag.quellen.map((q) => (
                              <span key={q.datei} className="truncate">
                                {q.datei}
                                {q.seiten.length > 0 && (
                                  <span className="text-app-text-leise">
                                    {" "}
                                    · Seite {q.seiten.join(", ")}
                                  </span>
                                )}
                              </span>
                            ))}
                          </div>
                          {tag.datum && (
                            <div className="mt-1 text-[12px] text-app-text">
                              {langesDatum(tag.datum)}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Einzeilig: Bei fünf Tagen untereinander entscheidet
                          die Höhe darüber, ob man die Woche noch auf einen
                          Blick prüfen kann. Der Haupteintrag ist ohnehin
                          meist ein Satz. */}
                      <div className="mt-2">
                        <Field label="Ergänzung für diesen Tag">
                          <Input
                            value={tag.ergaenzende_angaben}
                            placeholder="optional — z. B. Kranmontage, Begehung, Behinderung"
                            onChange={(e) =>
                              setzeTag(i, { ergaenzende_angaben: e.target.value })
                            }
                          />
                        </Field>
                      </div>

                      {fehltDatum && (
                        <p className="mt-1.5 flex items-start gap-1.5 text-[12px] text-app-warn">
                          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                          Ohne Tag wird daraus kein Bericht. Bitte das Datum
                          eintragen oder die Zeile ignorieren.
                        </p>
                      )}
                      {istDoppelt && (
                        <p className="mt-1.5 flex items-start gap-1.5 text-[12px] text-app-warn">
                          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                          Dieser Tag kommt mehrfach vor — pro Tag entsteht nur
                          ein Bericht.
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2 border-t border-app-linie pt-3">
              <Button
                icon={FileText}
                onClick={erzeugen}
                disabled={
                  laeuft !== "" ||
                  bereiteTage.length === 0 ||
                  doppelt.size > 0 ||
                  empfaengerId === ""
                }
              >
                {laeuft === "erzeugen"
                  ? "Wird erzeugt…"
                  : `${bereiteTage.length} Bericht(e) erzeugen`}
              </Button>
              <Button variante="still" onClick={zuruecksetzen} disabled={laeuft !== ""}>
                Verwerfen
              </Button>
              {empfaengerId === "" && (
                <span className="text-[12px] text-app-warn">
                  Bitte oben einen Empfänger wählen.
                </span>
              )}
            </div>
          </KarteInhalt>
        </Karte>
      )}

      {/* ─── Schritt 3: Ergebnis ─── */}
      {ergebnis && ergebnis.length > 0 && (
        <Karte>
          <KarteKopf
            titel="Angelegt"
            unterzeile="Die Verarbeitung läuft im Hintergrund"
            icon={CheckCircle2}
          />
          <KarteInhalt className="flex flex-col gap-3">
            {hinweise.map((h, i) => (
              <p key={i} className="text-[12.5px] text-app-text-still">
                {h}
              </p>
            ))}
            <div className="flex flex-col gap-1">
              {ergebnis.map((e) => (
                <div
                  key={e.id}
                  className="flex items-center justify-between gap-2 rounded-app-sm border border-app-linie px-2.5 py-2 text-[12.5px]"
                >
                  <span>{langesDatum(e.datum)}</span>
                  <a
                    href={api.einreichungen.downloadUrl(e.id)}
                    className="shrink-0 text-app-akzent underline"
                  >
                    Word
                  </a>
                </div>
              ))}
            </div>
            <div>
              <Button
                variante="sekundaer"
                icon={Download}
                onClick={alleAlsZip}
                disabled={laeuft !== ""}
              >
                {laeuft === "zip" ? "Wird gepackt…" : "Alle als ZIP"}
              </Button>
              <p className="mt-1.5 text-[12px] text-app-text-leise">
                Das Archiv enthält nur bereits fertige Berichte. Wenn ein Tag
                noch verarbeitet wird, kurz warten und erneut tippen.
              </p>
            </div>
          </KarteInhalt>
        </Karte>
      )}
    </div>
  );
}
