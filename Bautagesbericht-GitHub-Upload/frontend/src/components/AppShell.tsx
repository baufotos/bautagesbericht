"use client";

/**
 * Programmhülle: Seitenleiste links, Kopfzeile oben, Arbeitsfläche rechts.
 *
 * WARUM SEITENLEISTE STATT TABS
 * =============================
 * Die App ist inzwischen kein Formular mehr, sondern drei Arbeitsbereiche
 * (Baufotos, Mängelberichte, Bautagesberichte) mit je mehreren Ansichten. Eine
 * waagerechte Tab-Leiste bräuchte dafür zwölf Einträge und würde am Rechner
 * umbrechen. Die Seitenleiste zeigt alle Bereiche gleichzeitig, gruppiert sie
 * und macht sichtbar, wo man ist — so arbeitet jedes Bauprogramm auf dem
 * Windows-Rechner.
 *
 * DREI GERÄTEKLASSEN, EINE HÜLLE
 * ==============================
 *   ab lg   feste Seitenleiste (Arbeitsplatz am Schreibtisch)
 *   ab sm   Seitenleiste als Schublade über den Inhalt (Tablet)
 *   mobil   Schublade + untere Leiste für die drei Hauptbereiche, weil der
 *           Daumen unten liegt und auf der Baustelle nur der zählt
 *
 * Der Projektwähler sitzt in der Kopfzeile und gilt für die ganze App: Man
 * arbeitet einen Tag lang an einem Bauvorhaben, nicht pro Ansicht an einem
 * anderen. Die Suche springt in die Mängelübersicht — das ist die einzige
 * Liste, in der man wirklich sucht.
 */

