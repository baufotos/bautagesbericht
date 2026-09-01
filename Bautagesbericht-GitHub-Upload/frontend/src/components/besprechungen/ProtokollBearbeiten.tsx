"use client";

/**
 * Ein Baubesprechungsprotokoll prüfen und freigeben.
 *
 * DIESE ANSICHT *IST* DER PRÜFSCHRITT
 * ===================================
 * Zwischen "KI hat ausgewertet" und "Word-Dokument" steht genau dieses
 * Formular. Es ist nicht Beiwerk, sondern der Grund, warum die Funktion so
 * gebaut ist: Ein erfundener Termin sieht in einem Protokoll aus wie ein
 * richtiger, und das Protokoll geht an Bauherrn und Firmen.
 *
 * Deshalb sagt jede Zeile, woher sie kommt:
 *
 *   übernommen   stand schon im letzten Protokoll, unverändert — gilt als
 *                geprüft, trägt weiterhin ihre alte BB-Nummer
 *   Vorschlag    kam aus der Analyse — hervorgehoben, bis jemand sie ansieht
 *   bearbeitet   von Hand angelegt oder geändert; die BB-Nummer rückt dann
 *                auf die laufende Sitzung
 *
 * Freigeben geht erst, wenn keine Zeile mehr offen ist. Wer trotzdem will,
 * muss das ausdrücklich bestätigen — der Weg existiert, aber man geht ihn
 * nicht versehentlich.
 */

import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCheck,
  Download,
  FileText,
  Loader2,
  Paperclip,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Users,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { dateiSpeichern } from "@/lib/dateien";
import type {
  BesprechungsKapitel,
  BesprechungStatus,
  Protokoll,
  ThemaUpdate,
} from "@/lib/types";
import {
  Bereichstitel,
  Button,
  Card,
  Checkbox,
  EmptyState,
  Field,
  Input,
  Meldung,
  Section,
  Select,
  Textarea,
  formatDatum,
} from "@/components/ui";

/** Legende des Protokolls — dieselben Buchstaben und Farben wie im Dokument. */
const STATUS: { wert: BesprechungStatus; text: string; farbe: string }[] = [
  { wert: "n", text: "neu", farbe: "bg-[#DDEBF7] text-[#1F3864]" },
  { wert: "b", text: "in Bearbeitung", farbe: "bg-[#FFEB9C] text-[#9C5700]" },
  { wert: "e", text: "erledigt", farbe: "bg-[#C6EFCE] text-[#006100]" },
  { wert: "k", text: "kritisch", farbe: "bg-[#FFC7CE] text-[#9C0006]" },
  { wert: "i", text: "informativ", farbe: "bg-ui-surface-muted text-ui-text-muted" },
];

function statusFarbe(wert: string): string {
  return STATUS.find((s) => s.wert === wert)?.farbe ?? "bg-ui-surface-muted";
}

function statusText(wert: string): string {
  return STATUS.find((s) => s.wert === wert)?.text ?? wert;
}

