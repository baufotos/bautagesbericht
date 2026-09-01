"use client";

/**
 * Die Protokolle eines Projekts: Liste, Anlegen, Öffnen.
 *
 * Der Hinweis über der Liste ist wichtiger, als er aussieht: Ein neues
 * Protokoll erbt die offenen Punkte des letzten. Wer das nicht weiß, legt aus
 * Versehen eine zweite Themenliste an — und genau das soll die Funktion
 * verhindern.
 */

import { CalendarPlus, FileText, Loader2, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Bearbeiter, Projekt, ProtokollListItem } from "@/lib/types";
import {
  Bereichstitel,
  Button,
  Card,
  Checkbox,
  EmptyState,
  Field,
  Input,
  Meldung,
  Select,
  formatDatum,
  heuteIso,
} from "@/components/ui";
import { ProtokollBearbeiten } from "./ProtokollBearbeiten";

export function BesprechungenUebersicht({
  projekt,
  bearbeiter,
}: {
  projekt: Projekt;
  bearbeiter: Bearbeiter[];
}) {
  const [protokolle, setProtokolle] = useState<ProtokollListItem[]>([]);
  const [offenesProtokoll, setOffenesProtokoll] = useState<number | null>(null);
  const [laedt, setLaedt] = useState(true);
  const [fehler, setFehler] = useState<string | null>(null);
  const [formularOffen, setFormularOffen] = useState(false);

  const laden = useCallback(async () => {
    setLaedt(true);
    try {
      setProtokolle(await api.besprechungen.list(projekt.id));
      setFehler(null);
    } catch (f) {
      setFehler(f instanceof Error ? f.message : "Liste konnte nicht geladen werden.");
    } finally {
      setLaedt(false);
    }
  }, [projekt.id]);

  useEffect(() => {
    laden();
  }, [laden]);

  if (offenesProtokoll !== null) {
    return (
      <ProtokollBearbeiten
        protokollId={offenesProtokoll}
        onZurueck={() => {
          setOffenesProtokoll(null);
          laden();
        }}
        onGeaendert={laden}
      />
    );
  }

  const letztes = protokolle[0];

  return (
    <div className="flex flex-col gap-4">
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      <Card className="p-4">
        <Bereichstitel
          aktion={
            <Button
              variante={protokolle.length ? "sekundaer" : "primaer"}
              icon={CalendarPlus}
              onClick={() => setFormularOffen((o) => !o)}
            >
              Neue Besprechung
            </Button>
          }
        >
          Protokolle — {projekt.name}
        </Bereichstitel>

        {formularOffen && (
          <NeuesProtokoll
            projekt={projekt}
            bearbeiter={bearbeiter}
            naechsteNummer={(letztes?.nummer ?? 0) + 1}
            hatVorgaenger={Boolean(letztes)}
            onAbbrechen={() => setFormularOffen(false)}
            onAngelegt={(id) => {
              setFormularOffen(false);
              setOffenesProtokoll(id);
              laden();
            }}
          />
        )}

        {laedt ? (
          <div className="flex items-center gap-2 text-[13px] text-ui-text-muted">
            <Loader2 size={15} className="animate-spin" /> wird geladen…
          </div>
        ) : protokolle.length === 0 ? (
          <EmptyState>
            Für dieses Projekt gibt es noch kein Baubesprechungsprotokoll. Das
            erste legt die Themenliste an, jedes weitere schreibt sie fort.
          </EmptyState>
        ) : (
          <div className="flex flex-col divide-y divide-ui-line">
            {protokolle.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setOffenesProtokoll(p.id)}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 px-1 py-3 text-left hover:bg-ui-surface-muted"
              >
                <span className="font-mono text-[13px] font-medium text-ui-text">
                  Nr. {p.nummer}
                </span>
                <span className="text-[13px] text-ui-text">
                  {formatDatum(p.besprechungsdatum)}
                </span>
                <span className="text-[12.5px] text-ui-text-muted">
                  {p.anzahl_themen} Themen · {p.anzahl_offen} offen ·{" "}
                  {p.anzahl_teilnehmer} Teilnehmer
                </span>
                <span className="ml-auto flex items-center gap-2">
                  {p.anzahl_ungeprueft > 0 && (
                    <span className="rounded bg-ui-warn-soft px-1.5 py-0.5 text-[12px] text-ui-warn">
                      {p.anzahl_ungeprueft} zu prüfen
                    </span>
                  )}
                  {p.status === "freigegeben" ? (
                    <span className="rounded bg-ui-ok-soft px-1.5 py-0.5 text-[12px] text-ui-ok">
                      freigegeben
                    </span>
                  ) : (
                    <span className="rounded bg-ui-surface-muted px-1.5 py-0.5 text-[12px] text-ui-text-muted">
                      Entwurf
                    </span>
                  )}
                  {p.hat_dokument && (
                    <FileText size={15} className="text-ui-text-faint" />
                  )}
                </span>
              </button>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function NeuesProtokoll({
  projekt,
  bearbeiter,
  naechsteNummer,
  hatVorgaenger,
  onAbbrechen,
  onAngelegt,
}: {
  projekt: Projekt;
  bearbeiter: Bearbeiter[];
  naechsteNummer: number;
  hatVorgaenger: boolean;
  onAbbrechen: () => void;
  onAngelegt: (id: number) => void;
}) {
  const [datum, setDatum] = useState(heuteIso());
  const [ort, setOrt] = useState("");
  const [leistung, setLeistung] = useState("Baubesprechung");
  const [erstellerId, setErstellerId] = useState<number | "">("");
  const [uebernehmen, setUebernehmen] = useState(true);
  const [speichert, setSpeichert] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  async function anlegen() {
    setSpeichert(true);
    setFehler(null);
    try {
      const person = bearbeiter.find((b) => b.id === erstellerId);
      const neu = await api.besprechungen.create({
        projekt_id: projekt.id,
        besprechungsdatum: datum,
        besprechungsort: ort.trim(),
        leistung: leistung.trim() || "Baubesprechung",
        ersteller_id: typeof erstellerId === "number" ? erstellerId : null,
        ersteller_name: person?.name ?? "",
        ersteller_email: person?.email ?? "",
        offene_punkte_uebernehmen: uebernehmen,
      });
      onAngelegt(neu.id);
    } catch (f) {
      setFehler(f instanceof Error ? f.message : "Anlegen fehlgeschlagen.");
    } finally {
      setSpeichert(false);
    }
  }

  return (
    <div className="mb-4 flex flex-col gap-3 rounded-ui border border-ui-line bg-ui-surface-muted p-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Besprechungsdatum">
          <Input type="date" value={datum} onChange={(e) => setDatum(e.target.value)} />
        </Field>
        <Field label="Protokoll-Nr." hinweis="wird fortlaufend je Projekt vergeben">
          <Input value={naechsteNummer} readOnly />
        </Field>
        <Field label="Besprechungsort">
          <Input
            value={ort}
            onChange={(e) => setOrt(e.target.value)}
            placeholder="Weidenstieg 29, Baufeld"
          />
        </Field>
        <Field label="Leistung">
          <Input value={leistung} onChange={(e) => setLeistung(e.target.value)} />
        </Field>
        <Field label="Aufgestellt durch" hinweis="Kürzel und Durchwahl aus den Stammdaten">
          <Select
            value={erstellerId}
            onChange={(e) =>
              setErstellerId(e.target.value ? Number(e.target.value) : "")
            }
          >
            <option value="">— bitte wählen —</option>
            {bearbeiter.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {hatVorgaenger && (
        <Checkbox
          checked={uebernehmen}
          onChange={setUebernehmen}
          label="Offene Punkte aus dem letzten Protokoll übernehmen (empfohlen)"
        />
      )}
      {hatVorgaenger && !uebernehmen && (
        <Meldung art="hinweis">
          Ohne Übernahme beginnt dieses Protokoll leer — die laufenden Themen des
          Projekts tauchen dann nicht auf. Das ist fast nie gewollt.
        </Meldung>
      )}
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      <div className="flex gap-2">
        <Button icon={Plus} onClick={anlegen} disabled={speichert}>
          {speichert && <Loader2 size={15} className="animate-spin" />}
          Anlegen und öffnen
        </Button>
        <Button variante="still" onClick={onAbbrechen}>
          Abbrechen
        </Button>
      </div>
    </div>
  );
}
