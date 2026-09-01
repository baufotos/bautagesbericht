"use client";

/**
 * Karten- und Diagrammbausteine der Arbeitsflächen.
 *
 * GESTALTUNGSVORGABE (gilt für alle Ansichten, hier ist die einzige Quelle):
 *
 *   Karte        Fläche (app-flaeche) vor dem verlaufenden Grund, 1-px-Kante
 *                aus 8 % Weiß, Radius 16, weicher Schatten mit einer feinen
 *                Lichtkante oben. Kein Rahmen um Rahmen, keine Farbflächen
 *                als Deko.
 *   Kartentitel  Sans, 13 px, halbfett — links oben. Rechts daneben höchstens
 *                EINE Aktion oder eine Plakette.
 *   Zahlen       groß (26 px, in der Hauptkachel 40 px), halbfett, darunter
 *                ein kleines graues Label. Die Zahl ist der Held.
 *   Trend        Pfeil plus Wert, grün für besser, rot für schlechter — die
 *                einzige Stelle, an der Farbe ohne Zustand erlaubt ist, weil
 *                die Richtung selbst die Aussage ist.
 *   Diagramme    Linie in Akzenthelligkeit (app-chart) mit Verlauf darunter,
 *                Grau (app-chart-still) für Vergleichswerte, keine Legenden,
 *                wenn die Achsenbeschriftung genügt.
 *   Formularlabel bleibt Mono/klein/grau (components/ui.tsx) — das ist die
 *                Handschrift des Hauses und unterscheidet Eingabe von Anzeige.
 *
 * Alle Diagramme sind handgezeichnetes SVG. Bewusst keine Diagramm-Bibliothek:
 * Das Bündel bleibt klein (wichtig für den Start auf der Baustelle), es gibt
 * keine Abhängigkeit, die bei einem Next-Update bricht, und der Service Worker
 * kann alles zwischenspeichern.
 *
 * Kein Baustein erfindet Daten. Fehlen Werte, zeigt er einen ruhigen
 * Leerhinweis — eine erfundene Kurve in einer Mängelliste wäre schlimmer als
 * eine leere Fläche.
 */

import { ArrowDownRight, ArrowUpRight, MoreHorizontal, type LucideIcon } from "lucide-react";
import { useId, type ReactNode } from "react";

import { statusFarben } from "@/lib/farben";

/* ───────────────────────────── Flächen ───────────────────────────── */

