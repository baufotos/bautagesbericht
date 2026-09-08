"use client";

/**
 * Liste aller Beauftragungen mit dem Zustand ihrer Ablage.
 *
 * WAS DIE LISTE LEISTEN MUSS
 * ==========================
 * Der Projektordner entsteht im Hintergrund. Die eine Frage, mit der man
 * morgens hierher kommt, ist deshalb: Ist die Ablage durch, oder hängt etwas?
 * Genau das steht als Plakette an jeder Karte, und Fälle mit Fehler stehen
 * oben — nicht in der Reihenfolge des Eingangs, sondern in der Reihenfolge
 * dessen, was noch zu tun ist.
 *
 * Ein Fall ohne Standort ist kein Sonderfall: Ohne Anthropic-Schlüssel hat
 * jeder Upload zunächst leere Felder. Die Karte sagt dann, dass Angaben
 * fehlen, statt einen leeren Titel zu zeigen.
 */

import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  FolderOpen,
  Loader2,
  MapPin,
  Phone,
  Plus,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";

import type {
  McdonaldsFaehigkeiten,
  McdonaldsFall,
  OrdnerStatus,
} from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  LeerHinweis,
  Plakette,
} from "@/components/dashboard";
import { Button, Chip, ChipLeiste, Meldung, formatDatum } from "@/components/ui";

type Filter = "alle" | OrdnerStatus;

const STATUS_TEXT: Record<OrdnerStatus, string> = {
  ausstehend: "Ordner wird angelegt",
  angelegt: "Ordner angelegt",
  fehler: "Ordner offen",
};

const STATUS_ART: Record<OrdnerStatus, "ok" | "warn" | "gefahr"> = {
  ausstehend: "warn",
  angelegt: "ok",
  fehler: "gefahr",
};

/** Fehler zuerst, dann Ausstehende, dann Fertige — nach dem Handlungsbedarf. */
const RANG: Record<OrdnerStatus, number> = {
  fehler: 0,
  ausstehend: 1,
  angelegt: 2,
};

