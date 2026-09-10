"use client";

/**
 * Liste aller McDonald's-Standorte mit dem Zustand ihrer Ablage.
 *
 * WAS DIE LISTE LEISTEN MUSS
 * ==========================
 * Die eine Frage, mit der man morgens hierher kommt: Wo fehlt noch etwas?
 * Deshalb stehen Standorte mit Handlungsbedarf oben — nicht in der
 * Reihenfolge des Eingangs.
 *
 * „VORBEREITET" IST KEIN FEHLER
 * =============================
 * Auf der Büro-Website ist es der Normalzustand: Ein Dienst im Internet
 * erreicht das Projektlaufwerk im Büronetz nicht. Name und Struktur des
 * Ordners stehen fest, angelegt wird er von einem Rechner im Büro. Das wird
 * ruhig als Zustand gezeigt und nicht als Störung — wer fünfzigmal „Fehler"
 * liest, schaut beim echten Fehler nicht mehr hin.
 */

import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileText,
  FolderOpen,
  Loader2,
  MapPin,
  Plus,
  RefreshCw,
  Send,
} from "lucide-react";
import { useMemo, useState } from "react";

import type { McdFaehigkeiten, McdStandort, OrdnerStatus } from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  LeerHinweis,
  Plakette,
} from "@/components/dashboard";
import { Button, Chip, ChipLeiste, Meldung, formatDatum } from "@/components/ui";

type Filter = "alle" | "offen" | "beauftragt";

const STATUS_TEXT: Record<OrdnerStatus, string> = {
  ausstehend: "Ordner wird angelegt",
  vorbereitet: "Ordner vorbereitet",
  angelegt: "Ordner angelegt",
  fehler: "Ordner fehlerhaft",
};

const STATUS_ART: Record<OrdnerStatus, "ok" | "warn" | "gefahr" | "info"> = {
  ausstehend: "warn",
  vorbereitet: "info",
  angelegt: "ok",
  fehler: "gefahr",
};

const STATUS_ICON: Record<OrdnerStatus, typeof CheckCircle2> = {
  ausstehend: Loader2,
  vorbereitet: Clock,
  angelegt: CheckCircle2,
  fehler: AlertTriangle,
};

/** Fehler zuerst, dann noch nicht beauftragt, dann fertig. */
function rang(standort: McdStandort): number {
  if (standort.ordner_status === "fehler") return 0;
  if (!standort.ort) return 1;
  if (standort.beauftragungen.length === 0) return 2;
  return 3;
}