export function Karte({
  children,
  className = "",
  hervorgehoben = false,
}: {
  children: ReactNode;
  className?: string;
  /** Hauptkachel: eine Stufe hellere Fläche und deutlichere Kante. */
  hervorgehoben?: boolean;
}) {
  return (
    <div
      className={`schatten-karte rounded-app border ${
        hervorgehoben
          ? "border-app-linie-stark bg-app-flaeche-hoch"
          : "border-app-linie bg-app-flaeche"
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function KarteKopf({
  titel,
  unterzeile,
  aktion,
  menue = false,
  icon: Icon,
}: {
  titel: string;
  unterzeile?: ReactNode;
  /** Höchstens eine Aktion — sonst wird die Karte zur Werkzeugleiste. */
  aktion?: ReactNode;
  /** Das dezente "…" rechts oben wie in der Vorlage (nur Zierde, kein Menü). */
  menue?: boolean;
  icon?: LucideIcon;
}) {
  return (
    <div className="flex items-start justify-between gap-3 px-4 pt-4 pb-2.5 sm:px-5">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          {Icon && <Icon size={14} className="shrink-0 text-app-text-still" />}
          <h3 className="truncate text-[13px] font-semibold text-app-text">{titel}</h3>
        </div>
        {unterzeile && (
          <div className="mt-0.5 text-[11.5px] text-app-text-still">{unterzeile}</div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {aktion}
        {menue && <MoreHorizontal size={16} className="text-app-text-leise" />}
      </div>
    </div>
  );
}

export function KarteInhalt({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`px-4 pb-4 sm:px-5 sm:pb-5 ${className}`}>{children}</div>;
}

/** Antwortendes Kartenraster — die Grundordnung jeder Arbeitsfläche. */
export function KartenGitter({
  children,
  spalten = 3,
}: {
  children: ReactNode;
  spalten?: 2 | 3 | 4;
}) {
  const klassen = {
    2: "sm:grid-cols-2",
    3: "sm:grid-cols-2 xl:grid-cols-3",
    4: "sm:grid-cols-2 xl:grid-cols-4",
  }[spalten];
  return <div className={`grid grid-cols-1 gap-4 ${klassen}`}>{children}</div>;
}

/* ───────────────────────────── Plaketten ───────────────────────────── */

export type PlakettenArt = "ok" | "warn" | "gefahr" | "info" | "neutral";

const PLAKETTE: Record<PlakettenArt, string> = {
  ok: "bg-app-ok-sanft text-app-ok",
  warn: "bg-app-warn-sanft text-app-warn",
  gefahr: "bg-app-gefahr-sanft text-app-gefahr",
  info: "bg-app-info-sanft text-app-info",
  neutral: "bg-app-flaeche-still text-app-text-still border border-app-linie",
};

export function Plakette({
  children,
  art = "neutral",
  gross = false,
}: {
  children: ReactNode;
  art?: PlakettenArt;
  /** Große Fassung für die Kopfzeile einer Ansicht (wie "ACTIVE" in der Vorlage). */
  gross?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full font-semibold uppercase tracking-[0.04em] ${
        gross ? "px-3 py-1 text-[10.5px]" : "px-2.5 py-0.5 text-[10px]"
      } ${PLAKETTE[art]}`}
    >
      {children}
    </span>
  );
}

/**
 * Farbige Plakette mit frei gesetzter Farbe (Status aus den Stammdaten).
 *
 * Die gespeicherte Farbe wird in der dunklen Fassung aufgehellt — sie wurde
 * für Weiß gewählt und wäre hier sonst nicht lesbar (siehe lib/farben.ts).
 */
export function FarbPlakette({ text, farbe }: { text: string; farbe?: string }) {
  const { ton, rand, flaeche } = statusFarben(farbe);
  return (
    <span
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium"
      style={{ color: ton, borderColor: rand, background: flaeche }}
    >
      <span className="size-1.5 shrink-0 rounded-full" style={{ background: ton }} />
      {text}
    </span>
  );
}

/* ───────────────────────────── Kennzahlen ───────────────────────────── */

export function Kennzahl({
  wert,
  label,
  hinweis,
  art = "normal",
  gross = false,
  trend,
}: {
  wert: ReactNode;
  label: string;
  hinweis?: ReactNode;
  art?: "normal" | "gefahr" | "ok";
  /** Hauptkennzahl einer Ansicht — deutlich größer gesetzt. */
  gross?: boolean;
  /** Veränderung gegenüber dem Vergleichszeitraum. */
  trend?: TrendWert;
}) {
  const farbe = {
    normal: "text-app-text",
    gefahr: "text-app-gefahr",
    ok: "text-app-ok",
  }[art];
  return (
    <div>
      <div className="flex flex-wrap items-end gap-2.5">
        <div
          className={`font-semibold leading-none tracking-tight ${
            gross ? "text-[40px]" : "text-[26px]"
          } ${farbe}`}
        >
          {wert}
        </div>
        {trend && <Trend {...trend} />}
      </div>
      <div className={`text-[11.5px] text-app-text-still ${gross ? "mt-2" : "mt-1"}`}>
        {label}
      </div>
      {hinweis && <div className="mt-0.5 text-[11px] text-app-text-leise">{hinweis}</div>}
    </div>
  );
}

