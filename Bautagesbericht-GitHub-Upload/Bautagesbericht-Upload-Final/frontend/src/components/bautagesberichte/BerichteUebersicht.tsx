"use client";

/**
 * Übersicht der eingereichten Bautagesberichte.
 *
 * Bewusst eine Hol-Ansicht: Man schaut selbst nach, statt auf eine
 * Benachrichtigung zu warten. Deshalb steht oben, wie viele Berichte gerade
 * noch in Arbeit sind — das ist die einzige Information, die man sonst übersieht.
 *
 * Warnungen aus der automatischen Auswertung sind aufklappbar. Wartet ein
 * Bericht auf Bestätigung, wird er direkt hier freigegeben ("Trotzdem
 * erstellen") — genau wie in der ersten Fassung der App.
 */

import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  Info,
  Loader2,
} from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { formatDatumIso, relativeZeit } from "@/lib/formate";
import type { Einreichung } from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  KartenGitter,
  Kennzahl,
  LeerHinweis,
} from "@/components/dashboard";
import { Button, Chip, ChipLeiste, Meldung } from "@/components/ui";
import { BerichtStatus } from "./BerichtEinreichen";

/** Status, in denen noch etwas passieren muss. */
const OFFENE_STATUS = ["eingereicht", "wird_verarbeitet", "wartet_auf_bestaetigung"];

export function BerichteUebersicht({
  einreichungen,
  onAendern,
}: {
  einreichungen: Einreichung[];
  onAendern: () => void;
}) {
  const [filter, setFilter] = useState<"alle" | "offen" | "fertig">("alle");
  const [fehler, setFehler] = useState<string | null>(null);

  const offen = einreichungen.filter((e) => OFFENE_STATUS.includes(e.status));
  const fertig = einreichungen.filter((e) => e.status === "abgeschlossen");
  const gescheitert = einreichungen.filter((e) => e.status === "fehlgeschlagen");
  const wartend = einreichungen.filter((e) => e.status === "wartet_auf_bestaetigung");

  const gefiltert = einreichungen.filter((e) => {
    if (filter === "offen") return OFFENE_STATUS.includes(e.status);
    if (filter === "fertig") return !OFFENE_STATUS.includes(e.status);
    return true;
  });

  return (
    <div className="flex flex-col gap-3">
      <KartenGitter spalten={4}>
        <Karte>
          <KarteInhalt className="pt-4">
            <Kennzahl wert={einreichungen.length} label="Berichte insgesamt" />
          </KarteInhalt>
        </Karte>
        <Karte>
          <KarteInhalt className="pt-4">
            <Kennzahl
              wert={offen.length}
              label="in Arbeit"
              hinweis={
                wartend.length > 0
                  ? `${wartend.length} wartet auf Bestätigung`
                  : undefined
              }
            />
          </KarteInhalt>
        </Karte>
        <Karte>
          <KarteInhalt className="pt-4">
            <Kennzahl wert={fertig.length} label="fertig" art="ok" />
          </KarteInhalt>
        </Karte>
        <Karte>
          <KarteInhalt className="pt-4">
            <Kennzahl
              wert={gescheitert.length}
              label="fehlgeschlagen"
              art={gescheitert.length > 0 ? "gefahr" : "normal"}
            />
          </KarteInhalt>
        </Karte>
      </KartenGitter>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      <ChipLeiste>
        <Chip aktiv={filter === "alle"} onClick={() => setFilter("alle")}>
          Alle ({einreichungen.length})
        </Chip>
        <Chip aktiv={filter === "offen"} onClick={() => setFilter("offen")}>
          In Arbeit ({offen.length})
        </Chip>
        <Chip aktiv={filter === "fertig"} onClick={() => setFilter("fertig")}>
          Abgeschlossen ({einreichungen.length - offen.length})
        </Chip>
      </ChipLeiste>

      <Karte>
        <KarteKopf
          titel="Eingereichte Berichte"
          unterzeile="Neueste zuerst — Download sobald das Word-Dokument fertig ist"
          icon={FileText}
        />
        {gefiltert.length === 0 ? (
          <KarteInhalt>
            <LeerHinweis>Keine Berichte in dieser Ansicht.</LeerHinweis>
          </KarteInhalt>
        ) : (
          <div className="border-t border-app-linie">
            {gefiltert.map((e) => (
              <BerichtZeile
                key={e.id}
                einreichung={e}
                onAendern={onAendern}
                onFehler={setFehler}
              />
            ))}
          </div>
        )}
      </Karte>
    </div>
  );
}

