"use client";

/**
 * Stammdaten der Baubesprechung: Kapitel und Projektbeteiligte.
 *
 * Beides gehört zum Projekt, nicht zu einer Sitzung.
 *
 *   Kapitel            die grauen Balkenzeilen im Protokoll und damit die
 *                      erste Zahl jeder Themennummer. Ohne Kapitel hat ein
 *                      neues Thema keine Nummer — deshalb steht hier der
 *                      Knopf, der sie aus den Gewerken erzeugt.
 *   Projektbeteiligte  die Abkürzungstabelle auf Seite 3 und zugleich die
 *                      Quelle für Firma und Telefonnummer der Teilnehmer.
 *                      tl;dv liefert nur Namen; alles Weitere kommt von hier.
 *
 * Die dritte Liste — die Themen selbst — wird bewusst nicht hier gepflegt.
 * Sie entsteht in den Protokollen und wird dort fortgeschrieben; eine zweite
 * Bearbeitungsstelle würde nur Stände auseinanderlaufen lassen.
 */

import { ListTree, Loader2, Plus, Trash2, Wand2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type {
  BesprechungsKapitel,
  BesprechungsThema,
  Projekt,
  Projektbeteiligter,
} from "@/lib/types";
import {
  Bereichstitel,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Meldung,
  Section,
} from "@/components/ui";

export function BesprechungStammdaten({ projekt }: { projekt: Projekt }) {
  const [kapitel, setKapitel] = useState<BesprechungsKapitel[]>([]);
  const [beteiligte, setBeteiligte] = useState<Projektbeteiligter[]>([]);
  const [themen, setThemen] = useState<BesprechungsThema[]>([]);
  const [laedt, setLaedt] = useState(true);
  const [fehler, setFehler] = useState<string | null>(null);
  const [beschaeftigt, setBeschaeftigt] = useState(false);

  const laden = useCallback(async () => {
    try {
      const [k, b, t] = await Promise.all([
        api.besprechungen.kapitel(projekt.id),
        api.besprechungen.beteiligte(projekt.id),
        api.besprechungen.themen(projekt.id, true),
      ]);
      setKapitel(k);
      setBeteiligte(b);
      setThemen(t);
      setFehler(null);
    } catch (f) {
      setFehler(f instanceof Error ? f.message : "Laden fehlgeschlagen.");
    } finally {
      setLaedt(false);
    }
  }, [projekt.id]);

  useEffect(() => {
    laden();
  }, [laden]);

  async function tun(arbeit: () => Promise<void>) {
    setBeschaeftigt(true);
    setFehler(null);
    try {
      await arbeit();
      await laden();
    } catch (f) {
      setFehler(f instanceof Error ? f.message : "Das hat nicht geklappt.");
    } finally {
      setBeschaeftigt(false);
    }
  }

  if (laedt) {
    return (
      <Card className="p-4">
        <div className="flex items-center gap-2 text-[13px] text-ui-text-muted">
          <Loader2 size={15} className="animate-spin" /> wird geladen…
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      <Kapitelliste
        kapitel={kapitel}
        projektId={projekt.id}
        beschaeftigt={beschaeftigt}
        onTun={tun}
      />

      <Beteiligtenliste
        beteiligte={beteiligte}
        projektId={projekt.id}
        beschaeftigt={beschaeftigt}
        onTun={tun}
      />

      <Themenliste themen={themen} />
    </div>
  );
}

/* ───────────────────────────── Kapitel ───────────────────────────── */

function Kapitelliste({
  kapitel,
  projektId,
  beschaeftigt,
  onTun,
}: {
  kapitel: BesprechungsKapitel[];
  projektId: number;
  beschaeftigt: boolean;
  onTun: (arbeit: () => Promise<void>) => void;
}) {
  const [nummer, setNummer] = useState("");
  const [titel, setTitel] = useState("");

  return (
    <Card className="p-4">
      <Bereichstitel
        aktion={
          <Button
            variante="sekundaer"
            icon={Wand2}
            disabled={beschaeftigt}
            onClick={() =>
              onTun(async () => {
                await api.besprechungen.kapitelAusGewerken(projektId);
              })
            }
          >
            Aus Gewerken erzeugen
          </Button>
        }
      >
        Kapitel — {kapitel.length}
      </Bereichstitel>

      <p className="mb-3 text-[13px] text-ui-text-muted">
        Kapitel 01 ist immer „Allgemein/ Projektorganisation“, danach kommt je
        Vergabeeinheit eines. „Aus Gewerken erzeugen“ ergänzt nur, was fehlt —
        umbenannte Kapitel bleiben unverändert.
      </p>

      {kapitel.length === 0 ? (
        <EmptyState>
          Noch keine Kapitel. Ohne Kapitel bekommt ein neues Thema keine Nummer.
        </EmptyState>
      ) : (
        <div className="flex flex-col divide-y divide-ui-line">
          {kapitel.map((k) => (
            <div key={k.id} className="flex items-center gap-3 py-2">
              <Input
                defaultValue={k.nummer}
                className="w-16"
                onBlur={(e) =>
                  e.target.value !== k.nummer &&
                  onTun(async () => {
                    await api.besprechungen.kapitelAendern(k.id, {
                      nummer: e.target.value,
                    });
                  })
                }
              />
              <Input
                defaultValue={k.titel}
                className="flex-1"
                onBlur={(e) =>
                  e.target.value !== k.titel &&
                  onTun(async () => {
                    await api.besprechungen.kapitelAendern(k.id, {
                      titel: e.target.value,
                    });
                  })
                }
              />
              <span className="w-24 shrink-0 text-right text-[12.5px] text-ui-text-faint">
                {k.anzahl_themen} Themen
              </span>
              <button
                type="button"
                title={
                  k.anzahl_themen
                    ? "Kapitel mit Themen lässt sich nicht löschen"
                    : "Kapitel löschen"
                }
                disabled={k.anzahl_themen > 0}
                onClick={() =>
                  onTun(async () => {
                    await api.besprechungen.kapitelLoeschen(k.id);
                  })
                }
                className="text-ui-text-faint hover:text-ui-danger disabled:opacity-30"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 flex items-end gap-2 border-t border-ui-line pt-3">
        <Field label="Nr." className="w-20">
          <Input
            value={nummer}
            onChange={(e) => setNummer(e.target.value)}
            placeholder="4."
          />
        </Field>
        <Field label="Titel" className="flex-1">
          <Input
            value={titel}
            onChange={(e) => setTitel(e.target.value)}
            placeholder="VE03 Fassade - …"
          />
        </Field>
        <Button
          variante="sekundaer"
          icon={Plus}
          disabled={!titel.trim() || beschaeftigt}
          className="mb-0.5"
          onClick={() =>
            onTun(async () => {
              await api.besprechungen.kapitelAnlegen({
                projekt_id: projektId,
                nummer: nummer.trim(),
                titel: titel.trim(),
              });
              setNummer("");
              setTitel("");
            })
          }
        >
          Anlegen
        </Button>
      </div>
    </Card>
  );
}

/* ───────────────────────────── Beteiligte ───────────────────────────── */

function Beteiligtenliste({
  beteiligte,
  projektId,
  beschaeftigt,
  onTun,
}: {
  beteiligte: Projektbeteiligter[];
  projektId: number;
  beschaeftigt: boolean;
  onTun: (arbeit: () => Promise<void>) => void;
}) {
  const [neu, setNeu] = useState({
    kuerzel: "",
    name: "",
    rolle: "",
    ansprechpartner: "",
    telefon: "",
  });

  const felder: {
    schluessel: keyof typeof neu;
    label: string;
    breite: string;
    platzhalter: string;
  }[] = [
    { schluessel: "kuerzel", label: "Kürzel", breite: "w-20", platzhalter: "SBH" },
    { schluessel: "name", label: "Firma / Büro", breite: "flex-1", platzhalter: "Schulbau Hamburg" },
    { schluessel: "rolle", label: "Rolle", breite: "flex-1", platzhalter: "Bauherr" },
    { schluessel: "ansprechpartner", label: "Ansprechpartner", breite: "flex-1", platzhalter: "Herr R. Melms" },
    { schluessel: "telefon", label: "Telefon", breite: "flex-1", platzhalter: "+49 40 …" },
  ];

  return (
    <Card className="p-4">
      <Bereichstitel>Projektbeteiligte — {beteiligte.length}</Bereichstitel>
      <p className="mb-3 text-[13px] text-ui-text-muted">
        Diese Liste wird als „Abkürzungen Projektbeteiligte“ auf Seite 3 des
        Protokolls gedruckt. Ansprechpartner und Telefon füllen außerdem die
        Teilnehmerliste — tl;dv liefert beides nicht.
      </p>

      {beteiligte.length === 0 ? (
        <EmptyState>
          Noch keine Projektbeteiligten. Ohne sie bleibt Seite 3 des Protokolls
          leer und die Analyse kann keine Zuständigen zuordnen.
        </EmptyState>
      ) : (
        <div className="flex flex-col divide-y divide-ui-line">
          {beteiligte.map((b) => (
            <div key={b.id} className="flex flex-wrap items-center gap-2 py-2">
              {felder.map((feld) => (
                <Input
                  key={feld.schluessel}
                  defaultValue={b[feld.schluessel] as string}
                  className={feld.breite}
                  onBlur={(e) =>
                    e.target.value !== b[feld.schluessel] &&
                    onTun(async () => {
                      await api.besprechungen.beteiligterAendern(b.id, {
                        [feld.schluessel]: e.target.value,
                      });
                    })
                  }
                />
              ))}
              <button
                type="button"
                onClick={() =>
                  onTun(async () => {
                    await api.besprechungen.beteiligterLoeschen(b.id);
                  })
                }
                className="text-ui-text-faint hover:text-ui-danger"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-ui-line pt-3">
        {felder.map((feld) => (
          <Field key={feld.schluessel} label={feld.label} className={feld.breite}>
            <Input
              value={neu[feld.schluessel]}
              placeholder={feld.platzhalter}
              onChange={(e) =>
                setNeu((alt) => ({ ...alt, [feld.schluessel]: e.target.value }))
              }
            />
          </Field>
        ))}
        <Button
          variante="sekundaer"
          icon={Plus}
          className="mb-0.5"
          disabled={!neu.kuerzel.trim() || !neu.name.trim() || beschaeftigt}
          onClick={() =>
            onTun(async () => {
              await api.besprechungen.beteiligterAnlegen({
                projekt_id: projektId,
                kuerzel: neu.kuerzel.trim().toUpperCase(),
                name: neu.name.trim(),
                rolle: neu.rolle.trim(),
                ansprechpartner: neu.ansprechpartner.trim(),
                telefon: neu.telefon.trim(),
              });
              setNeu({ kuerzel: "", name: "", rolle: "", ansprechpartner: "", telefon: "" });
            })
          }
        >
          Anlegen
        </Button>
      </div>
    </Card>
  );
}

/* ───────────────────────────── Themenliste ───────────────────────────── */

function Themenliste({ themen }: { themen: BesprechungsThema[] }) {
  return (
    <Section
      titel="Laufende Themenliste"
      icon={ListTree}
      offenStart={false}
      zusatz={`${themen.length} offen`}
    >
      <p className="mb-3 text-[13px] text-ui-text-muted">
        Nur zum Nachsehen: Das ist die Liste, die über alle Besprechungen hinweg
        weiterläuft. Geändert wird sie im jeweiligen Protokoll — ein Thema
        verschwindet hier erst, wenn es dort auf „erledigt“ gesetzt wurde.
      </p>
      {themen.length === 0 ? (
        <EmptyState>Keine offenen Themen.</EmptyState>
      ) : (
        <div className="flex flex-col divide-y divide-ui-line text-[13px]">
          {themen.map((t) => (
            <div key={t.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
              <span className="font-mono font-medium text-ui-text">
                {t.kennung} {t.zuletzt_bb != null ? String(t.zuletzt_bb).padStart(2, "0") : "—"}
              </span>
              <span className="min-w-0 flex-1 text-ui-text">
                {t.thema.split("\n")[0]}
              </span>
              {t.zustaendig && (
                <span className="text-ui-text-muted">{t.zustaendig.replace(/\n/g, " ")}</span>
              )}
              {t.bearb_bis && <span className="text-ui-text-muted">{t.bearb_bis}</span>}
              <span className="text-ui-text-faint">{t.status}</span>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}