import {
  Bell,
  Building2,
  Camera,
  ChevronRight,
  FileSignature,
  FileText,
  Images,
  LayoutDashboard,
  ListChecks,
  ListTree,
  Mail,
  Map,
  MapPin,
  Menu,
  MessagesSquare,
  Moon,
  Plus,
  RefreshCw,
  ScrollText,
  Search,
  Settings,
  SlidersHorizontal,
  Sun,
  Upload,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { useThema } from "@/lib/thema";
import type { Projekt } from "@/lib/types";
import { HppWortmarke } from "@/components/HppLogo";

/* ───────────────────────────── Navigationsmodell ───────────────────────────── */

export type Ansicht =
  | "dashboard"
  | "baufotos-neu"
  | "baufotos-galerie"
  | "maengel-uebersicht"
  | "maengel-neu"
  | "maengel-anzeige"
  | "projektberichte"
  | "besprechungen"
  | "btb-einreichen"
  | "btb-uebersicht"
  | "stamm-projekte"
  | "stamm-empfaenger"
  | "stamm-firmen"
  | "stamm-plaene"
  | "stamm-besprechung"
  | "stamm-listen";

export interface NavEintrag {
  key: Ansicht;
  label: string;
  /** Kurzform für die untere Leiste am Handy. */
  kurz?: string;
  icon: LucideIcon;
  /** Titel und Kennung der Ansicht — die Kopfzeile liest sie hier ab. */
  titel: string;
  bereich: string;
}

export interface NavGruppe {
  label?: string;
  eintraege: NavEintrag[];
}

export const NAVIGATION: NavGruppe[] = [
  {
    eintraege: [
      {
        key: "dashboard",
        label: "Dashboard",
        kurz: "Start",
        icon: LayoutDashboard,
        titel: "Dashboard",
        bereich: "Übersicht",
      },
    ],
  },
  {
    label: "Baufotos",
    eintraege: [
      {
        key: "baufotos-neu",
        label: "Fotos hochladen",
        kurz: "Fotos",
        icon: Camera,
        titel: "Baufotos hochladen",
        bereich: "Baufotos",
      },
      {
        key: "baufotos-galerie",
        label: "Fotosätze",
        icon: Images,
        titel: "Fotosätze",
        bereich: "Baufotos",
      },
    ],
  },
  {
    label: "Mängelberichte",
    eintraege: [
      {
        key: "maengel-uebersicht",
        label: "Übersicht",
        kurz: "Mängel",
        icon: ListChecks,
        titel: "Mängelübersicht",
        bereich: "Mängelberichte",
      },
      {
        key: "maengel-neu",
        label: "Mangel erfassen",
        icon: Plus,
        titel: "Mangel erfassen",
        bereich: "Mängelberichte",
      },
      {
        key: "maengel-anzeige",
        label: "Mängelanzeige",
        icon: FileSignature,
        titel: "Mängelanzeige erstellen",
        bereich: "Mängelberichte",
      },
    ],
  },
  {
    label: "Projektberichte",
    eintraege: [
      {
        key: "projektberichte",
        label: "Monatsberichte",
        kurz: "Bericht",
        icon: ScrollText,
        titel: "Monatsberichte",
        bereich: "Projektberichte",
      },
    ],
  },
  {
    label: "Baubesprechungen",
    eintraege: [
      {
        key: "besprechungen",
        label: "Protokolle",
        kurz: "Protokoll",
        icon: MessagesSquare,
        titel: "Baubesprechungsprotokolle",
        bereich: "Baubesprechungen",
      },
    ],
  },
  {
    label: "Bautagesberichte",
    eintraege: [
      {
        key: "btb-einreichen",
        label: "Bericht einreichen",
        kurz: "Bericht",
        icon: Upload,
        titel: "Bautagesbericht einreichen",
        bereich: "Bautagesberichte",
      },
      {
        key: "btb-uebersicht",
        label: "Übersicht",
        icon: FileText,
        titel: "Eingereichte Berichte",
        bereich: "Bautagesberichte",
      },
    ],
  },
  {
    label: "Stammdaten",
    eintraege: [
      {
        key: "stamm-projekte",
        label: "Projekte",
        icon: MapPin,
        titel: "Projekte",
        bereich: "Stammdaten",
      },
      {
        key: "stamm-firmen",
        label: "Firmen / Gewerke",
        icon: Building2,
        titel: "Firmen und Gewerke",
        bereich: "Stammdaten",
      },
      {
        key: "stamm-plaene",
        label: "Pläne",
        icon: Map,
        titel: "Projektpläne",
        bereich: "Stammdaten",
      },
      {
        key: "stamm-empfaenger",
        label: "Empfänger",
        icon: Mail,
        titel: "Empfänger",
        bereich: "Stammdaten",
      },
      {
        key: "stamm-besprechung",
        label: "Besprechungen",
        icon: ListTree,
        titel: "Kapitel und Projektbeteiligte",
        bereich: "Stammdaten",
      },
      {
        key: "stamm-listen",
        label: "Wertelisten",
        icon: SlidersHorizontal,
        titel: "Wertelisten",
        bereich: "Stammdaten",
      },
    ],
  },
];

/** Alle Einträge flach — für Titel-Suche und die untere Leiste. */
export const ALLE_EINTRAEGE: NavEintrag[] = NAVIGATION.flatMap((g) => g.eintraege);

/** Die vier Einträge der unteren Leiste am Handy. */
const MOBILE_LEISTE: Ansicht[] = [
  "dashboard",
  "baufotos-neu",
  "maengel-uebersicht",
  "btb-einreichen",
];

export function eintragZu(ansicht: Ansicht): NavEintrag {
  return ALLE_EINTRAEGE.find((e) => e.key === ansicht) ?? ALLE_EINTRAEGE[0];
}

/* ───────────────────────────── Seitenleiste ───────────────────────────── */

function SeitenleisteInhalt({
  ansicht,
  onAnsicht,
}: {
  ansicht: Ansicht;
  onAnsicht: (ansicht: Ansicht) => void;
}) {
  return (
    <div className="flex h-full flex-col bg-app-sidebar">
      {/*
        Wortmarke des Büros, darunter die Anwendung — dieselbe Anordnung wie im
        Briefkopf ("HPP" über "Architekten"). Die Marke ist ein Vektor und färbt
        sich über currentColor weiß, siehe components/HppLogo.
      */}
      <div className="border-b border-app-sidebar-linie px-4 py-4">
        <HppWortmarke hoehe={19} className="text-app-sidebar-text-hell" />
        <span className="mt-1.5 block truncate text-[9px] tracking-[0.14em] text-app-sidebar-label">
          BAUMANAGEMENT
        </span>
      </div>

      <nav className="flex-1 overflow-y-auto px-2.5 py-3">
        {NAVIGATION.map((gruppe, gi) => (
          <div key={gruppe.label ?? `gruppe-${gi}`} className={gi > 0 ? "mt-5" : ""}>
            {gruppe.label && (
              <div className="px-2 pb-2 text-[9.5px] font-semibold uppercase tracking-[0.14em] text-app-sidebar-label">
                {gruppe.label}
              </div>
            )}
            <div className="flex flex-col gap-1">
              {gruppe.eintraege.map(({ key, label, icon: Icon }) => {
                const aktiv = ansicht === key;
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => onAnsicht(key)}
                    aria-current={aktiv ? "page" : undefined}
                    /* Aktiv = aufgehellte Fläche mit feiner Kante, nicht die
                       Akzentfarbe: Der Akzent ist hell und gehört den Knöpfen.
                       Der transparente Rahmen bei den übrigen Einträgen
                       verhindert das Verrutschen um 1px beim Wechsel. */
                    className={`flex w-full cursor-pointer items-center gap-2.5 rounded-app-sm border px-2.5 py-2 text-left text-[12.5px] transition-colors ${
                      aktiv
                        ? "border-app-sidebar-kante bg-app-sidebar-aktiv font-medium text-app-sidebar-text-hell"
                        : "border-transparent text-app-sidebar-text hover:bg-app-sidebar-hover hover:text-app-sidebar-text-hell"
                    }`}
                  >
                    <Icon size={15} className="shrink-0" strokeWidth={aktiv ? 2.2 : 1.8} />
                    <span className="truncate">{label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-app-sidebar-linie px-4 py-3 text-[10px] leading-relaxed text-app-sidebar-label">
        Zentrale Daten — alle im Team sehen denselben Stand.
      </div>
    </div>
  );
}

/* ───────────────────────────── Bausteine der Kopfzeile ───────────────────────────── */

/** Runder Knopf in der Kopfzeile — einheitlich für alle Symbole dort. */
function KopfKnopf({
  icon: Icon,
  label,
  onClick,
  dreht = false,
  zaehler = 0,
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  /** Dreht das Symbol, solange geladen wird. */
  dreht?: boolean;
  /** Zahl auf der Sprechblase; 0 heißt: keine Blase. */
  zaehler?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="relative cursor-pointer rounded-full border border-transparent p-2 text-app-text-still transition-colors hover:border-app-linie hover:bg-app-flaeche-hoch hover:text-app-text"
    >
      <Icon size={16} className={dreht ? "animate-spin" : ""} />
      {zaehler > 0 && (
        <span className="absolute -top-0.5 -right-0.5 flex min-w-[16px] items-center justify-center rounded-full bg-app-gefahr px-1 text-[9px] font-bold text-app-flaeche">
          {zaehler > 99 ? "99+" : zaehler}
        </span>
      )}
    </button>
  );
}

/** Pfad zur aktuellen Ansicht: Bereich › Titel — aus dem Navigationsmodell. */
function Brotkrumen({ ansicht }: { ansicht: Ansicht }) {
  const eintrag = eintragZu(ansicht);
  return (
    <div className="hidden min-w-0 shrink items-center gap-1.5 md:flex">
      <span className="truncate text-[12px] text-app-text-leise">{eintrag.bereich}</span>
      <ChevronRight size={13} className="shrink-0 text-app-text-leise" />
      <span className="truncate text-[12.5px] font-semibold text-app-text">
        {eintrag.titel}
      </span>
    </div>
  );
}

/* ───────────────────────────── Hülle ───────────────────────────── */

export function AppShell({
  ansicht,
  onAnsicht,
  projekte,
  projektId,
  onProjekt,
  onSuche,
  onAktualisieren,
  laedt = false,
  ueberfaellig = 0,
  banner,
  children,
}: {
  ansicht: Ansicht;
  onAnsicht: (ansicht: Ansicht) => void;
  projekte: Projekt[];
  projektId: number | null;
  onProjekt: (id: number) => void;
  /** Enter im Suchfeld — springt in die Mängelübersicht. */
  onSuche: (begriff: string) => void;
  onAktualisieren: () => void;
  laedt?: boolean;
  /**
   * Anzahl überfälliger Mängel — die Zahl auf der Glocke.
   *
   * Absichtlich ein echter Wert und keine Zierde: Eine Glocke, die immer
   * gleich aussieht, schaut nach zwei Tagen niemand mehr an. Ein Klick führt
   * in die Mängelübersicht, wo die Fristen stehen.
   */
  ueberfaellig?: number;
  /** Hinweisleisten (Installieren, offline, Fehler) direkt unter der Kopfzeile. */
  banner?: ReactNode;
  children: ReactNode;
}) {
  const [schubladeOffen, setSchubladeOffen] = useState(false);
  const [suchbegriff, setSuchbegriff] = useState("");
  const { thema, umschalten } = useThema();

  // Nach jedem Ansichtswechsel die Schublade schließen — sonst verdeckt sie
  // am Tablet die Ansicht, die man gerade geöffnet hat.
  useEffect(() => {
    setSchubladeOffen(false);
  }, [ansicht]);

  return (
    <div className="flex min-h-screen bg-app-bg">
      {/* Feste Seitenleiste am Rechner */}
      <aside className="hidden w-[212px] shrink-0 lg:block">
        <div className="fixed top-0 bottom-0 w-[212px]">
          <SeitenleisteInhalt ansicht={ansicht} onAnsicht={onAnsicht} />
        </div>
      </aside>

      {/* Schublade auf kleineren Geräten */}
      {schubladeOffen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Menü schließen"
            className="absolute inset-0 cursor-default bg-black/60 backdrop-blur-sm"
            onClick={() => setSchubladeOffen(false)}
          />
          <div className="schatten-hoch absolute top-0 bottom-0 left-0 w-[244px]">
            <button
              type="button"
              onClick={() => setSchubladeOffen(false)}
              aria-label="Menü schließen"
              className="absolute top-3.5 right-3 z-10 cursor-pointer rounded-app-sm p-1 text-app-sidebar-label hover:text-app-sidebar-text-hell"
            >
              <X size={16} />
            </button>
            <SeitenleisteInhalt ansicht={ansicht} onAnsicht={onAnsicht} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Kopfzeile: Pfad links, Suche in der Mitte, Werkzeuge rechts.
            Halbdurchsichtig mit Weichzeichner — beim Scrollen schiebt sich der
            Inhalt darunter durch, statt an einer harten Kante zu enden. */}
        <header className="sticky top-0 z-30 flex items-center gap-2 border-b border-app-linie bg-app-flaeche/80 px-3 py-2.5 backdrop-blur-xl sm:gap-3 sm:px-5">
          <button
            type="button"
            onClick={() => setSchubladeOffen(true)}
            aria-label="Menü öffnen"
            className="shrink-0 cursor-pointer rounded-full p-2 text-app-text-still transition-colors hover:bg-app-flaeche-hoch hover:text-app-text lg:hidden"
          >
            <Menu size={18} />
          </button>

          <Brotkrumen ansicht={ansicht} />

          {/* Suche — greift wirklich, kein Zierbalken */}
          <div className="flex min-w-0 flex-1 justify-center">
            <div className="relative w-full sm:max-w-[420px]">
              <Search
                size={14}
                className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-app-text-leise"
              />
              <input
                value={suchbegriff}
                onChange={(e) => setSuchbegriff(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onSuche(suchbegriff.trim());
                }}
                placeholder="Mängel durchsuchen…"
                aria-label="Mängel durchsuchen"
                className="w-full rounded-full border border-app-linie bg-app-flaeche-still py-2 pr-3 pl-9 text-[12.5px] text-app-text outline-none transition-colors placeholder:text-app-text-leise focus:border-app-linie-stark focus:bg-app-flaeche-hoch"
              />
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1.5">
            {/* Projektwahl gilt für die ganze App */}
            <select
              value={projektId ?? ""}
              onChange={(e) => onProjekt(Number(e.target.value))}
              aria-label="Projekt wählen"
              className="max-w-[130px] cursor-pointer truncate rounded-full border border-app-linie bg-app-flaeche-still px-3 py-1.5 text-[12px] text-app-text outline-none transition-colors hover:bg-app-flaeche-hoch focus:border-app-linie-stark sm:max-w-[240px]"
            >
              {projekte.length === 0 && <option value="">kein Projekt</option>}
              {projekte.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>

            <KopfKnopf
              icon={RefreshCw}
              label="Daten neu laden"
              onClick={onAktualisieren}
              dreht={laedt}
            />

            {/* Die Glocke trägt eine echte Zahl: überfällige Mängel. */}
            <div className="hidden sm:block">
              <KopfKnopf
                icon={Bell}
                label={
                  ueberfaellig > 0
                    ? `${ueberfaellig} überfällige Mängel anzeigen`
                    : "Keine überfälligen Mängel"
                }
                onClick={() => onAnsicht("maengel-uebersicht")}
                zaehler={ueberfaellig}
              />
            </div>

            <div className="hidden sm:block">
              <KopfKnopf
                icon={Settings}
                label="Stammdaten"
                onClick={() => onAnsicht("stamm-projekte")}
              />
            </div>

            <KopfKnopf
              icon={thema === "dunkel" ? Sun : Moon}
              label={thema === "dunkel" ? "Helle Fassung" : "Dunkle Fassung"}
              onClick={umschalten}
            />

            {/* Kein Anmeldesystem, also kein Personenbild — die Kürzel des
                Büros als ruhiger Abschluss der Zeile. */}
            <span
              aria-hidden
              className="ml-0.5 hidden size-8 items-center justify-center rounded-full border border-app-linie bg-app-flaeche-hoch text-[10.5px] font-semibold tracking-[0.04em] text-app-text-still lg:flex"
            >
              HPP
            </span>
          </div>
        </header>

        {banner}

        <main className="min-w-0 flex-1 px-3 py-4 pb-[calc(5rem+env(safe-area-inset-bottom))] sm:px-6 sm:py-6 lg:pb-8">
          <div className="mx-auto max-w-[1320px]">{children}</div>
        </main>

        {/* Untere Leiste am Handy für die Hauptbereiche */}
        <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-app-linie bg-app-flaeche/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl sm:hidden">
          <div className="flex px-1.5 py-1.5">
            {MOBILE_LEISTE.map((key) => {
              const eintrag = eintragZu(key);
              const Icon = eintrag.icon;
              const aktiv = ansicht === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => onAnsicht(key)}
                  aria-current={aktiv ? "page" : undefined}
                  className={`flex flex-1 cursor-pointer flex-col items-center gap-1 rounded-app-sm py-1.5 transition-colors ${
                    aktiv
                      ? "bg-app-akzent-sanft text-app-text"
                      : "text-app-text-leise"
                  }`}
                >
                  <Icon size={19} strokeWidth={aktiv ? 2.3 : 1.8} />
                  <span className="text-[9.5px] font-medium uppercase tracking-[0.04em]">
                    {eintrag.kurz ?? eintrag.label}
                  </span>
                </button>
              );
            })}
          </div>
        </nav>
      </div>
    </div>
  );
}
