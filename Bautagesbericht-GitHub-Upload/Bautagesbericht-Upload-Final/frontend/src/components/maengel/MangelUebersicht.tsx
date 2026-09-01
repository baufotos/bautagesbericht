"use client";

/**
 * Mängel-Übersicht: filtern, überblicken, öffnen.
 *
 * Wie die bestehende Einreichungs-Übersicht ist das eine Hol-Ansicht — man
 * schaut selbst nach, statt auf eine Benachrichtigung zu warten. Überfällige
 * Fristen stechen rot heraus, weil das die einzige Information ist, die von
 * allein niemand bemerkt.
 *
 * Aufteilung der Filter nach Häufigkeit: Der Status wird ständig umgestellt und
 * liegt daher offen in einer wischbaren Zeile. Firma, Priorität und Suche
 * braucht man seltener und stecken am Handy hinter "Filter" — sonst müsste man
 * auf einem 390-px-Bildschirm erst vier Bedienelemente überblättern, bevor der
 * erste Mangel zu sehen ist.
 */

import {
  ChevronRight,
  Copy,
  FileDown,
  ImageOff,
  Plus,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import type {
  Gewerk,
  MangelFilter,
  MangelListItem,
  MangelStammdaten,
} from "@/lib/types";
import {
  Button,
  Card,
  Chip,
  ChipLeiste,
  EmptyState,
  Input,
  LinkButton,
  PrioritaetText,
  Select,
  StatusBadge,
  formatDatum,
} from "@/components/ui";

export function MangelUebersicht({
  maengel,
  gewerke,
  stammdaten,
  filter,
  onFilter,
  onOeffnen,
  onNeu,
  laden,
}: {
  maengel: MangelListItem[];
  gewerke: Gewerk[];
  stammdaten: MangelStammdaten | null;
  filter: MangelFilter;
  onFilter: (filter: MangelFilter) => void;
  onOeffnen: (id: number) => void;
  onNeu: () => void;
  laden: boolean;
}) {
  const [filterOffen, setFilterOffen] = useState(false);
  const anzahlUeberfaellig = maengel.filter((m) => m.ist_ueberfaellig).length;

  function setze(teil: Partial<MangelFilter>) {
    onFilter({ ...filter, ...teil });
  }

  /** Status-Schnellfilter: "alle" / einzelner Status / nur überfällige. */
  const statusAktiv = filter.status ?? (filter.ueberfaellig ? "__ueberfaellig" : "alle");
  const feinFilterAktiv =
    filter.gewerk_id !== undefined ||
    filter.prioritaet !== undefined ||
    (filter.suche ?? "") !== "";

  return (
    <div className="flex flex-col gap-3">
      {/* Zählzeile und Export in einer Zeile — spart am Handy eine ganze Reihe */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-ui-text-muted">
          {maengel.length} Mangel/Mängel
          {anzahlUeberfaellig > 0 && (
            <span className="text-ui-danger"> · {anzahlUeberfaellig} überfällig</span>
          )}
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <LinkButton
            href={api.maengel.exportUrl({ ...filter, intern: false })}
            target="_blank"
            rel="noopener noreferrer"
            icon={FileDown}
            title="Word-Dokument mit der aktuell gefilterten Auswahl — Fassung für die Firma, ohne interne Bemerkungen"
          >
            {/* Am Handy nur ein Wort, sonst wird die Zeile zu breit. */}
            <span className="sm:hidden">Word</span>
            <span className="hidden sm:inline">Mängelliste (Word)</span>
          </LinkButton>
          <LinkButton
            href={api.maengel.exportUrl({ ...filter, intern: true })}
            target="_blank"
            rel="noopener noreferrer"
            variante="still"
            title="Interne Fassung mit internen Bemerkungen — nicht an Firmen weitergeben"
          >
            intern
          </LinkButton>
          {/* Am Handy übernimmt der runde Knopf unten rechts das Erfassen. */}
          <span className="hidden sm:inline-flex">
            <Button icon={Plus} onClick={onNeu}>
              Mangel erfassen
            </Button>
          </span>
        </div>
      </div>

      {/* Status: die häufigste Umstellung, deshalb immer sichtbar */}
      <ChipLeiste>
        <Chip
          aktiv={statusAktiv === "alle"}
          onClick={() => setze({ status: undefined, ueberfaellig: undefined })}
        >
          Alle
        </Chip>
        <Chip
          aktiv={statusAktiv === "__ueberfaellig"}
          onClick={() => setze({ status: undefined, ueberfaellig: true })}
        >
          Überfällig
        </Chip>
        {(stammdaten?.status || []).map((s) => (
          <Chip
            key={s.id}
            aktiv={filter.status === s.bezeichnung}
            onClick={() => setze({ status: s.bezeichnung, ueberfaellig: undefined })}
          >
            {s.bezeichnung}
          </Chip>
        ))}
      </ChipLeiste>

      {/* Feinfilter: am Handy eingeklappt, am Rechner immer offen */}
      <div className="sm:hidden">
        <Chip
          aktiv={filterOffen || feinFilterAktiv}
          onClick={() => setFilterOffen((v) => !v)}
        >
          <SlidersHorizontal size={12} className="mr-1 inline" />
          Filter{feinFilterAktiv ? " aktiv" : ""}
        </Chip>
      </div>

      <div className={`flex-wrap gap-2 ${filterOffen ? "flex" : "hidden"} sm:flex`}>
        <div className="min-w-[190px] flex-1">
          <Select
            value={filter.gewerk_id ?? ""}
            onChange={(e) =>
              setze({ gewerk_id: e.target.value ? Number(e.target.value) : undefined })
            }
          >
            <option value="">Alle Firmen / Büros</option>
            {gewerke.map((g) => (
              <option key={g.id} value={g.id}>
                {g.anzeige_name}
              </option>
            ))}
          </Select>
        </div>

        <div className="w-full sm:w-[170px]">
          <Select
            value={filter.prioritaet ?? ""}
            onChange={(e) => setze({ prioritaet: e.target.value || undefined })}
          >
            <option value="">Alle Prioritäten</option>
            {(stammdaten?.prioritaeten || []).map((p) => (
              <option key={p} value={p}>
                Priorität {p}
              </option>
            ))}
          </Select>
        </div>

        <div className="relative min-w-[190px] flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ui-text-faint"
          />
          <Input
            className="pl-8"
            placeholder="Nummer, Kurzbezeichnung, Beschreibung…"
            value={filter.suche ?? ""}
            onChange={(e) => setze({ suche: e.target.value || undefined })}
          />
        </div>
      </div>

      {/*
        Runder Knopf unten rechts — die übliche App-Geste für "neu anlegen".
        Sitzt über der Navigationsleiste und über dem Sicherheitsabstand des
        Geräts, damit er nicht unter der Wischleiste klebt.
      */}
      <div className="sm:hidden">
        <button
          type="button"
          onClick={onNeu}
          aria-label="Mangel erfassen"
          className="fixed right-4 bottom-[calc(5rem+env(safe-area-inset-bottom))] z-30 flex size-14 cursor-pointer items-center justify-center rounded-full bg-ui-accent text-ui-accent-text schatten-akzent transition-colors hover:bg-ui-accent-hover"
        >
          <Plus size={24} />
        </button>
      </div>

      {laden ? (
        <EmptyState>Mängel werden geladen…</EmptyState>
      ) : maengel.length === 0 ? (
        <EmptyState>
          Keine Mängel in dieser Ansicht. Auf der Baustelle erfasste Mängel
          erscheinen hier sofort.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-1.5">
          {maengel.map((m) => (
            <MangelZeile key={m.id} mangel={m} onOeffnen={onOeffnen} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Eine Zeile der Liste.
 *
 * Bewusst gestapelt statt in Spalten: Auf dem Handy bliebe für die
 * Kurzbezeichnung sonst nur ein Wortfragment übrig. Erste Zeile Nummer und
 * Bezeichnung, zweite Zeile Firma und Ort, dritte Zeile die Merkmale (Status,
 * Frist, Priorität) — was zuerst gesucht wird, steht oben.
 */
function MangelZeile({
  mangel,
  onOeffnen,
}: {
  mangel: MangelListItem;
  onOeffnen: (id: number) => void;
}) {
  const meta = [mangel.firma_name || "keine Firma", mangel.raumnummer, mangel.hinweis_ort]
    .filter(Boolean)
    .join(" · ");

  return (
    <Card className="transition-colors hover:border-ui-line-strong">
      <button
        type="button"
        onClick={() => onOeffnen(mangel.id)}
        className="flex w-full cursor-pointer items-start gap-3 p-2.5 text-left"
      >
        {/* Vorschaubild klein geladen (thumb), damit die Liste auch mobil zügig steht */}
        <span className="size-14 shrink-0 overflow-hidden rounded-ui-sm border border-ui-line bg-ui-surface-muted">
          {mangel.titel_foto_id ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={api.maengel.fotoUrl(mangel.titel_foto_id, true)}
              alt=""
              className="size-full object-cover"
              loading="lazy"
            />
          ) : (
            <span className="flex size-full items-center justify-center text-ui-text-faint">
              <ImageOff size={16} />
            </span>
          )}
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-2">
            <span className="shrink-0 font-mono text-[12px] text-ui-text-muted">
              {mangel.nummer}
            </span>
            <span className="truncate text-[14.5px] font-semibold text-ui-text">
              {mangel.kurzbezeichnung}
            </span>
            {mangel.farbmarkierung && (
              <span
                className="size-2.5 shrink-0 rounded-full"
                style={{ background: mangel.farbmarkierung }}
                title="Farbmarkierung"
              />
            )}
          </span>

          <span className="mt-0.5 block truncate text-[12.5px] text-ui-text-muted">
            {meta}
          </span>

          <span className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <StatusBadge text={mangel.status} farbe={mangel.status_farbe} klein />
            {mangel.aktuelle_frist && (
              <span
                className={`font-mono text-[11.5px] ${
                  mangel.ist_ueberfaellig
                    ? "font-semibold text-ui-danger"
                    : "text-ui-text-muted"
                }`}
              >
                {mangel.ist_ueberfaellig ? "überfällig " : "Frist "}
                {formatDatum(mangel.aktuelle_frist)}
              </span>
            )}
            <PrioritaetText wert={mangel.prioritaet} />
            {mangel.anzahl_fotos > 1 && (
              <span className="text-[12px] text-ui-text-muted">
                {mangel.anzahl_fotos} Fotos
              </span>
            )}
            {mangel.eltern_mangel_id && (
              <span
                className="inline-flex items-center gap-1 text-[11.5px] text-ui-text-faint"
                title="Duplikat eines anderen Mangels"
              >
                <Copy size={11} /> Kopie
              </span>
            )}
          </span>
        </span>

        <ChevronRight size={16} className="mt-4 shrink-0 text-ui-text-faint" />
      </button>
    </Card>
  );
}