export function ProtokollBearbeiten({
  protokollId,
  onZurueck,
  onGeaendert,
}: {
  protokollId: number;
  onZurueck: () => void;
  onGeaendert?: () => void;
}) {
  const [protokoll, setProtokoll] = useState<Protokoll | null>(null);
  const [kapitel, setKapitel] = useState<BesprechungsKapitel[]>([]);
  const [laedt, setLaedt] = useState(true);
  const [fehler, setFehler] = useState<string | null>(null);
  const [hinweis, setHinweis] = useState<string | null>(null);
  const [beschaeftigt, setBeschaeftigt] = useState<string | null>(null);

  const laden = useCallback(async () => {
    try {
      const daten = await api.besprechungen.get(protokollId);
      setProtokoll(daten);
      setKapitel(await api.besprechungen.kapitel(daten.projekt_id));
    } catch (f) {
      setFehler(
        f instanceof Error ? f.message : "Protokoll konnte nicht geladen werden."
      );
    } finally {
      setLaedt(false);
    }
  }, [protokollId]);

  useEffect(() => {
    laden();
  }, [laden]);

  async function mitLadebalken(name: string, tun: () => Promise<void>) {
    setBeschaeftigt(name);
    setFehler(null);
    try {
      await tun();
      await laden();
      onGeaendert?.();
    } catch (f) {
      setFehler(f instanceof Error ? f.message : "Das hat nicht geklappt.");
    } finally {
      setBeschaeftigt(null);
    }
  }

  if (laedt) {
    return (
      <Card className="p-4">
        <div className="flex items-center gap-2 text-[13px] text-ui-text-muted">
          <Loader2 size={15} className="animate-spin" />
          Protokoll wird geladen…
        </div>
      </Card>
    );
  }

  if (!protokoll) {
    return <Meldung art="fehler">{fehler ?? "Protokoll nicht gefunden."}</Meldung>;
  }

  const freigegeben = protokoll.status === "freigegeben";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button variante="still" icon={ArrowLeft} onClick={onZurueck}>
          Zurück zur Übersicht
        </Button>
        <div className="flex items-center gap-2 text-[13px] text-ui-text-muted">
          <span className="font-medium text-ui-text">
            Protokoll Nr. {protokoll.nummer}
          </span>
          <span>·</span>
          <span>{formatDatum(protokoll.besprechungsdatum)}</span>
          {freigegeben && (
            <span className="rounded bg-ui-ok-soft px-2 py-0.5 text-[12px] text-ui-ok">
              freigegeben
            </span>
          )}
        </div>
      </div>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}
      {hinweis && <Meldung art="erfolg">{hinweis}</Meldung>}

      {protokoll.analyse_hinweise.length > 0 && (
        <Meldung art="hinweis">
          <div className="font-medium">Bitte beim Prüfen beachten:</div>
          <ul className="ml-4 list-disc">
            {protokoll.analyse_hinweise.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        </Meldung>
      )}

      {!freigegeben && (
        <TldvImport
          protokoll={protokoll}
          beschaeftigt={beschaeftigt}
          onAuswerten={(transkript, notizen) =>
            mitLadebalken("analyse", async () => {
              const ergebnis = await api.besprechungen.tldvImport(protokoll.id, {
                transkript,
                notizen,
              });
              setHinweis(
                `Auswertung fertig: ${ergebnis.fortschreibungen} bestehende Themen ` +
                  `fortgeschrieben, ${ergebnis.neue_themen} neu angelegt, ` +
                  `${ergebnis.teilnehmer} Teilnehmer erkannt. Bitte jede Zeile prüfen.`
              );
            })
          }
          onErneut={() =>
            mitLadebalken("analyse", async () => {
              await api.besprechungen.analysieren(protokoll.id);
              setHinweis("Erneut ausgewertet.");
            })
          }
        />
      )}

      <ThemenTabelle
        protokoll={protokoll}
        kapitel={kapitel}
        gesperrt={freigegeben}
        beschaeftigt={beschaeftigt}
        onAendern={(updateId, daten) =>
          mitLadebalken(`zeile-${updateId}`, async () => {
            await api.besprechungen.themaAendern(protokoll.id, updateId, daten);
          })
        }
        onEntfernen={(updateId) =>
          mitLadebalken(`zeile-${updateId}`, async () => {
            await api.besprechungen.themaEntfernen(protokoll.id, updateId);
          })
        }
        onHinzufuegen={(daten) =>
          mitLadebalken("neu", async () => {
            await api.besprechungen.themaHinzufuegen(protokoll.id, daten);
          })
        }
      />

      <Teilnehmerliste
        protokoll={protokoll}
        gesperrt={freigegeben}
        onAendern={(id, daten) =>
          mitLadebalken(`tn-${id}`, async () => {
            await api.besprechungen.teilnehmerAendern(protokoll.id, id, daten);
          })
        }
        onEntfernen={(id) =>
          mitLadebalken(`tn-${id}`, async () => {
            await api.besprechungen.teilnehmerLoeschen(protokoll.id, id);
          })
        }
        onHinzufuegen={(daten) =>
          mitLadebalken("tn-neu", async () => {
            await api.besprechungen.teilnehmerHinzufuegen(protokoll.id, daten);
          })
        }
        onAusStammdaten={() =>
          mitLadebalken("tn-stamm", async () => {
            await api.besprechungen.teilnehmerAusBeteiligten(protokoll.id);
          })
        }
      />

      <Anlagen
        protokoll={protokoll}
        gesperrt={freigegeben}
        beschaeftigt={beschaeftigt}
        onHochladen={(datei, bezeichnung) =>
          mitLadebalken("anlage", async () => {
            await api.besprechungen.anlageHochladen(protokoll.id, datei, bezeichnung);
          })
        }
        onLoeschen={(id) =>
          mitLadebalken(`anlage-${id}`, async () => {
            await api.besprechungen.anlageLoeschen(protokoll.id, id);
          })
        }
      />

      <Abschluss
        protokoll={protokoll}
        beschaeftigt={beschaeftigt}
        onFreigeben={(trotzdem) =>
          mitLadebalken("freigabe", async () => {
            await api.besprechungen.freigeben(protokoll.id, {
              trotz_ungeprueft: trotzdem,
            });
            setHinweis(
              "Freigegeben. Die noch offenen Punkte stehen im nächsten Protokoll " +
                "automatisch wieder drin."
            );
          })
        }
        onNeuErzeugen={() =>
          mitLadebalken("erzeugen", async () => {
            await api.besprechungen.neuErzeugen(protokoll.id);
            setHinweis("Dokument neu erzeugt.");
          })
        }
        onHerunterladen={async (alsPdf) => {
          try {
            const { blob, dateiname } = await api.besprechungen.dokument(
              protokoll.id,
              alsPdf
            );
            dateiSpeichern(blob, dateiname);
          } catch (f) {
            setFehler(f instanceof Error ? f.message : "Download fehlgeschlagen.");
          }
        }}
      />
    </div>
  );
}