export function McdonaldsUebersicht({
  standorte,
  faehigkeiten,
  laedt = false,
  onOeffnen,
  onNeu,
  onAktualisieren,
}: {
  standorte: McdStandort[];
  faehigkeiten: McdFaehigkeiten | null;
  laedt?: boolean;
  onOeffnen: (id: number) => void;
  onNeu: () => void;
  onAktualisieren: () => void;
}) {
  const [filter, setFilter] = useState<Filter>("alle");

  const offen = standorte.filter((s) => s.beauftragungen.length === 0).length;
  const beauftragt = standorte.length - offen;

  const sichtbar = useMemo(() => {
    const gefiltert = standorte.filter((s) => {
      if (filter === "offen") return s.beauftragungen.length === 0;
      if (filter === "beauftragt") return s.beauftragungen.length > 0;
      return true;
    });
    return [...gefiltert].sort((a, b) => {
      const r = rang(a) - rang(b);
      return r !== 0 ? r : b.erstellt_am.localeCompare(a.erstellt_am);
    });
  }, [standorte, filter]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <ChipLeiste>
          <Chip aktiv={filter === "alle"} onClick={() => setFilter("alle")}>
            alle ({standorte.length})
          </Chip>
          <Chip aktiv={filter === "offen"} onClick={() => setFilter("offen")}>
            nicht beauftragt ({offen})
          </Chip>
          <Chip
            aktiv={filter === "beauftragt"}
            onClick={() => setFilter("beauftragt")}
          >
            beauftragt ({beauftragt})
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
            Standort anlegen
          </Button>
        </div>
      </div>

      {/* Solange die Referenztabelle fehlt, heißt jeder Ordner „XXX_…". Das
          ist behebbar, aber nur, wenn es jemand erfährt. */}
      {faehigkeiten && faehigkeiten.unlocode_eintraege === 0 && (
        <Meldung art="hinweis">
          Die UN/LOCODE-Tabelle ist noch nicht hochgeladen. Ordner heißen
          deshalb „XXX_…“ statt mit dem amtlichen Ortscode (Nievern → NIV). Die
          Tabelle — Anlage 5.1 des Projekthandbuchs — lädt man in einem
          geöffneten Standort hoch.
        </Meldung>
      )}

      {sichtbar.length === 0 ? (
        <LeerHinweis>
          {standorte.length === 0
            ? "Noch kein Standort erfasst. Lade die als .eml exportierte SLS-Anfrage hoch — Phase, Ort, Straße und Termine liest die App daraus selbst."
            : "In dieser Auswahl ist nichts."}
        </LeerHinweis>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {sichtbar.map((standort) => (
            <StandortKarte
              key={standort.id}
              standort={standort}
              onOeffnen={() => onOeffnen(standort.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function StandortKarte({
  standort,
  onOeffnen,
}: {
  standort: McdStandort;
  onOeffnen: () => void;
}) {
  const titel =
    standort.ordner_name || standort.standort_name || standort.ort || "Ohne Ort";
  const Icon = STATUS_ICON[standort.ordner_status];

  return (
    <Karte>
      <KarteKopf
        titel={titel}
        icon={MapPin}
        unterzeile={
          <>
            {standort.phase ? `Phase ${standort.phase} · ` : ""}
            {formatDatum(standort.erstellt_am)}
            {standort.sls_erkannt
              ? " · aus SLS gelesen"
              : standort.analysiert_am
              ? " · KI-Auswertung"
              : " · von Hand"}
          </>
        }
        aktion={
          <Plakette art={STATUS_ART[standort.ordner_status]}>
            {STATUS_TEXT[standort.ordner_status]}
          </Plakette>
        }
      />
      <KarteInhalt className="flex flex-col gap-2">
        {standort.ort ? (
          <div className="inline-flex items-start gap-1.5 text-[12px] text-app-text-still">
            <MapPin size={13} className="mt-0.5 shrink-0" />
            <span className="min-w-0">
              {[standort.strasse, `${standort.plz} ${standort.ort}`.trim()]
                .filter(Boolean)
                .join(", ")}
            </span>
          </div>
        ) : (
          <div className="inline-flex items-center gap-1.5 text-[12px] text-app-warn">
            <AlertTriangle size={13} className="shrink-0" />
            Kein Ort erkannt — bitte öffnen und nachtragen.
          </div>
        )}

        {standort.ordner_name && (
          <div className="inline-flex items-center gap-1.5 text-[12px] text-app-text-still">
            <FolderOpen size={13} className="shrink-0" />
            <span className="truncate font-mono">{standort.ordner_name}</span>
            {standort.ordner_anzahl > 0 && (
              <span className="shrink-0">· {standort.ordner_anzahl} Ordner</span>
            )}
          </div>
        )}

        {standort.abgabetermin && (
          <div className="inline-flex items-center gap-1.5 text-[12px] text-app-text-still">
            <Clock size={13} className="shrink-0" />
            Abgabe {formatDatum(standort.abgabetermin)}
          </div>
        )}

        {standort.beauftragungen.length > 0 ? (
          <div className="inline-flex items-center gap-1.5 text-[12px] text-app-ok">
            <Send size={13} className="shrink-0" />
            {standort.beauftragungen.length} Einzelabruf(e) —{" "}
            {standort.beauftragungen
              .map((b) => b.subplaner_kuerzel || b.subplaner_name)
              .join(", ")}
          </div>
        ) : (
          <div className="inline-flex items-center gap-1.5 text-[12px] text-app-text-leise">
            <FileText size={13} className="shrink-0" />
            Noch nicht beauftragt
          </div>
        )}

        <div className="flex items-center justify-between gap-2 border-t border-app-linie pt-2">
          <Icon
            size={14}
            className={`shrink-0 text-app-text-leise ${
              standort.ordner_status === "ausstehend" ? "animate-spin" : ""
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
