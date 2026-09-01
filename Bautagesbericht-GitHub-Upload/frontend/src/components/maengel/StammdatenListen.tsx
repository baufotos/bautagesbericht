"use client";

/**
 * Die konfigurierbaren Wertelisten des Mängelmoduls: Typ, Status,
 * Rückmeldestatus, Bearbeiter.
 *
 * Diese Listen gehören dem Büro, nicht dem Code — wer einen weiteren Typ
 * braucht, legt ihn hier an, ohne dass etwas neu ausgeliefert werden muss.
 * Ein gelöschter Eintrag verschwindet nur aus der Auswahl; bereits erfasste
 * Mängel behalten ihren Wert (im Mangel steht die Bezeichnung als Text).
 */

import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import type { MangelStammdaten } from "@/lib/types";
import {
  Bereichstitel,
  Button,
  Card,
  Input,
  Meldung,
  Section,
  StatusBadge,
} from "@/components/ui";

export function StammdatenListen({
  stammdaten,
  onAendern,
}: {
  stammdaten: MangelStammdaten | null;
  onAendern: () => void;
}) {
  const [fehler, setFehler] = useState<string | null>(null);

  async function fuehreAus(arbeit: () => Promise<unknown>) {
    setFehler(null);
    try {
      await arbeit();
      onAendern();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Aktion fehlgeschlagen");
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <Bereichstitel>Wertelisten</Bereichstitel>
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      <Section
        titel="Typ"
        offenStart={false}
        zusatz={`${stammdaten?.typen.length ?? 0} Einträge`}
      >
        <ListenPflege
          eintraege={(stammdaten?.typen || []).map((t) => ({
            id: t.id,
            text: `${t.sortierung} ${t.bezeichnung}`,
          }))}
          platzhalter="Neuer Typ, z. B. Restleistung"
          onAnlegen={(bezeichnung) =>
            fuehreAus(() => api.mangelStammdaten.createTyp({ bezeichnung }))
          }
          onLoeschen={(id) =>
            fuehreAus(() => api.mangelStammdaten.deleteTyp(id))
          }
        />
      </Section>

      <Section
        titel="Status"
        offenStart={false}
        zusatz={`${stammdaten?.status.length ?? 0} Einträge`}
      >
        <StatusPflege stammdaten={stammdaten} fuehreAus={fuehreAus} />
      </Section>

      <Section
        titel="Rückmeldung"
        offenStart={false}
        zusatz={`${stammdaten?.rueckmeldung_status.length ?? 0} Einträge`}
      >
        <ListenPflege
          eintraege={(stammdaten?.rueckmeldung_status || []).map((r) => ({
            id: r.id,
            text: r.bezeichnung,
          }))}
          platzhalter="Neuer Rückmeldestatus"
          onAnlegen={(bezeichnung) =>
            fuehreAus(() => api.mangelStammdaten.createRueckmeldung({ bezeichnung }))
          }
          onLoeschen={(id) =>
            fuehreAus(() => api.mangelStammdaten.deleteRueckmeldung(id))
          }
        />
      </Section>

      <Section
        titel="Bearbeiter"
        offenStart={false}
        zusatz={`${stammdaten?.bearbeiter.length ?? 0} Einträge`}
      >
        <ListenPflege
          eintraege={(stammdaten?.bearbeiter || []).map((b) => ({
            id: b.id,
            text: b.email ? `${b.name} · ${b.email}` : b.name,
          }))}
          platzhalter="Name des Bearbeiters"
          onAnlegen={(name) =>
            fuehreAus(() => api.mangelStammdaten.createBearbeiter({ name }))
          }
          onLoeschen={(id) =>
            fuehreAus(() => api.mangelStammdaten.deleteBearbeiter(id))
          }
          hinweis="Auswahl für „Aufgenommen von“ und das User-Feld am Mangel."
        />

        {/* Kürzel und Durchwahl stehen in der Kopfzeile jedes
            Besprechungsprotokolls ("Ze: kbl   T - 22"). Einmal hier gepflegt,
            füllt sich jedes neue Protokoll selbst. */}
        {(stammdaten?.bearbeiter.length ?? 0) > 0 && (
          <div className="mt-4 border-t border-ui-line pt-3">
            <p className="mb-2 text-[12.5px] text-ui-text-muted">
              Kürzel und Durchwahl für die Kopfzeile des
              Besprechungsprotokolls — „Ze: kbl“ und „T - 22“.
            </p>
            <div className="flex flex-col gap-2">
              {(stammdaten?.bearbeiter || []).map((b) => (
                <div
                  key={b.id}
                  className="flex flex-wrap items-center gap-2 text-[13px]"
                >
                  <span className="min-w-[9rem] flex-1 text-ui-text">{b.name}</span>
                  <input
                    defaultValue={b.kuerzel}
                    placeholder="Kürzel"
                    className="w-24 rounded-ui border border-ui-line bg-ui-surface px-2 py-1"
                    onBlur={(e) =>
                      e.target.value !== b.kuerzel &&
                      fuehreAus(() =>
                        api.mangelStammdaten.updateBearbeiter(b.id, {
                          kuerzel: e.target.value,
                        })
                      )
                    }
                  />
                  <input
                    defaultValue={b.durchwahl}
                    placeholder="Durchwahl"
                    className="w-28 rounded-ui border border-ui-line bg-ui-surface px-2 py-1"
                    onBlur={(e) =>
                      e.target.value !== b.durchwahl &&
                      fuehreAus(() =>
                        api.mangelStammdaten.updateBearbeiter(b.id, {
                          durchwahl: e.target.value,
                        })
                      )
                    }
                  />
                </div>
              ))}
            </div>
          </div>
        )}
      </Section>
    </div>
  );
}

function ListenPflege({
  eintraege,
  platzhalter,
  onAnlegen,
  onLoeschen,
  hinweis,
}: {
  eintraege: { id: number; text: string }[];
  platzhalter: string;
  onAnlegen: (bezeichnung: string) => void;
  onLoeschen: (id: number) => void;
  hinweis?: string;
}) {
  const [neu, setNeu] = useState("");

  function anlegen() {
    if (!neu.trim()) return;
    onAnlegen(neu.trim());
    setNeu("");
  }

  return (
    <div className="flex flex-col gap-2">
      {hinweis && <p className="text-[12px] text-ui-text-muted">{hinweis}</p>}
      {eintraege.map((eintrag) => (
        <div
          key={eintrag.id}
          className="flex items-center justify-between gap-3 rounded-ui-sm border border-ui-line px-3 py-1.5 text-[13px]"
        >
          <span className="truncate">{eintrag.text}</span>
          <button
            type="button"
            onClick={() => onLoeschen(eintrag.id)}
            aria-label={`${eintrag.text} entfernen`}
            className="shrink-0 cursor-pointer text-ui-text-faint transition-colors hover:text-ui-danger"
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}
      <div className="flex gap-2">
        <Input
          value={neu}
          onChange={(e) => setNeu(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && anlegen()}
          placeholder={platzhalter}
        />
        <Button icon={Plus} onClick={anlegen} disabled={!neu.trim()}>
          Anlegen
        </Button>
      </div>
    </div>
  );
}

function StatusPflege({
  stammdaten,
  fuehreAus,
}: {
  stammdaten: MangelStammdaten | null;
  fuehreAus: (arbeit: () => Promise<unknown>) => void;
}) {
  const [bezeichnung, setBezeichnung] = useState("");
  const [farbe, setFarbe] = useState("#1D4ED8");
  const [abgeschlossen, setAbgeschlossen] = useState(false);

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[12px] text-ui-text-muted">
        Die Farbe erscheint als Punkt im Status-Badge der Übersicht. „Gilt als
        abgeschlossen“ steuert die Überfälligkeits-Rechnung: In einem solchen
        Status ist ein Mangel nie überfällig.
      </p>

      {(stammdaten?.status || []).map((status) => (
        <div
          key={status.id}
          className="flex items-center justify-between gap-3 rounded-ui-sm border border-ui-line px-3 py-1.5"
        >
          <span className="flex items-center gap-2.5">
            <span className="font-mono text-[11px] text-ui-text-muted">
              {status.sortierung}
            </span>
            <StatusBadge text={status.bezeichnung} farbe={status.farbe} klein />
            {status.ist_abgeschlossen && (
              <span className="text-[11.5px] text-ui-text-muted">
                gilt als abgeschlossen
              </span>
            )}
          </span>
          <button
            type="button"
            onClick={() => fuehreAus(() => api.mangelStammdaten.deleteStatus(status.id))}
            aria-label={`${status.bezeichnung} entfernen`}
            className="shrink-0 cursor-pointer text-ui-text-faint transition-colors hover:text-ui-danger"
          >
            <Trash2 size={14} />
          </button>
        </div>
      ))}

      <Card className="flex flex-wrap items-center gap-2 p-2.5">
        <Input
          className="w-auto min-w-[180px] flex-1"
          value={bezeichnung}
          onChange={(e) => setBezeichnung(e.target.value)}
          placeholder="Neuer Status"
        />
        <input
          type="color"
          value={farbe}
          onChange={(e) => setFarbe(e.target.value)}
          className="size-9 shrink-0 cursor-pointer rounded-ui-sm border border-ui-line bg-ui-surface"
          aria-label="Farbe des Status"
        />
        <label className="flex shrink-0 items-center gap-2 text-[12.5px]">
          <input
            type="checkbox"
            checked={abgeschlossen}
            onChange={(e) => setAbgeschlossen(e.target.checked)}
            className="size-4 accent-ui-accent"
          />
          gilt als abgeschlossen
        </label>
        <Button
          icon={Plus}
          disabled={!bezeichnung.trim()}
          onClick={() => {
            fuehreAus(() =>
              api.mangelStammdaten.createStatus({
                bezeichnung: bezeichnung.trim(),
                farbe,
                ist_abgeschlossen: abgeschlossen,
              })
            );
            setBezeichnung("");
            setAbgeschlossen(false);
          }}
        >
          Anlegen
        </Button>
      </Card>
    </div>
  );
}