export function McdonaldsUebersicht({
  faelle,
  faehigkeiten,
  laedt = false,
  onOeffnen,
  onNeu,
  onAktualisieren,
}: {
  faelle: McdonaldsFall[];
  faehigkeiten: McdonaldsFaehigkeiten | null;
  laedt?: boolean;
  onOeffnen: (id: number) => void;
  onNeu: () => void;
  onAktualisieren: () => void;
}) {
  const [filter, setFilter] = useState<Filter>("alle");

  const zaehler = useMemo(() => {
    const werte: Record<OrdnerStatus, number> = {
      ausstehend: 0,
      angelegt: 0,
      fehler: 0,
    };
    for (const fall of faelle) werte[fall.ordner_status] += 1;
    return werte;
  }, [faelle]);

  const sichtbar = useMemo(() => {
    const gefiltert =
      filter === "alle"
        ? faelle
        : faelle.filter((f) => f.ordner_status === filter);
    return [...gefiltert].sort((a, b) => {
      const rang = RANG[a.ordner_status] - RANG[b.ordner_status];
      if (rang !== 0) return rang;
      return b.erstellt_am.localeCompare(a.erstellt_am);
    });
  }, [faelle, filter]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <ChipLeiste>
          <Chip aktiv={filter === "alle"} onClick={() => setFilter("alle")}>
            alle ({faelle.length})
          </Chip>
          <Chip aktiv={filter === "fehler"} onClick={() => setFilter("fehler")}>
            offen ({zaehler.fehler})
          </Chip>
          <Chip
            aktiv={filter === "ausstehend"}
            onClick={() => setFilter("ausstehend")}
          >
            in Arbeit ({zaehler.ausstehend})
          </Chip>
          <Chip aktiv={filter === "angelegt"} onClick={() => setFilter("angelegt")}>
            angelegt ({zaehler.angelegt})
          </Chip>
        </ChipLeiste>
        <div className="ml-auto flex items-center gap-2">
          <Button
            variante="still"
            icon={laedt ? Loader2 : RefreshCw}
            onClick={onAktualisieren}
          >
            Aktualisieren
          </Button>
          <Button icon={Plus} onClick={onNeu}>
            Beauftragung erfassen
          </Button>
        </div>
      </div>

      {/* Solange die Referenztabelle fehlt, heißt jeder Ordner "XXX_…". Das
          ist behebbar, aber nur, wenn es jemand erfährt. */}
      {faehigkeiten && faehigkeiten.unlocode_eintraege === 0 && (
        <Meldung art="hinweis">
          Die UN/LOCODE-Tabelle ist noch nicht hochgeladen. Ordner heißen
          deshalb „XXX_…“ statt mit dem amtlichen Ortscode. Die Tabelle
          (Anlage 5.1 des Projekthandbuchs) lässt sich in einer geöffneten
          Beauftragung hochladen.
        </Meldung>
      )}
      {faehigkeiten && !faehigkeiten.ordner_h && (
        <Meldung art="hinweis">
          Der Basispfad für das Netzlaufwerk ist nicht eingetragen — es werden
          noch keine Projektordner angelegt. In{" "}
          <span className="font-mono">einstellungen.txt</span> bei
          „mcdonalds_ordner_h=“ hinterlegen.
        </Meldung>
      )}

      {sichtbar.length === 0 ? (
        <LeerHinweis>
          {faelle.length === 0
            ? "Noch keine Beauftragung erfasst. Lade eine als .eml exportierte Auftragsmail hoch — oder trage eine telefonische Beauftragung von Hand ein."
            : "In dieser Auswahl ist nichts."}
        </LeerHinweis>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {sichtbar.map((fall) => (
            <FallKarte
              key={fall.id}
              fall={fall}
              onOeffnen={() => onOeffnen(fall.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function FallKarte({
  fall,
  onOeffnen,
}: {
  fall: McdonaldsFall;
  onOeffnen: () => void;
}) {
  const titel =
    fall.standort_name || fall.ordner_name || fall.standort_ort || "Ohne Standort";
  const StatusIcon =
    fall.ordner_status === "angelegt"
      ? CheckCircle2
      : fall.ordner_status === "fehler"
      ? AlertTriangle
      : Loader2;

  return (
    <Karte>
      <KarteKopf
        titel={titel}
        icon={fall.quelle === "telefon" ? Phone : FileText}
        unterzeile={
          <>
            {fall.leistungsphase ? `LPH ${fall.leistungsphase} · ` : ""}
            {formatDatum(fall.erstellt_am)}
            {fall.analysiert_am ? " · KI-Analyse" : " · von Hand"}
          </>
        }
        aktion={
          <Plakette art={STATUS_ART[fall.ordner_status]}>
            {STATUS_TEXT[fall.ordner_status]}
          </Plakette>
        }
      />
      <KarteInhalt className="flex flex-col gap-2">
        {fall.standort_adresse ? (
          <div className="inline-flex items-start gap-1.5 text-[12px] text-app-text-still">
            <MapPin size={13} className="mt-0.5 shrink-0" />
            <span className="min-w-0">{fall.standort_adresse}</span>
          </div>
        ) : (
          <div className="inline-flex items-center gap-1.5 text-[12px] text-app-warn">
            <AlertTriangle size={13} className="shrink-0" />
            Angaben fehlen — bitte öffnen und nachtragen.
          </div>
        )}

        {fall.ordner_name && (
          <div className="inline-flex items-center gap-1.5 text-[12px] text-app-text-still">
            <FolderOpen size={13} className="shrink-0" />
            <span className="truncate font-mono">{fall.ordner_name}</span>
          </div>
        )}

        {fall.angebote.length > 0 && (
          <div className="inline-flex items-center gap-1.5 text-[12px] text-app-text-still">
            <Sparkles size={13} className="shrink-0" />
            {fall.angebote.length} Angebot(e)
            {fall.angebote.some((a) => a.mail_versendet_am)
              ? " · Entwurf erstellt"
              : ""}
          </div>
        )}

        {fall.ordner_status === "fehler" && fall.fehlermeldung && (
          <p className="text-[12px] leading-relaxed text-app-gefahr">
            {fall.fehlermeldung}
          </p>
        )}

        <div className="flex items-center justify-between gap-2 border-t border-app-linie pt-2">
          <StatusIcon
            size={14}
            className={`shrink-0 text-app-text-leise ${
              fall.ordner_status === "ausstehend" ? "animate-spin" : ""
            }`}
          />
          <Button variante="sekundaer" onClick={onOeffnen}>
            Öffnen
          </Button>
        </div>
      </KarteInhalt>
    </Karte>
  );
}
