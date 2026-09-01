"use client";

/**
 * Detailansicht und Bearbeitung eines Mangels.
 *
 * Aufbau wie in der Bürosoftware: Kopfzeile mit Funktionen, darunter die
 * einklappbaren Abschnitte Status, Text, Termine, Mail, Fotos, Markierung,
 * Rückmeldung, Dateien.
 *
 * Speicherverhalten: Die Textfelder werden in einem Entwurf gesammelt und mit
 * einem Klick gespeichert — auf einer wackeligen Verbindung ist ein Aufruf
 * mit allen Änderungen deutlich zuverlässiger als ein Aufruf pro Tastendruck.
 * Fotos, Anhänge und Plan-Markierung haben eigene Endpunkte und werden sofort
 * wirksam; das ist auch so gemeint, denn dort geht es um Dateien, die man
 * nicht "halb" speichern will.
 *
 * Sichtbarkeit: Was mit einem Schloss-Symbol markiert ist, geht nie an eine
 * Firma. Diese Trennung ist im Backend abgesichert (der Export übernimmt die
 * interne Bemerkung nur in die interne Fassung), hier wird sie sichtbar
 * gemacht.
 */

import {
  AlertTriangle,
  ArrowLeft,
  CalendarClock,
  Copy,
  FileText,
  Files,
  Image as ImageIcon,
  Lock,
  Loader2,
  Mail,
  MapPin,
  MessageSquareReply,
  Paperclip,
  Send,
  SlidersHorizontal,
  Trash2,
  Undo2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import type {
  Gewerk,
  Mangel,
  MangelStammdaten,
  MangelUpdateInput,
  Prioritaet,
  ProjektPlan,
} from "@/lib/types";
import {
  Bereichstitel,
  Button,
  Card,
  Checkbox,
  EmptyState,
  Field,
  Input,
  Label,
  LinkButton,
  Meldung,
  ReadOnlyField,
  Section,
  Select,
  StatusBadge,
  Textarea,
  formatDatum,
  formatDatumKurz,
} from "@/components/ui";
import { FotoGalerie } from "./FotoAufnahme";
import { PlanMarkierungFeld, type MarkierungsWert } from "./PlanMarkierung";

/** Felder, die über den Entwurf bearbeitet werden. */
type Entwurf = Pick<
  Mangel,
  | "typ"
  | "status"
  | "gewerk_id"
  | "raumnummer"
  | "hinweis_ort"
  | "prioritaet"
  | "kurzbezeichnung"
  | "beschreibung"
  | "farbmarkierung"
  | "interne_bemerkung"
  | "erstellt_am"
  | "erste_frist_bis"
  | "aufgenommen_von"
  | "zustaendiger_user_id"
  | "erste_nachfrist_gesetzt_am"
  | "erste_nachfrist_bis"
  | "anmerkung_nachfrist"
  | "beseitigungsanzeige_am"
  | "freigemeldet_am"
  | "erledigt_am"
  | "zurueckweisung_am"
  | "rueckmeldung_status"
  | "mail_autosend"
  | "mail_versendemodus"
>;

const ENTWURF_FELDER: (keyof Entwurf)[] = [
  "typ",
  "status",
  "gewerk_id",
  "raumnummer",
  "hinweis_ort",
  "prioritaet",
  "kurzbezeichnung",
  "beschreibung",
  "farbmarkierung",
  "interne_bemerkung",
  "erstellt_am",
  "erste_frist_bis",
  "aufgenommen_von",
  "zustaendiger_user_id",
  "erste_nachfrist_gesetzt_am",
  "erste_nachfrist_bis",
  "anmerkung_nachfrist",
  "beseitigungsanzeige_am",
  "freigemeldet_am",
  "erledigt_am",
  "zurueckweisung_am",
  "rueckmeldung_status",
  "mail_autosend",
  "mail_versendemodus",
];

function entwurfAus(mangel: Mangel): Entwurf {
  const werte = {} as Entwurf;
  for (const feld of ENTWURF_FELDER) {
    // Der Entwurf spiegelt genau die bearbeitbaren Felder des Mangels.
    (werte as Record<string, unknown>)[feld] = mangel[feld];
  }
  return werte;
}

export function MangelDetail({
  mangel,
  gewerke,
  plaene,
  stammdaten,
  hinweis,
  onZurueck,
  onAktualisiert,
  onGeloescht,
  onDupliziert,
  onOeffnen,
}: {
  mangel: Mangel;
  gewerke: Gewerk[];
  plaene: ProjektPlan[];
  stammdaten: MangelStammdaten | null;
  /** Meldung aus dem Erfassungsschritt (z. B. Foto nicht übertragen). */
  hinweis?: string;
  onZurueck: () => void;
  onAktualisiert: () => void;
  onGeloescht: () => void;
  onDupliziert: (neueId: number) => void;
  onOeffnen: (id: number) => void;
}) {
  const [entwurf, setEntwurf] = useState<Entwurf>(() => entwurfAus(mangel));
  const [speichert, setSpeichert] = useState(false);
  const [aktion, setAktion] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [erfolg, setErfolg] = useState<string | null>(null);
  const anhangRef = useRef<HTMLInputElement>(null);

  // Beim Wechsel auf einen anderen Mangel (oder nach dem Neuladen) den
  // Entwurf zurücksetzen.
  useEffect(() => {
    setEntwurf(entwurfAus(mangel));
    setFehler(null);
    setErfolg(null);
  }, [mangel]);

  const aenderungen = useMemo(() => {
    const diff: MangelUpdateInput = {};
    for (const feld of ENTWURF_FELDER) {
      if (entwurf[feld] !== mangel[feld]) {
        (diff as Record<string, unknown>)[feld] = entwurf[feld];
      }
    }
    return diff;
  }, [entwurf, mangel]);
  const hatAenderungen = Object.keys(aenderungen).length > 0;

  function setzeFeld<K extends keyof Entwurf>(feld: K, wert: Entwurf[K]) {
    setEntwurf((alt) => ({ ...alt, [feld]: wert }));
  }

  async function speichern() {
    if (!hatAenderungen) return;
    setSpeichert(true);
    setFehler(null);
    try {
      await api.maengel.update(mangel.id, aenderungen);
      setErfolg("Änderungen gespeichert.");
      onAktualisiert();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Speichern fehlgeschlagen");
    } finally {
      setSpeichert(false);
    }
  }

  async function fuehreAus(name: string, arbeit: () => Promise<void>) {
    setAktion(name);
    setFehler(null);
    try {
      await arbeit();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Aktion fehlgeschlagen");
    } finally {
      setAktion(null);
    }
  }

  const gewaehltesGewerk = gewerke.find((g) => g.id === entwurf.gewerk_id);
  const mailFehler =
    mangel.mail_fehler ||
    (entwurf.gewerk_id === null
      ? "Fehler! Kein zuständiges Gewerk / keine Firma gewählt"
      : gewaehltesGewerk && !gewaehltesGewerk.email
      ? "Fehler! Firma/Büro hat keine Email-Adresse"
      : null);

  return (
    <div className="flex flex-col gap-4 pb-24">
      {/* ───── Kopf ───── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Button variante="still" icon={ArrowLeft} onClick={onZurueck}>
            Zurück zur Übersicht
          </Button>
          <div className="mt-2 flex flex-wrap items-baseline gap-3">
            <h2 className="text-[22px] font-semibold tracking-tight text-ui-text">
              {mangel.nummer} {mangel.kurzbezeichnung}
            </h2>
            <StatusBadge text={mangel.status} farbe={mangel.status_farbe} />
            {mangel.ist_ueberfaellig && (
              <span className="inline-flex items-center gap-1 text-[13px] font-semibold text-ui-danger">
                <AlertTriangle size={14} /> Frist überschritten
              </span>
            )}
          </div>
          <div className="mt-1 text-[13px] text-ui-text-muted">
            {mangel.projekt_name}
            {mangel.gewerk_anzeige ? ` · ${mangel.gewerk_anzeige}` : ""}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            variante="sekundaer"
            icon={Copy}
            disabled={aktion !== null}
            onClick={() =>
              fuehreAus("duplizieren", async () => {
                const kopie = await api.maengel.duplizieren(mangel.id);
                onDupliziert(kopie.id);
              })
            }
          >
            {aktion === "duplizieren" ? "Wird erstellt…" : "Duplikat NU erstellen"}
          </Button>
          <LinkButton
            href={api.maengel.exportUrl({
              projekt_id: mangel.projekt_id,
              gewerk_id: mangel.gewerk_id ?? undefined,
              intern: false,
            })}
            target="_blank"
            rel="noopener noreferrer"
            icon={FileText}
            title="Mängelliste dieser Firma als Word-Dokument"
          >
            Mängelliste
          </LinkButton>
          <Button
            variante="gefahr"
            icon={Trash2}
            disabled={aktion !== null}
            onClick={() =>
              fuehreAus("loeschen", async () => {
                if (
                  !window.confirm(
                    `Mangel ${mangel.nummer} „${mangel.kurzbezeichnung}“ mit allen ` +
                      "Fotos und Anhängen endgültig löschen?"
                  )
                ) {
                  return;
                }
                await api.maengel.delete(mangel.id);
                onGeloescht();
              })
            }
          >
            Löschen
          </Button>
        </div>
      </div>

      {mangel.eltern_mangel_id !== null && mangel.eltern_nummer && (
        <Card className="px-4 py-2.5">
          <button
            type="button"
            onClick={() => onOeffnen(mangel.eltern_mangel_id as number)}
            className="inline-flex cursor-pointer items-center gap-2 text-[13px] text-ui-accent hover:underline"
          >
            <Copy size={13} />
            Ist Kopie von: {mangel.eltern_nummer} {mangel.eltern_kurzbezeichnung}
          </button>
        </Card>
      )}

      {mangel.anzahl_duplikate > 0 && (
        <div className="text-[12.5px] text-ui-text-muted">
          Von diesem Mangel gibt es {mangel.anzahl_duplikate} Duplikat(e) für
          weitere Nachunternehmer.
        </div>
      )}

      {hinweis && <Meldung art="hinweis">{hinweis}</Meldung>}
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}
      {erfolg && <Meldung art="erfolg">{erfolg}</Meldung>}

      {/* ───── Status ───── */}
      <Section titel="Status" icon={SlidersHorizontal}>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Typ">
            <Select
              value={entwurf.typ}
              onChange={(e) => setzeFeld("typ", e.target.value)}
            >
              {(stammdaten?.typen || []).map((t) => (
                <option key={t.id} value={t.bezeichnung}>
                  {t.sortierung} {t.bezeichnung}
                </option>
              ))}
              {!(stammdaten?.typen || []).some(
                (t) => t.bezeichnung === entwurf.typ
              ) && <option value={entwurf.typ}>{entwurf.typ}</option>}
            </Select>
          </Field>
          <Field label="Status">
            <Select
              value={entwurf.status}
              onChange={(e) => setzeFeld("status", e.target.value)}
            >
              {(stammdaten?.status || []).map((s) => (
                <option key={s.id} value={s.bezeichnung}>
                  {s.sortierung} {s.bezeichnung}
                </option>
              ))}
              {!(stammdaten?.status || []).some(
                (s) => s.bezeichnung === entwurf.status
              ) && <option value={entwurf.status}>{entwurf.status}</option>}
            </Select>
          </Field>
          <Field label="Nummer" hinweis="Wird fortlaufend je Projekt vergeben.">
            <Input value={mangel.nummer} disabled />
          </Field>
        </div>

        <div className="mt-4">
          <Field label="Zuständige Firma / Büro">
            <Select
              value={entwurf.gewerk_id ?? ""}
              onChange={(e) =>
                setzeFeld("gewerk_id", e.target.value ? Number(e.target.value) : null)
              }
            >
              <option value="">— keine Firma —</option>
              {gewerke.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.anzeige_name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <Field label="Raumnummer">
            <Input
              value={entwurf.raumnummer ?? ""}
              onChange={(e) => setzeFeld("raumnummer", e.target.value || null)}
              placeholder="z. B. E.014"
            />
          </Field>
          <Field label="Hinweis Ort">
            <Input
              value={entwurf.hinweis_ort}
              onChange={(e) => setzeFeld("hinweis_ort", e.target.value)}
              placeholder="z. B. EG"
            />
          </Field>
          <Field label="Priorität">
            <Select
              value={entwurf.prioritaet}
              onChange={(e) =>
                setzeFeld("prioritaet", e.target.value as Prioritaet)
              }
            >
              {(stammdaten?.prioritaeten || ["hoch", "mittel", "niedrig"]).map(
                (p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                )
              )}
            </Select>
          </Field>
        </div>
      </Section>

      {/* ───── Text ───── */}
      <Section titel="Text" icon={FileText} zusatz={mangel.kurzbezeichnung}>
        <div className="flex flex-col gap-4">
          <Field label="Kurzbezeichnung">
            <Input
              value={entwurf.kurzbezeichnung}
              onChange={(e) => setzeFeld("kurzbezeichnung", e.target.value)}
            />
          </Field>
          <Field
            label="Beschreibung"
            hinweis="Geht in die Mängelrüge ein — so genau, dass die Firma die Stelle ohne Rückfrage findet."
          >
            <Textarea
              value={entwurf.beschreibung}
              onChange={(e) => setzeFeld("beschreibung", e.target.value)}
            />
          </Field>
          <Field label="Farbmarkierung">
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={entwurf.farbmarkierung || "#B45309"}
                onChange={(e) => setzeFeld("farbmarkierung", e.target.value)}
                className="size-9 cursor-pointer rounded-ui-sm border border-ui-line bg-ui-surface"
                aria-label="Farbe wählen"
              />
              {entwurf.farbmarkierung && (
                <Button
                  variante="still"
                  onClick={() => setzeFeld("farbmarkierung", "")}
                >
                  entfernen
                </Button>
              )}
            </div>
          </Field>
        </div>
      </Section>

      {/* ───── Termine ───── */}
      <Section
        titel="Termine"
        icon={CalendarClock}
        zusatz={
          mangel.aktuelle_frist
            ? `aktuelle Frist ${formatDatumKurz(mangel.aktuelle_frist)}`
            : "keine Frist"
        }
      >
        {/* Kopfzeile wie in der Bürosoftware: die vier Eckdaten auf einen Blick */}
        <div className="mb-4 flex flex-wrap gap-x-6 gap-y-2 rounded-ui bg-ui-surface-muted px-3.5 py-2.5 text-[12.5px]">
          <span className="text-ui-text-muted">
            Aufgenommen:{" "}
            <span className="text-ui-text">{formatDatumKurz(mangel.erstellt_am)}</span>
          </span>
          <span className="text-ui-text-muted">
            aktuelle Frist:{" "}
            <span
              className={
                mangel.ist_ueberfaellig ? "font-semibold text-ui-danger" : "text-ui-text"
              }
            >
              {formatDatumKurz(mangel.aktuelle_frist) || "—"}
            </span>
          </span>
          <span className="text-ui-text-muted">
            Freigemeldet:{" "}
            <span className="text-ui-text">
              {formatDatumKurz(mangel.freigemeldet_am) || "—"}
            </span>
          </span>
          <span className="text-ui-text-muted">
            Erledigt:{" "}
            <span className="text-ui-text">
              {formatDatumKurz(mangel.erledigt_am) || "—"}
            </span>
          </span>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Erstellt / 1. Frist gesetzt">
            <Input
              type="date"
              value={entwurf.erstellt_am}
              onChange={(e) => setzeFeld("erstellt_am", e.target.value)}
            />
          </Field>
          <Field label="1. Frist bis">
            <Input
              type="date"
              value={entwurf.erste_frist_bis ?? ""}
              onChange={(e) => setzeFeld("erste_frist_bis", e.target.value || null)}
            />
          </Field>
          <Field
            label="1. Nachfrist gesetzt"
            hinweis="Wird beim Speichern automatisch auf heute gesetzt, sobald ein Nachfristende eingetragen ist."
          >
            <Input
              type="date"
              value={entwurf.erste_nachfrist_gesetzt_am ?? ""}
              onChange={(e) =>
                setzeFeld("erste_nachfrist_gesetzt_am", e.target.value || null)
              }
            />
          </Field>
          <Field label="1. Nachfrist bis">
            <Input
              type="date"
              value={entwurf.erste_nachfrist_bis ?? ""}
              onChange={(e) =>
                setzeFeld("erste_nachfrist_bis", e.target.value || null)
              }
            />
          </Field>
          <Field label="Beseitigungsanzeige" hinweis="Firma meldet die Beseitigung.">
            <Input
              type="date"
              value={entwurf.beseitigungsanzeige_am ?? ""}
              onChange={(e) =>
                setzeFeld("beseitigungsanzeige_am", e.target.value || null)
              }
            />
          </Field>
          <Field label="Freigemeldet am">
            <Input
              type="date"
              value={entwurf.freigemeldet_am ?? ""}
              onChange={(e) => setzeFeld("freigemeldet_am", e.target.value || null)}
            />
          </Field>
          <Field label="Erledigt am">
            <Input
              type="date"
              value={entwurf.erledigt_am ?? ""}
              onChange={(e) => setzeFeld("erledigt_am", e.target.value || null)}
            />
          </Field>
          <Field label="Zurückweisung" hinweis="Prüfung abgelehnt.">
            <Input
              type="date"
              value={entwurf.zurueckweisung_am ?? ""}
              onChange={(e) => setzeFeld("zurueckweisung_am", e.target.value || null)}
            />
          </Field>
          <Field label="Aufgenommen von">
            <Input
              value={entwurf.aufgenommen_von}
              onChange={(e) => setzeFeld("aufgenommen_von", e.target.value)}
            />
          </Field>
          <Field label="User">
            <Select
              value={entwurf.zustaendiger_user_id ?? ""}
              onChange={(e) =>
                setzeFeld(
                  "zustaendiger_user_id",
                  e.target.value ? Number(e.target.value) : null
                )
              }
            >
              <option value="">— nicht zugeordnet —</option>
              {(stammdaten?.bearbeiter || []).map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="mt-4">
          <Field label="Anmerkung 1. Nachfrist">
            <Input
              value={entwurf.anmerkung_nachfrist}
              onChange={(e) => setzeFeld("anmerkung_nachfrist", e.target.value)}
            />
          </Field>
        </div>

        {/* Intern — bewusst abgesetzt und beschriftet. */}
        <div className="mt-5 rounded-ui border border-dashed border-ui-line-strong bg-ui-warn-soft/40 p-3.5">
          <div className="mb-2 inline-flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ui-warn">
            <Lock size={12} /> Nur intern — für Firmen nicht sichtbar
          </div>
          <Textarea
            value={entwurf.interne_bemerkung}
            onChange={(e) => setzeFeld("interne_bemerkung", e.target.value)}
            placeholder="Interne Bemerkung zu Fristen und Freimeldung…"
          />
          <p className="mt-1.5 text-[12px] text-ui-text-muted">
            Dieser Text erscheint nur in der internen Fassung der Mängelliste,
            niemals in der Fassung für die Firma.
          </p>
        </div>
      </Section>

      {/* ───── Mail ───── */}
      <Section
        titel="Mail"
        icon={Mail}
        warnung={mailFehler !== null}
        zusatz={
          mangel.zuletzt_versendet_am
            ? `versendet ${formatDatumKurz(mangel.zuletzt_versendet_am)}`
            : "noch nicht versendet"
        }
      >
        <div className="flex flex-col gap-3">
          {mailFehler && (
            <div className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-ui-danger">
              <AlertTriangle size={14} /> {mailFehler}
            </div>
          )}

          <Checkbox
            checked={entwurf.mail_autosend}
            disabled={mailFehler !== null}
            onChange={(wert) => {
              setzeFeld("mail_autosend", wert);
              setzeFeld("mail_versendemodus", wert ? "automatisch" : "manuell");
            }}
            label="Autosend — Mängelrüge bei Änderungen automatisch melden"
          />

          <div className="text-[13px] text-ui-text-muted">
            Versendemodus:{" "}
            <span className="text-ui-text">
              {entwurf.mail_versendemodus === "automatisch"
                ? "automatisches Senden"
                : "manuelles Senden"}
            </span>
            {gewaehltesGewerk?.email && (
              <> · Empfänger: <span className="text-ui-text">{gewaehltesGewerk.email}</span></>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              icon={Send}
              disabled={mailFehler !== null || aktion !== null}
              onClick={() =>
                fuehreAus("senden", async () => {
                  const ergebnis = await api.maengel.senden(mangel.id);
                  if (ergebnis.versendet) {
                    setErfolg(ergebnis.nachricht);
                  } else {
                    setFehler(ergebnis.nachricht);
                  }
                  onAktualisiert();
                })
              }
            >
              {aktion === "senden" ? "Wird gemeldet…" : "Jetzt senden"}
            </Button>
            {mangel.zuletzt_versendet_am && (
              <span className="text-[12.5px] text-ui-text-muted">
                Zuletzt versendet am {formatDatum(mangel.zuletzt_versendet_am)}
              </span>
            )}
          </div>
        </div>
      </Section>

      {/* ───── Fotos ───── */}
      <Section
        titel="Fotos"
        icon={ImageIcon}
        zusatz={`${mangel.fotos.length} Foto(s)`}
      >
        <FotoGalerie
          mangelId={mangel.id}
          fotos={mangel.fotos}
          onAendern={onAktualisiert}
        />
      </Section>

      {/* ───── Markierung ───── */}
      <Section
        titel="Markierung"
        icon={MapPin}
        offenStart={false}
        zusatz={
          mangel.markierung
            ? `${mangel.markierung.plan_dateiname}, Seite ${mangel.markierung.seite}`
            : "Es ist keine Markierung vorhanden."
        }
      >
        <PlanMarkierungFeld
          plaene={plaene}
          planName={mangel.markierung?.plan_dateiname}
          wert={
            mangel.markierung
              ? {
                  plan_datei_id: mangel.markierung.plan_datei_id,
                  x_prozent: mangel.markierung.x_prozent,
                  y_prozent: mangel.markierung.y_prozent,
                  seite: mangel.markierung.seite,
                }
              : null
          }
          onWert={(wert: MarkierungsWert | null) =>
            fuehreAus("markierung", async () => {
              if (wert) {
                await api.maengel.setzeMarkierung(mangel.id, wert);
              } else {
                await api.maengel.loescheMarkierung(mangel.id);
              }
              onAktualisiert();
            })
          }
        />
      </Section>

      {/* ───── Rückmeldung ───── */}
      <Section
        titel="Rückmeldung"
        icon={MessageSquareReply}
        offenStart={false}
        zusatz={mangel.rueckmeldung_status || "keine Rückmeldung"}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Status Rückmeldung">
            <Select
              value={entwurf.rueckmeldung_status}
              onChange={(e) => setzeFeld("rueckmeldung_status", e.target.value)}
            >
              <option value="">— keine Angabe —</option>
              {(stammdaten?.rueckmeldung_status || []).map((r) => (
                <option key={r.id} value={r.bezeichnung}>
                  {r.bezeichnung}
                </option>
              ))}
              {entwurf.rueckmeldung_status &&
                !(stammdaten?.rueckmeldung_status || []).some(
                  (r) => r.bezeichnung === entwurf.rueckmeldung_status
                ) && (
                  <option value={entwurf.rueckmeldung_status}>
                    {entwurf.rueckmeldung_status}
                  </option>
                )}
            </Select>
          </Field>
          <ReadOnlyField
            label="Beseitigungsanzeige der Firma"
            wert={formatDatum(mangel.beseitigungsanzeige_am)}
          />
        </div>
      </Section>

      {/* ───── Dateien ───── */}
      <Section
        titel="Dateien"
        icon={Files}
        offenStart={false}
        zusatz={`${mangel.dateien.length} Anhang/Anhänge`}
      >
        <div className="flex flex-col gap-3">
          {mangel.dateien.length === 0 ? (
            <EmptyState>
              Keine weiteren Anhänge. Hier gehören Schriftverkehr, Protokolle
              oder Prüfberichte hin — Fotos haben ihren eigenen Abschnitt.
            </EmptyState>
          ) : (
            <div className="flex flex-col gap-1.5">
              {mangel.dateien.map((datei) => (
                <div
                  key={datei.id}
                  className="flex items-center justify-between gap-3 rounded-ui-sm border border-ui-line px-3 py-2 text-[13px]"
                >
                  <a
                    href={api.maengel.dateiUrl(datei.id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex min-w-0 items-center gap-2 text-ui-accent hover:underline"
                  >
                    <Paperclip size={13} className="shrink-0" />
                    <span className="truncate">{datei.dateiname}</span>
                  </a>
                  <button
                    type="button"
                    aria-label="Anhang löschen"
                    className="shrink-0 cursor-pointer text-ui-text-faint transition-colors hover:text-ui-danger"
                    onClick={() =>
                      fuehreAus("datei", async () => {
                        await api.maengel.deleteDatei(datei.id);
                        onAktualisiert();
                      })
                    }
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div>
            <Button
              variante="sekundaer"
              icon={Paperclip}
              disabled={aktion !== null}
              onClick={() => anhangRef.current?.click()}
            >
              {aktion === "anhang" ? "Wird übertragen…" : "Anhang hinzufügen"}
            </Button>
            <input
              ref={anhangRef}
              type="file"
              multiple
              className="hidden"
              onChange={(event) => {
                const dateien = Array.from(event.target.files || []);
                event.target.value = "";
                if (dateien.length === 0) return;
                fuehreAus("anhang", async () => {
                  await api.maengel.uploadDateien(mangel.id, dateien);
                  onAktualisiert();
                });
              }}
            />
          </div>
        </div>
      </Section>

      {/* ───── Speicherleiste ───── */}
      {hatAenderungen && (
        <div className="fixed inset-x-0 bottom-[calc(4.25rem+env(safe-area-inset-bottom))] z-40 border-t border-ui-line bg-ui-surface/95 px-4 py-3 backdrop-blur sm:bottom-0 sm:px-5">
          <div className="mx-auto flex max-w-[1100px] flex-wrap items-center gap-3">
            <span className="mr-auto min-w-0 text-[13px] text-ui-text-muted">
              {Object.keys(aenderungen).length} Änderung(en) noch nicht gespeichert
            </span>
            <Button variante="still" icon={Undo2} onClick={() => setEntwurf(entwurfAus(mangel))}>
              Verwerfen
            </Button>
            <Button onClick={speichern} disabled={speichert}>
              {speichert ? (
                <>
                  <Loader2 size={15} className="animate-spin" /> Wird gespeichert…
                </>
              ) : (
                "Änderungen speichern"
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Kleiner Kopfbereich für die Detailansicht, wenn nichts geladen ist. */
export function MangelDetailLaedt() {
  return (
    <div className="flex flex-col gap-3">
      <Bereichstitel>Mangel</Bereichstitel>
      <Card className="flex items-center gap-2 px-4 py-6 text-[13px] text-ui-text-muted">
        <Loader2 size={15} className="animate-spin" />
        Mangel wird geladen…
      </Card>
      <Label>Bitte einen Moment</Label>
    </div>
  );
}