/* ───────────────────────────── tl;dv-Import ───────────────────────────── */

function TldvImport({
  protokoll,
  beschaeftigt,
  onAuswerten,
  onErneut,
}: {
  protokoll: Protokoll;
  beschaeftigt: string | null;
  onAuswerten: (transkript: string, notizen: string) => void;
  onErneut: () => void;
}) {
  const [transkript, setTranskript] = useState(protokoll.tldv_transkript_roh);
  const [notizen, setNotizen] = useState(protokoll.tldv_notizen_roh);
  const laeuft = beschaeftigt === "analyse";

  return (
    <Section
      titel="tl;dv-Text auswerten"
      icon={Sparkles}
      offenStart={!protokoll.hat_transkript}
      zusatz={
        protokoll.analyse_am
          ? `zuletzt ${formatDatum(protokoll.analyse_am)}`
          : undefined
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-[13px] text-ui-text-muted">
          In tl;dv die KI-Notizen und — wenn vorhanden — das Transkript
          markieren, kopieren und hier einfügen. Eines von beidem genügt;
          zusammen wird die Zuordnung besser.
        </p>
        <Field label="tl;dv-Notizen (KI-Zusammenfassung)">
          <Textarea
            rows={6}
            value={notizen}
            onChange={(e) => setNotizen(e.target.value)}
            placeholder="Hier die Meeting-Notizen aus tl;dv einfügen…"
          />
        </Field>
        <Field label="Transkript (Wortprotokoll)">
          <Textarea
            rows={8}
            value={transkript}
            onChange={(e) => setTranskript(e.target.value)}
            placeholder="Hier das Transkript aus tl;dv einfügen…"
          />
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button
            icon={laeuft ? undefined : Sparkles}
            onClick={() => onAuswerten(transkript, notizen)}
            disabled={laeuft || (!transkript.trim() && !notizen.trim())}
          >
            {laeuft && <Loader2 size={15} className="animate-spin" />}
            Analysieren
          </Button>
          {protokoll.hat_transkript && (
            <Button
              variante="sekundaer"
              icon={RefreshCw}
              onClick={onErneut}
              disabled={laeuft}
            >
              Erneut auswerten
            </Button>
          )}
        </div>
        <p className="text-[12.5px] text-ui-text-faint">
          Die Auswertung ordnet jeden Punkt einem bestehenden offenen Thema zu
          oder legt ein neues an. Sie läuft auch ohne Anthropic-Schlüssel — dann
          nach Regeln statt mit KI: Stichpunkte der tl;dv-Notizen, Fristen wie
          „KW 36’26“, Zuständige an ihrem Kürzel. Nichts davon geht ungeprüft
          ins Dokument.
        </p>
      </div>
    </Section>
  );
}

/* ───────────────────────────── Themen ───────────────────────────── */

function ThemenTabelle({
  protokoll,
  kapitel,
  gesperrt,
  beschaeftigt,
  onAendern,
  onEntfernen,
  onHinzufuegen,
}: {
  protokoll: Protokoll;
  kapitel: BesprechungsKapitel[];
  gesperrt: boolean;
  beschaeftigt: string | null;
  onAendern: (updateId: number, daten: Partial<ThemaUpdate>) => void;
  onEntfernen: (updateId: number) => void;
  onHinzufuegen: (daten: {
    kapitel_id: number;
    thema_text: string;
    zustaendig: string;
    bearb_bis: string;
    status: BesprechungStatus;
  }) => void;
}) {
  const [neuOffen, setNeuOffen] = useState(false);
  const offen = protokoll.themen_updates.filter((u) => !u.bestaetigt).length;

  const gruppen = useMemo(() => {
    const map = new Map<
      number,
      { titel: string; nummer: string; zeilen: ThemaUpdate[] }
    >();
    for (const zeile of protokoll.themen_updates) {
      const eintrag = map.get(zeile.kapitel_id) ?? {
        titel: zeile.kapitel_titel,
        nummer: zeile.kapitel_nummer,
        zeilen: [],
      };
      eintrag.zeilen.push(zeile);
      map.set(zeile.kapitel_id, eintrag);
    }
    return [...map.values()];
  }, [protokoll.themen_updates]);

  return (
    <Card className="p-4">
      <Bereichstitel
        aktion={
          gesperrt ? undefined : (
            <div className="flex flex-wrap gap-2">
              {offen > 0 && (
                <Button
                  variante="sekundaer"
                  icon={CheckCheck}
                  onClick={() =>
                    protokoll.themen_updates
                      .filter((u) => !u.bestaetigt)
                      .forEach((u) => onAendern(u.id, { bestaetigt: true }))
                  }
                >
                  Alle bestätigen
                </Button>
              )}
              <Button
                variante="sekundaer"
                icon={Plus}
                onClick={() => setNeuOffen((o) => !o)}
              >
                Thema
              </Button>
            </div>
          )
        }
      >
        Themen —{" "}
        {offen > 0
          ? `${offen} von ${protokoll.themen_updates.length} noch zu prüfen`
          : `${protokoll.themen_updates.length} Zeilen, alle geprüft`}
      </Bereichstitel>

      {neuOffen && !gesperrt && (
        <NeuesThema
          kapitel={kapitel}
          laeuft={beschaeftigt === "neu"}
          onAbbrechen={() => setNeuOffen(false)}
          onSpeichern={(daten) => {
            onHinzufuegen(daten);
            setNeuOffen(false);
          }}
        />
      )}

      {protokoll.themen_updates.length === 0 ? (
        <EmptyState>
          Noch keine Themen. tl;dv-Text auswerten oder ein Thema von Hand
          anlegen.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-4">
          {gruppen.map((gruppe, i) => (
            <div key={i} className="overflow-hidden rounded-ui border border-ui-line">
              <div className="bg-ui-surface-muted px-3 py-1.5 text-[13px] font-semibold text-ui-text">
                {gruppe.nummer} {gruppe.titel}
              </div>
              <div className="divide-y divide-ui-line">
                {gruppe.zeilen.map((zeile) => (
                  <ThemaZeile
                    key={zeile.id}
                    zeile={zeile}
                    gesperrt={gesperrt}
                    laeuft={beschaeftigt === `zeile-${zeile.id}`}
                    onAendern={(daten) => onAendern(zeile.id, daten)}
                    onEntfernen={() => onEntfernen(zeile.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function ThemaZeile({
  zeile,
  gesperrt,
  laeuft,
  onAendern,
  onEntfernen,
}: {
  zeile: ThemaUpdate;
  gesperrt: boolean;
  laeuft: boolean;
  onAendern: (daten: Partial<ThemaUpdate>) => void;
  onEntfernen: () => void;
}) {
  const [text, setText] = useState(zeile.thema_text);
  const [zustaendig, setZustaendig] = useState(zeile.zustaendig);
  const [frist, setFrist] = useState(zeile.bearb_bis);
  const gemerkt = useRef({
    text: zeile.thema_text,
    zustaendig: zeile.zustaendig,
    frist: zeile.bearb_bis,
  });

  useEffect(() => {
    setText(zeile.thema_text);
    setZustaendig(zeile.zustaendig);
    setFrist(zeile.bearb_bis);
    gemerkt.current = {
      text: zeile.thema_text,
      zustaendig: zeile.zustaendig,
      frist: zeile.bearb_bis,
    };
  }, [zeile.thema_text, zeile.zustaendig, zeile.bearb_bis]);

  /** Erst beim Verlassen des Feldes speichern — sonst ein Aufruf je Tastendruck. */
  function sichern() {
    const daten: Partial<ThemaUpdate> = {};
    if (text !== gemerkt.current.text) daten.thema_text = text;
    if (zustaendig !== gemerkt.current.zustaendig) daten.zustaendig = zustaendig;
    if (frist !== gemerkt.current.frist) daten.bearb_bis = frist;
    if (Object.keys(daten).length > 0) onAendern(daten);
  }

  const geaendert = zeile.vorher_text && zeile.vorher_text !== zeile.thema_text;

  return (
    <div className={`flex flex-col gap-2 p-3 ${zeile.bestaetigt ? "" : "bg-ui-warn-soft"}`}>
      <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
        <span className="font-mono font-medium text-ui-text">{zeile.nummer}</span>
        <span className={`rounded px-1.5 py-0.5 ${statusFarbe(zeile.status)}`}>
          {zeile.status} · {statusText(zeile.status)}
        </span>
        {zeile.uebernommen && (
          <span className="rounded bg-ui-surface-muted px-1.5 py-0.5 text-ui-text-muted">
            unverändert übernommen (BB {zeile.bb_nr})
          </span>
        )}
        {zeile.herkunft === "ki" && (
          <span className="flex items-center gap-1 rounded px-1.5 py-0.5 text-ui-warn">
            <Wand2 size={12} /> Vorschlag der Analyse
          </span>
        )}
        {geaendert && (
          <span className="text-ui-text-faint">
            vorher (BB {zeile.vorher_bb}): {zeile.vorher_text.slice(0, 60)}…
          </span>
        )}
        <span className="ml-auto flex items-center gap-2">
          {laeuft && <Loader2 size={14} className="animate-spin text-ui-text-muted" />}
          {!gesperrt && (
            <>
              {!zeile.bestaetigt && (
                <Button
                  variante="sekundaer"
                  icon={Check}
                  onClick={() => onAendern({ bestaetigt: true })}
                >
                  Passt
                </Button>
              )}
              <button
                type="button"
                onClick={onEntfernen}
                title="Zeile aus diesem Protokoll nehmen — das Thema bleibt in der Liste"
                className="text-ui-text-faint hover:text-ui-danger"
              >
                <Trash2 size={15} />
              </button>
            </>
          )}
        </span>
      </div>

      <Textarea
        rows={Math.min(6, Math.max(2, text.split("\n").length))}
        value={text}
        disabled={gesperrt}
        onChange={(e) => setText(e.target.value)}
        onBlur={sichern}
      />

      <div className="grid gap-2 sm:grid-cols-3">
        <Field label="Zuständig">
          <Input
            value={zustaendig}
            disabled={gesperrt}
            onChange={(e) => setZustaendig(e.target.value)}
            onBlur={sichern}
            placeholder="ROL"
          />
        </Field>
        <Field label="Bearb. bis">
          <Input
            value={frist}
            disabled={gesperrt}
            onChange={(e) => setFrist(e.target.value)}
            onBlur={sichern}
            placeholder="25.08.26 oder KW 35'26"
          />
        </Field>
        <Field label="Status">
          <Select
            value={zeile.status}
            disabled={gesperrt}
            onChange={(e) =>
              onAendern({ status: e.target.value as BesprechungStatus })
            }
          >
            {STATUS.map((s) => (
              <option key={s.wert} value={s.wert}>
                {s.wert} — {s.text}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {!gesperrt && (
        <Checkbox
          checked={zeile.hervorheben}
          onChange={(wert) => onAendern({ hervorheben: wert })}
          label="Frist im Dokument farbig hervorheben"
        />
      )}
    </div>
  );
}

function NeuesThema({
  kapitel,
  laeuft,
  onAbbrechen,
  onSpeichern,
}: {
  kapitel: BesprechungsKapitel[];
  laeuft: boolean;
  onAbbrechen: () => void;
  onSpeichern: (daten: {
    kapitel_id: number;
    thema_text: string;
    zustaendig: string;
    bearb_bis: string;
    status: BesprechungStatus;
  }) => void;
}) {
  const [kapitelId, setKapitelId] = useState(kapitel[0]?.id ?? 0);
  const [text, setText] = useState("");
  const [zustaendig, setZustaendig] = useState("");
  const [frist, setFrist] = useState("");
  const [status, setStatus] = useState<BesprechungStatus>("n");

  if (kapitel.length === 0) {
    return (
      <div className="mb-3">
        <Meldung art="hinweis">
          Für dieses Projekt sind noch keine Kapitel angelegt — ein neues Thema
          hätte keine Nummer. Unter „Stammdaten → Besprechungen“ die Kapitel aus
          den Gewerken erzeugen.
        </Meldung>
      </div>
    );
  }

  return (
    <div className="mb-3 flex flex-col gap-3 rounded-ui border border-ui-line bg-ui-surface-muted p-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Kapitel">
          <Select
            value={kapitelId}
            onChange={(e) => setKapitelId(Number(e.target.value))}
          >
            {kapitel.map((k) => (
              <option key={k.id} value={k.id}>
                {k.nummer} {k.titel}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Status">
          <Select
            value={status}
            onChange={(e) => setStatus(e.target.value as BesprechungStatus)}
          >
            {STATUS.map((s) => (
              <option key={s.wert} value={s.wert}>
                {s.wert} — {s.text}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="Thema">
        <Textarea
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Knapp und sachlich, wie im Protokoll…"
        />
      </Field>
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Zuständig">
          <Input value={zustaendig} onChange={(e) => setZustaendig(e.target.value)} />
        </Field>
        <Field label="Bearb. bis">
          <Input
            value={frist}
            onChange={(e) => setFrist(e.target.value)}
            placeholder="25.08.26 oder KW 35'26"
          />
        </Field>
      </div>
      <div className="flex gap-2">
        <Button
          icon={Plus}
          onClick={() =>
            onSpeichern({
              kapitel_id: kapitelId,
              thema_text: text.trim(),
              zustaendig: zustaendig.trim(),
              bearb_bis: frist.trim(),
              status,
            })
          }
          disabled={!text.trim() || laeuft}
        >
          {laeuft && <Loader2 size={15} className="animate-spin" />}
          Anlegen
        </Button>
        <Button variante="still" onClick={onAbbrechen}>
          Abbrechen
        </Button>
      </div>
    </div>
  );
}

/* ───────────────────────────── Teilnehmer ───────────────────────────── */

function Teilnehmerliste({
  protokoll,
  gesperrt,
  onAendern,
  onEntfernen,
  onHinzufuegen,
  onAusStammdaten,
}: {
  protokoll: Protokoll;
  gesperrt: boolean;
  onAendern: (
    id: number,
    daten: { name?: string; firma_kuerzel?: string; telefon?: string }
  ) => void;
  onEntfernen: (id: number) => void;
  onHinzufuegen: (daten: {
    name: string;
    firma_kuerzel: string;
    telefon: string;
  }) => void;
  onAusStammdaten: () => void;
}) {
  const [name, setName] = useState("");
  const [firma, setFirma] = useState("");
  const [telefon, setTelefon] = useState("");

  return (
    <Section
      titel="Teilnehmer"
      icon={Users}
      offenStart={false}
      zusatz={`${protokoll.teilnehmer.length} Person(en)`}
    >
      <div className="flex flex-col gap-2">
        {!gesperrt && (
          <div>
            <Button variante="sekundaer" icon={Users} onClick={onAusStammdaten}>
              Ansprechpartner aus den Projektbeteiligten übernehmen
            </Button>
          </div>
        )}

        {protokoll.teilnehmer.map((person) => (
          <div
            key={person.id}
            className="grid items-end gap-2 sm:grid-cols-[2fr_1fr_1.5fr_auto]"
          >
            <Field label="Name">
              <Input
                defaultValue={person.name}
                disabled={gesperrt}
                onBlur={(e) =>
                  e.target.value !== person.name &&
                  onAendern(person.id, { name: e.target.value })
                }
              />
            </Field>
            <Field label="Firma">
              <Input
                defaultValue={person.firma_kuerzel}
                disabled={gesperrt}
                onBlur={(e) =>
                  e.target.value !== person.firma_kuerzel &&
                  onAendern(person.id, { firma_kuerzel: e.target.value })
                }
              />
            </Field>
            <Field
              label="Telefon"
              hinweis={
                person.aus_transkript && !person.telefon
                  ? "tl;dv liefert keine Nummer — bitte ergänzen"
                  : undefined
              }
            >
              <Input
                defaultValue={person.telefon}
                disabled={gesperrt}
                onBlur={(e) =>
                  e.target.value !== person.telefon &&
                  onAendern(person.id, { telefon: e.target.value })
                }
              />
            </Field>
            {!gesperrt && (
              <button
                type="button"
                onClick={() => onEntfernen(person.id)}
                className="mb-2 text-ui-text-faint hover:text-ui-danger"
              >
                <Trash2 size={15} />
              </button>
            )}
          </div>
        ))}

        {protokoll.teilnehmer.length === 0 && (
          <EmptyState>
            Noch niemand eingetragen. tl;dv liefert Namen, aber weder Firma noch
            Telefonnummer — beides kommt aus den Projektbeteiligten.
          </EmptyState>
        )}

        {!gesperrt && (
          <div className="mt-2 grid items-end gap-2 border-t border-ui-line pt-3 sm:grid-cols-[2fr_1fr_1.5fr_auto]">
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Firma">
              <Input value={firma} onChange={(e) => setFirma(e.target.value)} />
            </Field>
            <Field label="Telefon">
              <Input value={telefon} onChange={(e) => setTelefon(e.target.value)} />
            </Field>
            <Button
              variante="sekundaer"
              icon={Plus}
              disabled={!name.trim()}
              className="mb-0.5"
              onClick={() => {
                onHinzufuegen({
                  name: name.trim(),
                  firma_kuerzel: firma.trim(),
                  telefon: telefon.trim(),
                });
                setName("");
                setFirma("");
                setTelefon("");
              }}
            >
              Hinzufügen
            </Button>
          </div>
        )}
      </div>
    </Section>
  );
}

/* ───────────────────────────── Anlagen ───────────────────────────── */

function Anlagen({
  protokoll,
  gesperrt,
  beschaeftigt,
  onHochladen,
  onLoeschen,
}: {
  protokoll: Protokoll;
  gesperrt: boolean;
  beschaeftigt: string | null;
  onHochladen: (datei: File, bezeichnung: string) => void;
  onLoeschen: (id: number) => void;
}) {
  const [bezeichnung, setBezeichnung] = useState("Teilnehmerliste, unterschrieben");
  const eingabe = useRef<HTMLInputElement>(null);

  return (
    <Section
      titel="Anlagen"
      icon={Paperclip}
      offenStart={false}
      zusatz={`${protokoll.anlagen.length} Datei(en)`}
    >
      <div className="flex flex-col gap-3">
        <p className="text-[13px] text-ui-text-muted">
          Hier gehört die unterschriebene Teilnehmerliste hin: Protokoll
          erzeugen, die Teilnehmerliste ausdrucken, vor Ort unterschreiben
          lassen, einscannen und die Datei hier hochladen. Sie wird beim
          Erzeugen als eigene Seite hinten angefügt. PDF und Bilder gehen beide.
        </p>

        {protokoll.anlagen.map((anlage) => (
          <div
            key={anlage.id}
            className="flex items-center gap-2 rounded-ui border border-ui-line px-3 py-2 text-[13px]"
          >
            <Paperclip size={15} className="shrink-0 text-ui-text-faint" />
            <span className="min-w-0 flex-1 truncate">
              {anlage.bezeichnung || anlage.dateiname}
              <span className="ml-2 text-ui-text-faint">{anlage.dateiname}</span>
            </span>
            {!gesperrt && (
              <button
                type="button"
                onClick={() => onLoeschen(anlage.id)}
                className="text-ui-text-faint hover:text-ui-danger"
              >
                <Trash2 size={15} />
              </button>
            )}
          </div>
        ))}

        {!gesperrt && (
          <div className="grid items-end gap-2 sm:grid-cols-[2fr_auto]">
            <Field label="Bezeichnung (steht über der Seite)">
              <Input
                value={bezeichnung}
                onChange={(e) => setBezeichnung(e.target.value)}
              />
            </Field>
            <div className="mb-0.5">
              <input
                ref={eingabe}
                type="file"
                className="hidden"
                accept=".pdf,image/*"
                onChange={(e) => {
                  const datei = e.target.files?.[0];
                  if (datei) onHochladen(datei, bezeichnung);
                  e.target.value = "";
                }}
              />
              <Button
                variante="sekundaer"
                icon={Paperclip}
                onClick={() => eingabe.current?.click()}
                disabled={beschaeftigt === "anlage"}
              >
                {beschaeftigt === "anlage" && (
                  <Loader2 size={15} className="animate-spin" />
                )}
                Datei wählen
              </Button>
            </div>
          </div>
        )}
      </div>
    </Section>
  );
}

/* ───────────────────────────── Freigabe ───────────────────────────── */

function Abschluss({
  protokoll,
  beschaeftigt,
  onFreigeben,
  onNeuErzeugen,
  onHerunterladen,
}: {
  protokoll: Protokoll;
  beschaeftigt: string | null;
  onFreigeben: (trotzdem: boolean) => void;
  onNeuErzeugen: () => void;
  onHerunterladen: (alsPdf: boolean) => void;
}) {
  const [trotzdem, setTrotzdem] = useState(false);
  const offen = protokoll.anzahl_ungeprueft;
  const freigegeben = protokoll.status === "freigegeben";

  return (
    <Card className="p-4">
      <Bereichstitel>Freigabe und Dokument</Bereichstitel>
      <div className="flex flex-col gap-3">
        {!freigegeben ? (
          <>
            {offen > 0 ? (
              <Meldung art="hinweis">
                <div className="flex items-start gap-2">
                  <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                  <div className="flex flex-col gap-2">
                    <span>
                      {offen} Zeile(n) sind noch nicht geprüft. Bitte oben jede
                      Zeile ansehen und mit „Passt“ bestätigen — genau dafür gibt
                      es diesen Schritt.
                    </span>
                    <Checkbox
                      checked={trotzdem}
                      onChange={setTrotzdem}
                      label="Trotzdem freigeben — ich habe alles gelesen"
                    />
                  </div>
                </div>
              </Meldung>
            ) : (
              <Meldung art="erfolg">
                Alle Zeilen geprüft. Mit der Freigabe werden die Themen in die
                laufende Liste des Projekts fortgeschrieben und das Word-Dokument
                erzeugt.
              </Meldung>
            )}
            <div>
              <Button
                icon={Check}
                onClick={() => onFreigeben(trotzdem)}
                disabled={
                  beschaeftigt === "freigabe" ||
                  protokoll.themen_updates.length === 0 ||
                  (offen > 0 && !trotzdem)
                }
              >
                {beschaeftigt === "freigabe" && (
                  <Loader2 size={15} className="animate-spin" />
                )}
                Freigeben und Dokument erzeugen
              </Button>
            </div>
          </>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button
              icon={Download}
              onClick={() => onHerunterladen(false)}
              disabled={!protokoll.hat_dokument}
            >
              Word herunterladen
            </Button>
            {protokoll.hat_pdf && (
              <Button
                variante="sekundaer"
                icon={FileText}
                onClick={() => onHerunterladen(true)}
              >
                PDF
              </Button>
            )}
            <Button
              variante="sekundaer"
              icon={RefreshCw}
              onClick={onNeuErzeugen}
              disabled={beschaeftigt === "erzeugen"}
            >
              Neu erzeugen
            </Button>
          </div>
        )}
      </div>
    </Card>
  );
}