export interface TrendWert {
  /** Beschriftung, z. B. "+3" oder "12 %". */
  text: string;
  /** Zeigt der Pfeil nach oben? */
  auf: boolean;
  /**
   * Ist die Richtung eine gute Nachricht?
   *
   * Getrennt von ``auf``, weil beides im Bauwesen auseinanderfällt: Mehr
   * erledigte Mängel ist oben und gut, mehr überfällige ist oben und schlecht.
   * Ohne diese Trennung wäre jeder steigende Wert grün — also sinnlos.
   */
  gut?: boolean;
  /** Zusatz hinter dem Wert, z. B. "zur Vorwoche". */
  bezug?: string;
}

/** Trend-Anzeige: Pfeil, Wert, Bezug — grün wenn gut, rot wenn nicht. */
export function Trend({ text, auf, gut = auf, bezug }: TrendWert) {
  const Pfeil = auf ? ArrowUpRight : ArrowDownRight;
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span
        className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
          gut ? "bg-app-ok-sanft text-app-ok" : "bg-app-gefahr-sanft text-app-gefahr"
        }`}
      >
        <Pfeil size={12} strokeWidth={2.6} />
        {text}
      </span>
      {bezug && <span className="text-[11px] text-app-text-leise">{bezug}</span>}
    </span>
  );
}

/**
 * Ringdiagramm mit Prozentwert in der Mitte.
 *
 * Der Ring beginnt oben und läuft im Uhrzeigersinn — die Leserichtung, die
 * jeder aus Fortschrittsanzeigen kennt.
 */
export function Ring({
  prozent,
  label,
  unterzeile,
  groesse = 132,
  dicke = 13,
  farbe = "var(--color-app-chart)",
}: {
  prozent: number;
  label?: string;
  unterzeile?: string;
  groesse?: number;
  dicke?: number;
  farbe?: string;
}) {
  const wert = Math.max(0, Math.min(100, Number.isFinite(prozent) ? prozent : 0));
  const radius = (groesse - dicke) / 2;
  const umfang = 2 * Math.PI * radius;
  const gefuellt = (wert / 100) * umfang;

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={groesse} height={groesse} viewBox={`0 0 ${groesse} ${groesse}`}>
        <g transform={`rotate(-90 ${groesse / 2} ${groesse / 2})`}>
          <circle
            cx={groesse / 2}
            cy={groesse / 2}
            r={radius}
            fill="none"
            stroke="var(--color-app-chart-spur)"
            strokeWidth={dicke}
          />
          <circle
            cx={groesse / 2}
            cy={groesse / 2}
            r={radius}
            fill="none"
            stroke={farbe}
            strokeWidth={dicke}
            strokeLinecap="round"
            strokeDasharray={`${gefuellt} ${umfang - gefuellt}`}
          />
        </g>
      </svg>
      <div className="absolute text-center">
        <div className="text-[22px] font-semibold leading-none text-app-text">
          {Math.round(wert)}%
        </div>
        {label && (
          <div className="mt-1 max-w-[92px] text-[11px] leading-tight text-app-text-still">
            {label}
          </div>
        )}
        {unterzeile && (
          <div className="text-[10px] text-app-text-leise">{unterzeile}</div>
        )}
      </div>
    </div>
  );
}

/* ───────────────────────────── Balken ───────────────────────────── */

export interface BalkenWert {
  label: string;
  wert: number;
  /** Beschriftung über dem Balken; ohne Angabe wird der Wert genommen. */
  anzeige?: string;
  /** true = Akzentfarbe (der Wert, um den es geht), false = grauer Vergleich. */
  betont?: boolean;
  farbe?: string;
}

/**
 * Balkengruppe mit Wertbeschriftung über und Achsenbeschriftung unter dem
 * Balken. Ohne Gitterlinien: Bei drei bis fünf Balken liest man die Zahl
 * ohnehin an der Beschriftung ab, Linien wären nur Unruhe.
 */
export function BalkenGruppe({
  werte,
  hoehe = 96,
  maximum,
}: {
  werte: BalkenWert[];
  hoehe?: number;
  maximum?: number;
}) {
  if (werte.length === 0) return <LeerHinweis>Keine Werte vorhanden.</LeerHinweis>;

  const max = Math.max(maximum ?? 0, ...werte.map((w) => w.wert), 1);

  return (
    <div className="flex items-end gap-3" style={{ minHeight: hoehe + 34 }}>
      {werte.map((w, i) => {
        const anteil = Math.max(0, w.wert) / max;
        return (
          <div key={`${w.label}-${i}`} className="flex min-w-0 flex-1 flex-col items-center">
            <div className="mb-1 text-[11.5px] font-semibold text-app-text">
              {w.anzeige ?? w.wert}
            </div>
            <div
              className="flex w-full items-end justify-center"
              style={{ height: hoehe }}
            >
              <div
                className="w-full max-w-[46px] rounded-[7px]"
                style={{
                  height: `${Math.max(anteil * 100, w.wert > 0 ? 4 : 0)}%`,
                  background:
                    w.farbe ??
                    (w.betont
                      ? "var(--color-app-chart)"
                      : "var(--color-app-chart-still)"),
                }}
              />
            </div>
            <div className="mt-1.5 w-full truncate text-center text-[10.5px] text-app-text-still">
              {w.label}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Waagerechter Fortschrittsbalken mit Beschriftung — für Listen und Quoten. */
export function Quote({
  label,
  prozent,
  rechts,
  farbe = "var(--color-app-chart)",
}: {
  label: string;
  prozent: number;
  rechts?: ReactNode;
  farbe?: string;
}) {
  const wert = Math.max(0, Math.min(100, Number.isFinite(prozent) ? prozent : 0));
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-[12.5px] text-app-text">{label}</span>
        <span className="shrink-0 text-[12px] font-semibold text-app-text">
          {rechts ?? `${Math.round(wert)} %`}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-app-chart-spur">
        <div
          className="h-full rounded-full"
          style={{ width: `${wert}%`, background: farbe }}
        />
      </div>
    </div>
  );
}

/* ───────────────────────────── Kurve ───────────────────────────── */

/**
 * Kleine Flächenkurve (wie "Financial Summary" in der Vorlage).
 *
 * Zeigt einen Verlauf, keine exakten Werte — deshalb ohne Achsen. Wer die
 * Zahl braucht, findet sie als Kennzahl daneben.
 */
export function Kurve({
  werte,
  hoehe = 64,
  farbe = "var(--color-app-chart)",
}: {
  werte: number[];
  hoehe?: number;
  farbe?: string;
}) {
  // Eigene Kennung je Instanz: Zwei Kurven auf einer Seite dürfen sich nicht
  // denselben Verlauf teilen, sonst zieht die zweite die Farbe der ersten.
  const kennung = useId().replace(/:/g, "");

  if (werte.length < 2) {
    return (
      <div
        className="flex items-center justify-center text-[11.5px] text-app-text-leise"
        style={{ height: hoehe }}
      >
        Noch zu wenige Daten für einen Verlauf.
      </div>
    );
  }

  const breite = 300;
  const max = Math.max(...werte);
  const min = Math.min(...werte);
  // Sind alle Werte gleich (auch: alle null), verläuft die Linie auf halber
  // Höhe. Auf der Grundlinie wäre sie kaum zu sehen und sähe nach Fehler aus.
  const spanne = max - min;
  const punkte = werte.map((w, i) => {
    const x = (i / (werte.length - 1)) * breite;
    const y =
      spanne === 0
        ? hoehe / 2
        : hoehe - ((w - min) / spanne) * (hoehe - 6) - 3;
    return [x, y] as const;
  });

  const linie = punkte.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x} ${y}`).join(" ");
  const flaeche = `${linie} L${breite} ${hoehe} L0 ${hoehe} Z`;
  const [letztX, letztY] = punkte[punkte.length - 1];

  return (
    <svg
      viewBox={`0 0 ${breite} ${hoehe}`}
      preserveAspectRatio="none"
      className="w-full overflow-visible"
      style={{ height: hoehe }}
      role="img"
      aria-label="Verlauf der letzten Wochen"
    >
      <defs>
        {/* Der Verlauf unter der Linie: auf dunklem Grund darf er kräftiger
            sein als auf hellem, sonst verschwindet die Fläche ganz. */}
        <linearGradient id={`${kennung}-flaeche`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={farbe} stopOpacity="0.3" />
          <stop offset="70%" stopColor={farbe} stopOpacity="0.06" />
          <stop offset="100%" stopColor={farbe} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={flaeche} fill={`url(#${kennung}-flaeche)`} />
      <path
        d={linie}
        fill="none"
        stroke={farbe}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      {/* Punkt auf dem letzten Wert — dort schaut man zuerst hin. */}
      <circle
        cx={letztX}
        cy={letztY}
        r="3"
        fill={farbe}
        stroke="var(--color-app-flaeche)"
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/* ───────────────────────────── Zeitleiste ───────────────────────────── */

export interface ZeitleisteEintrag {
  label: string;
  /** ISO-Datum des Beginns. */
  von: string;
  /** ISO-Datum des Endes. */
  bis: string;
  farbe?: string;
  hinweis?: string;
}

const MONATE = [
  "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
  "Jul", "Aug", "Sep", "Okt", "Nov", "Dez",
];

/**
 * Balkenplan über Monate (wie "Project Timeline" in der Vorlage).
 *
 * Die senkrechte Linie ist der heutige Tag — daran erkennt man auf einen Blick,
 * was schon fällig war. Der Zeitraum ergibt sich aus den Daten selbst, es wird
 * kein Zeitfenster erfunden.
 */
export function Zeitleiste({
  eintraege,
  heute,
}: {
  eintraege: ZeitleisteEintrag[];
  /** ISO-Datum; ohne Angabe wird nichts markiert (für stabile Darstellung). */
  heute?: string;
}) {
  const gueltig = eintraege.filter((e) => e.von && e.bis);
  if (gueltig.length === 0) {
    return <LeerHinweis>Keine Termine im gewählten Zeitraum.</LeerHinweis>;
  }

  const zahlen = gueltig.flatMap((e) => [Date.parse(e.von), Date.parse(e.bis)]);
  const heuteZahl = heute ? Date.parse(heute) : NaN;
  if (Number.isFinite(heuteZahl)) zahlen.push(heuteZahl);

  let start = Math.min(...zahlen);
  let ende = Math.max(...zahlen);
  // Auf Monatsgrenzen aufziehen, damit die Kopfzeile aufgeht.
  const startDatum = new Date(start);
  startDatum.setDate(1);
  const endDatum = new Date(ende);
  endDatum.setMonth(endDatum.getMonth() + 1, 1);
  start = startDatum.getTime();
  ende = endDatum.getTime();
  const spanne = ende - start || 1;

  // Monatsspalten aufbauen
  const spalten: { label: string; anteil: number }[] = [];
  const lauf = new Date(start);
  while (lauf.getTime() < ende) {
    const naechster = new Date(lauf);
    naechster.setMonth(naechster.getMonth() + 1, 1);
    const bis = Math.min(naechster.getTime(), ende);
    spalten.push({
      label: MONATE[lauf.getMonth()],
      anteil: ((bis - lauf.getTime()) / spanne) * 100,
    });
    lauf.setMonth(lauf.getMonth() + 1, 1);
  }

  const heuteAnteil = Number.isFinite(heuteZahl)
    ? ((heuteZahl - start) / spanne) * 100
    : null;

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[520px]">
        {/* Monatskopf */}
        <div className="flex border-b border-app-linie pb-1 pl-[34%]">
          {spalten.map((s, i) => (
            <div
              key={`${s.label}-${i}`}
              className="text-center text-[10.5px] text-app-text-still"
              style={{ width: `${s.anteil}%` }}
            >
              {s.label}
            </div>
          ))}
        </div>

        <div className="relative">
          {heuteAnteil !== null && heuteAnteil >= 0 && heuteAnteil <= 100 && (
            <div
              className="pointer-events-none absolute top-0 bottom-0 w-px bg-app-akzent/45"
              style={{ left: `calc(34% + ${heuteAnteil * 0.66}%)` }}
              aria-hidden
            />
          )}

          {gueltig.map((e, i) => {
            const von = Date.parse(e.von);
            const bis = Date.parse(e.bis);
            const links = ((Math.min(von, bis) - start) / spanne) * 100;
            const breite = Math.max(((Math.abs(bis - von) || 1) / spanne) * 100, 1.2);
            return (
              <div key={`${e.label}-${i}`} className="flex items-center py-[5px]">
                <div className="w-[34%] shrink-0 truncate pr-3 text-[12px] text-app-text">
                  {e.label}
                </div>
                <div className="relative h-4 flex-1">
                  <div
                    className="absolute top-0 h-4 rounded-[3px]"
                    style={{
                      left: `${links}%`,
                      width: `${breite}%`,
                      background: e.farbe ?? "var(--color-app-chart)",
                    }}
                    title={e.hinweis}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ───────────────────────────── Listen ───────────────────────────── */

const INITIAL_FARBEN = [
  "#2563EB", "#0E7490", "#7C3AED", "#B54708", "#047857", "#B42318",
];

/** Rundes Namenskürzel — Farbe leitet sich aus dem Namen ab, bleibt also gleich. */
export function Initialen({ name, groesse = 28 }: { name: string; groesse?: number }) {
  const teile = (name || "?").trim().split(/\s+/);
  const kuerzel =
    teile.length > 1
      ? `${teile[0][0] ?? ""}${teile[teile.length - 1][0] ?? ""}`
      : (teile[0] ?? "?").slice(0, 2);
  let summe = 0;
  for (const zeichen of name || "?") summe += zeichen.charCodeAt(0);
  const farbe = INITIAL_FARBEN[summe % INITIAL_FARBEN.length];

  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
      style={{
        width: groesse,
        height: groesse,
        background: farbe,
        fontSize: groesse * 0.38,
      }}
      aria-hidden
    >
      {kuerzel.toUpperCase()}
    </span>
  );
}

export function ListenZeile({
  titel,
  unterzeile,
  rechts,
  vorne,
  onClick,
}: {
  titel: ReactNode;
  unterzeile?: ReactNode;
  rechts?: ReactNode;
  vorne?: ReactNode;
  onClick?: () => void;
}) {
  const inhalt = (
    <>
      {vorne}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] text-app-text">{titel}</span>
        {unterzeile && (
          <span className="mt-0.5 block truncate text-[11.5px] text-app-text-still">
            {unterzeile}
          </span>
        )}
      </span>
      {rechts && <span className="shrink-0">{rechts}</span>}
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="flex w-full cursor-pointer items-center gap-2.5 border-b border-app-linie px-4 py-2.5 text-left last:border-b-0 hover:bg-app-flaeche-hoch"
      >
        {inhalt}
      </button>
    );
  }
  return (
    <div className="flex items-center gap-2.5 border-b border-app-linie px-4 py-2.5 last:border-b-0">
      {inhalt}
    </div>
  );
}

export function LeerHinweis({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-app-sm border border-dashed border-app-linie-stark px-4 py-6 text-center text-[12.5px] text-app-text-still">
      {children}
    </div>
  );
}

/* ───────────────────────────── Kopfzeile einer Ansicht ───────────────────────────── */

/**
 * Seitenkopf wie in der Vorlage: großer Titel, darunter eine technische
 * Kennung, rechts Zustand und Zuständigkeit.
 */
export function SeitenKopf({
  titel,
  kennung,
  plakette,
  rechts,
  aktionen,
}: {
  titel: string;
  kennung?: ReactNode;
  plakette?: ReactNode;
  rechts?: ReactNode;
  aktionen?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="text-[23px] font-semibold tracking-tight text-app-text">
            {titel}
          </h1>
          {plakette}
        </div>
        {kennung && (
          <div className="mt-0.5 text-[12px] text-app-text-still">{kennung}</div>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {rechts}
        {aktionen}
      </div>
    </div>
  );
}