function BerichtZeile({
  einreichung,
  onAendern,
  onFehler,
}: {
  einreichung: Einreichung;
  onAendern: () => void;
  onFehler: (text: string | null) => void;
}) {
  const [offen, setOffen] = useState(false);
  const [bestaetigt, setBestaetigt] = useState(false);

  const hatWarnungen = einreichung.warnungen.length > 0;
  // Aufhaltende Meldungen von bloßen Hinweisen trennen — siehe unten.
  const blockierende = einreichung.warnungen.filter((w) => w.blockiert !== false);
  const hinweise = einreichung.warnungen.filter((w) => w.blockiert === false);
  const inArbeit =
    einreichung.status === "eingereicht" || einreichung.status === "wird_verarbeitet";
  const brauchtBestaetigung = einreichung.status === "wartet_auf_bestaetigung";

  async function bestaetigen() {
    setBestaetigt(true);
    onFehler(null);
    try {
      await api.einreichungen.bestaetigen(einreichung.id);
      onAendern();
    } catch (err) {
      onFehler(err instanceof Error ? err.message : "Bestätigen fehlgeschlagen.");
    } finally {
      setBestaetigt(false);
    }
  }

  return (
    <div className="border-b border-app-linie last:border-b-0">
      <div className="flex items-center gap-2.5 px-4 py-2.5">
        <button
          type="button"
          onClick={() => hatWarnungen && setOffen((v) => !v)}
          className={`flex min-w-0 flex-1 items-center gap-2 text-left ${
            hatWarnungen ? "cursor-pointer" : "cursor-default"
          }`}
          aria-expanded={hatWarnungen ? offen : undefined}
        >
          {hatWarnungen ? (
            offen ? (
              <ChevronDown size={14} className="shrink-0 text-app-text-leise" />
            ) : (
              <ChevronRight size={14} className="shrink-0 text-app-text-leise" />
            )
          ) : (
            <span className="w-3.5 shrink-0" />
          )}
          <span className="min-w-0">
            <span className="block truncate text-[12.5px] text-app-text">
              {einreichung.projekt_name} · {formatDatumIso(einreichung.datum)}
            </span>
            <span className="block truncate text-[11.5px] text-app-text-still">
              {einreichung.empfaenger_label} · eingereicht{" "}
              {relativeZeit(einreichung.eingereicht_am)}
            </span>
          </span>
        </button>

        <div className="flex shrink-0 items-center gap-2">
          {inArbeit && (
            <Loader2 size={13} className="animate-spin text-app-text-leise" />
          )}
          {/* Das gelbe Dreieck bleibt echten Warnungen vorbehalten. Ein
              Hinweis zum Gegenlesen bekommt ein stilles Zeichen — sonst sieht
              eine fehlerfrei gelesene Woche aus wie fünf Probleme. */}
          {blockierende.length > 0 ? (
            <span className="inline-flex items-center gap-1 text-[11.5px] text-app-warn">
              <AlertTriangle size={13} />
              {blockierende.length}
            </span>
          ) : hinweise.length > 0 ? (
            <span
              className="inline-flex items-center text-app-text-leise"
              title="Aus einem Scan gelesen — bitte gegenlesen"
            >
              <Info size={13} />
            </span>
          ) : null}
          <BerichtStatus status={einreichung.status} />
          {einreichung.status === "abgeschlossen" && (
            <a
              href={api.einreichungen.downloadUrl(einreichung.id)}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Word-Dokument herunterladen"
              title="Word-Dokument herunterladen"
              className="cursor-pointer p-1 text-app-akzent transition-colors hover:text-app-akzent-hover"
            >
              <Download size={15} />
            </a>
          )}
        </div>
      </div>

      {/* Zwei Arten von Meldung, zwei Darstellungen. Eine fehlende Datei ist
          etwas anderes als "aus einem Scan gelesen": Das erste hält den
          Bericht auf, das zweite ist eine Bitte ums Gegenlesen. Beides gelb
          und mit Knopf zu zeigen hat dazu geführt, dass bei einer gescannten
          Woche fünf Mal dieselbe Warnung stand, obwohl nichts fehlte. */}
      {(offen || brauchtBestaetigung) && blockierende.length > 0 && (
        <div className="border-t border-app-linie bg-app-warn-sanft/50 px-4 py-3">
          <div className="text-[10px] uppercase tracking-[0.1em] text-app-warn">
            Warnungen der automatischen Auswertung
          </div>
          <ul className="mt-1.5 flex flex-col gap-1">
            {blockierende.map((warnung, i) => (
              <li key={i} className="text-[12px] text-app-text">
                <span className="font-medium">{warnung.feld}:</span> {warnung.problem}
                {warnung.quelle_datei && (
                  <span className="text-app-text-still"> ({warnung.quelle_datei})</span>
                )}
              </li>
            ))}
          </ul>
          {brauchtBestaetigung && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button onClick={bestaetigen} disabled={bestaetigt}>
                {bestaetigt ? (
                  <>
                    <Loader2 size={14} className="animate-spin" /> Wird erstellt…
                  </>
                ) : (
                  "Trotzdem erstellen"
                )}
              </Button>
              <span className="text-[12px] text-app-text-still">
                Der Bericht wird mit den erkannten Angaben erzeugt.
              </span>
            </div>
          )}
        </div>
      )}

      {offen && hinweise.length > 0 && (
        <div className="border-t border-app-linie px-4 py-2.5">
          {hinweise.map((hinweis, i) => (
            <p key={i} className="text-[12px] text-app-text-still">
              {hinweis.problem}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
