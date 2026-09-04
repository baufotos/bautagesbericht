"use client";

/**
 * Bausteine des Designsystems "ui" (siehe Token-Block in app/globals.css).
 *
 * Gestaltungsregeln, die hier — und nur hier — festgelegt sind:
 *   • Flächen (ui-surface) liegen vor dem Seitengrund (ui-bg), getrennt durch
 *     eine 1-px-Linie aus 8 % Weiß; Tiefe kommt aus dem Schatten, nicht aus
 *     schweren Rahmen.
 *   • Runde Formen durchgehend: Karten 12 px, Knöpfe und Chips vollrund.
 *   • Label klein, grau, Mono, gesperrt — Wert normal und in Textfarbe. Diese
 *     Hierarchie ist der rote Faden des ganzen Moduls.
 *   • Der Akzent kommt ausschließlich aus ui-accent, die Schrift darauf aus
 *     ui-accent-text. Nie "text-white" schreiben: In der hellen Fassung ist
 *     der Akzent dunkel, und weiße Schrift wäre dort unsichtbar.
 *
 * Wer eine neue Ansicht baut, sollte hier zuerst nachsehen, statt Klassen zu
 * wiederholen — so bleibt das Bild einheitlich und später austauschbar.
 */

import { ChevronDown, ChevronRight, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";

import { statusFarben } from "@/lib/farben";

/* ───────── Flächen ───────── */

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`bg-ui-surface border border-ui-line rounded-ui ${className}`}
    >
      {children}
    </div>
  );
}

/**
 * Einklappbare Karte — der Aufbau aus der Bürosoftware: Bezeichnung links in
 * der Akzentfarbe, Pfeil zum Auf- und Zuklappen, Inhalt rechts.
 */
export function Section({
  titel,
  children,
  offenStart = true,
  zusatz,
  icon: Icon,
  warnung = false,
}: {
  titel: string;
  children: ReactNode;
  offenStart?: boolean;
  /** Kurzinfo in der Kopfzeile, auch im zugeklappten Zustand sichtbar. */
  zusatz?: ReactNode;
  icon?: LucideIcon;
  warnung?: boolean;
}) {
  const [offen, setOffen] = useState(offenStart);

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOffen((v) => !v)}
        aria-expanded={offen}
        className="w-full flex items-center gap-2 px-4 py-3 text-left cursor-pointer hover:bg-ui-surface-muted transition-colors"
      >
        {offen ? (
          <ChevronDown size={15} className="text-ui-accent shrink-0" />
        ) : (
          <ChevronRight size={15} className="text-ui-accent shrink-0" />
        )}
        {Icon && <Icon size={15} className="text-ui-text-muted shrink-0" />}
        <span
          className={`font-mono text-[11px] tracking-[0.12em] uppercase ${
            warnung ? "text-ui-danger" : "text-ui-accent"
          }`}
        >
          {titel}
        </span>
        {zusatz && (
          <span className="ml-auto text-[12px] text-ui-text-muted truncate pl-3">
            {zusatz}
          </span>
        )}
      </button>
      {offen && (
        <div className="border-t border-ui-line px-4 py-4">{children}</div>
      )}
    </Card>
  );
}

/* ───────── Beschriftung und Eingaben ───────── */

export function Label({ children }: { children: ReactNode }) {
  return (
    <span className="block font-mono text-[10.5px] tracking-[0.1em] uppercase text-ui-text-muted">
      {children}
    </span>
  );
}

export function Field({
  label,
  children,
  hinweis,
  fehler,
  className = "",
}: {
  label: string;
  children: ReactNode;
  hinweis?: ReactNode;
  fehler?: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <Label>{label}</Label>
      <div className="mt-1.5">{children}</div>
      {fehler ? (
        <p className="mt-1 text-[12px] text-ui-danger">{fehler}</p>
      ) : hinweis ? (
        <p className="mt-1 text-[12px] text-ui-text-muted">{hinweis}</p>
      ) : null}
    </div>
  );
}

/** Nur-Lese-Darstellung eines Werts (Label oben, Wert darunter). */
export function ReadOnlyField({
  label,
  wert,
  hervorgehoben = false,
}: {
  label: string;
  wert: ReactNode;
  hervorgehoben?: boolean;
}) {
  return (
    <div>
      <Label>{label}</Label>
      <div
        className={`mt-1 text-[13.5px] ${
          hervorgehoben ? "text-ui-danger font-semibold" : "text-ui-text"
        }`}
      >
        {wert || <span className="text-ui-text-faint">—</span>}
      </div>
    </div>
  );
}

/* Eingabefelder liegen auf der ruhigen Fläche und heben sich beim Tippen
   heraus — auf Dunkel ist ein leuchtender Rahmen zu laut, eine Spur mehr
   Helligkeit reicht als Rückmeldung. */
const EINGABE_KLASSEN =
  "w-full bg-ui-surface-muted border border-ui-line rounded-ui-sm px-3 py-2.5 text-[14px] text-ui-text " +
  "outline-none transition-colors focus:border-ui-line-strong focus:bg-ui-surface " +
  "placeholder:text-ui-text-faint " +
  "disabled:bg-ui-surface-muted disabled:text-ui-text-muted";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { className = "", ...rest } = props;
  return <input {...rest} className={`${EINGABE_KLASSEN} ${className}`} />;
}

/**
 * ``ComponentPropsWithRef`` statt ``TextareaHTMLAttributes``: Damit laesst sich
 * ein ``ref`` durchgeben. Gebraucht wird das dort, wo etwas an der
 * Schreibmarke eingesetzt wird — die Textbausteine der Anzeigen-Antwort landen
 * an der Stelle, an der der Zeiger steht, nicht am Ende des Feldes. In React 19
 * reist ``ref`` als gewoehnliche Eigenschaft mit ``...rest`` mit.
 */
export function Textarea(props: React.ComponentPropsWithRef<"textarea">) {
  const { className = "", ...rest } = props;
  return (
    <textarea
      {...rest}
      className={`${EINGABE_KLASSEN} min-h-[92px] resize-y leading-relaxed ${className}`}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  const { className = "", ...rest } = props;
  return <select {...rest} className={`${EINGABE_KLASSEN} ${className}`} />;
}

export function Checkbox({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (wert: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex items-center gap-2.5 text-[13.5px] ${
        disabled ? "text-ui-text-faint" : "text-ui-text cursor-pointer"
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="size-4 accent-ui-accent cursor-pointer disabled:cursor-not-allowed"
      />
      {label}
    </label>
  );
}

/* ───────── Schaltflächen ───────── */

type ButtonVariante = "primaer" | "sekundaer" | "still" | "gefahr";

/* text-ui-accent-text statt "text-white": Der Akzent ist im dunklen Theme
   hell und im hellen dunkel — eine fest verdrahtete weiße Schrift wäre in
   einer der beiden Fassungen unsichtbar. */
const BUTTON_VARIANTEN: Record<ButtonVariante, string> = {
  primaer:
    "bg-ui-accent text-ui-accent-text border border-ui-accent hover:bg-ui-accent-hover",
  sekundaer:
    "bg-ui-surface-muted text-ui-text border border-ui-line hover:border-ui-line-strong hover:bg-ui-surface",
  still:
    "bg-transparent text-ui-text-muted border border-transparent hover:bg-ui-surface-muted hover:text-ui-text",
  gefahr:
    "bg-ui-danger-soft text-ui-danger border border-transparent hover:border-ui-danger",
};

function buttonKlassen(variante: ButtonVariante, className: string) {
  return (
    "inline-flex items-center justify-center gap-1.5 rounded-full px-4 py-2.5 " +
    "text-[13px] font-medium tracking-[0.01em] cursor-pointer transition-colors " +
    "disabled:opacity-45 disabled:cursor-not-allowed " +
    `${BUTTON_VARIANTEN[variante]} ${className}`
  );
}

export function Button({
  children,
  variante = "primaer",
  icon: Icon,
  className = "",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variante?: ButtonVariante;
  icon?: LucideIcon;
}) {
  return (
    <button {...rest} className={buttonKlassen(variante, className)}>
      {Icon && <Icon size={15} />}
      {children}
    </button>
  );
}

/**
 * Link, der wie ein Knopf aussieht — für Downloads (Word-Export, Anhänge).
 * Ein ``<button>`` in einem ``<a>`` zu verschachteln ist ungültiges HTML,
 * deshalb dieser eigene Baustein.
 */
export function LinkButton({
  children,
  variante = "sekundaer",
  icon: Icon,
  className = "",
  ...rest
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  variante?: ButtonVariante;
  icon?: LucideIcon;
}) {
  return (
    <a {...rest} className={buttonKlassen(variante, className)}>
      {Icon && <Icon size={15} />}
      {children}
    </a>
  );
}

/**
 * Waagerecht scrollbare Leiste für Filter- und Umschaltknöpfe.
 *
 * Auf einem Handy sind acht Statusfilter drei Zeilen hoch — bevor überhaupt
 * ein Mangel zu sehen ist. Eine wischbare Zeile ist die übliche App-Lösung.
 * Die negativen Ränder (-mx-4) lassen die Leiste bis an den Bildschirmrand
 * laufen, damit sichtbar ist, dass es rechts weitergeht.
 */
export function ChipLeiste({ children }: { children: ReactNode }) {
  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:overflow-visible sm:px-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      <div className="flex w-max items-center gap-2 sm:w-auto sm:flex-wrap">
        {children}
      </div>
    </div>
  );
}

/** Filter-/Umschalt-Knopf (Segmented Control). */
export function Chip({
  aktiv,
  children,
  onClick,
}: {
  aktiv: boolean;
  children: ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`font-mono text-[11px] tracking-[0.06em] px-3 py-1.5 rounded-full border cursor-pointer whitespace-nowrap transition-colors ${
        aktiv
          ? "bg-ui-accent text-ui-accent-text border-ui-accent"
          : "bg-ui-surface-muted text-ui-text-muted border-ui-line hover:border-ui-line-strong hover:text-ui-text"
      }`}
    >
      {children}
    </button>
  );
}

/* ───────── Anzeige ───────── */

/**
 * Status-Badge. Die Farbe kommt aus den Stammdaten (Feld ``farbe`` am Status)
 * und wird deshalb als Inline-Style gesetzt — Tailwind kann Klassen für
 * frei konfigurierbare Farben nicht zur Bauzeit erzeugen.
 *
 * Aufgehellt wird sie in der dunklen Fassung von ``statusFarben`` (lib/farben),
 * sonst wäre ein für Weiß gewähltes Dunkelrot hier nicht mehr zu lesen.
 */
export function StatusBadge({
  text,
  farbe,
  klein = false,
}: {
  text: string;
  farbe?: string;
  klein?: boolean;
}) {
  const { ton, rand, flaeche } = statusFarben(farbe);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium whitespace-nowrap ${
        klein ? "px-2 py-0.5 text-[10.5px]" : "px-2.5 py-1 text-[11.5px]"
      }`}
      style={{ color: ton, borderColor: rand, background: flaeche }}
    >
      <span
        className="size-1.5 rounded-full shrink-0"
        style={{ background: ton }}
      />
      {text}
    </span>
  );
}

const PRIO_FARBEN: Record<string, string> = {
  hoch: "text-ui-danger",
  mittel: "text-ui-warn",
  niedrig: "text-ui-text-muted",
};

export function PrioritaetText({ wert }: { wert: string }) {
  return (
    <span className={`text-[12px] ${PRIO_FARBEN[wert] || "text-ui-text-muted"}`}>
      {wert}
    </span>
  );
}

export function EmptyState({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`border border-dashed border-ui-line-strong rounded-ui px-6 py-8 text-center text-[13.5px] text-ui-text-muted ${className}`}
    >
      {children}
    </div>
  );
}

export function Meldung({
  art,
  children,
}: {
  art: "fehler" | "hinweis" | "erfolg";
  children: ReactNode;
}) {
  const stile = {
    fehler: "bg-ui-danger-soft text-ui-danger",
    hinweis: "bg-ui-warn-soft text-ui-warn",
    erfolg: "bg-ui-ok-soft text-ui-ok",
  }[art];
  return (
    <div className={`rounded-ui px-3.5 py-2.5 text-[13px] ${stile}`}>{children}</div>
  );
}

/** Kleine Überschrift über einer Liste oder einem Block. */
export function Bereichstitel({
  children,
  aktion,
}: {
  children: ReactNode;
  aktion?: ReactNode;
}) {
  return (
    // flex-wrap ist hier nicht Kosmetik: Auf einem 390-px-Bildschirm passen
    // Titel und Schaltflächen nicht in eine Zeile, und ohne Umbruch würde die
    // ganze Seite breiter als das Display (waagerechtes Scrollen).
    <div className="mb-3 flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
      <span className="font-mono text-[11px] tracking-[0.12em] uppercase text-ui-text-muted">
        {children}
      </span>
      {aktion}
    </div>
  );
}

/* ───────── Datumshilfen (überall in der Mängelansicht gebraucht) ───────── */

/** "2026-08-26" -> "26.08.2026"; leere Werte werden zu "". */
export function formatDatum(iso: string | null | undefined): string {
  if (!iso) return "";
  const [jahr, monat, tag] = iso.slice(0, 10).split("-");
  if (!jahr || !monat || !tag) return "";
  return `${tag}.${monat}.${jahr}`;
}

/** Kurzform wie in der Kopfzeile der Bürosoftware: "26.08.26". */
export function formatDatumKurz(iso: string | null | undefined): string {
  const lang = formatDatum(iso);
  return lang ? `${lang.slice(0, 6)}${lang.slice(8)}` : "";
}

export function heuteIso(): string {
  const jetzt = new Date();
  const monat = String(jetzt.getMonth() + 1).padStart(2, "0");
  const tag = String(jetzt.getDate()).padStart(2, "0");
  return `${jetzt.getFullYear()}-${monat}-${tag}`;
}

/** Datum in ISO-Form um Tage verschoben — für Fristvorschläge. */
export function isoPlusTage(tage: number): string {
  const ziel = new Date();
  ziel.setDate(ziel.getDate() + tage);
  const monat = String(ziel.getMonth() + 1).padStart(2, "0");
  const tag = String(ziel.getDate()).padStart(2, "0");
  return `${ziel.getFullYear()}-${monat}-${tag}`;
}
