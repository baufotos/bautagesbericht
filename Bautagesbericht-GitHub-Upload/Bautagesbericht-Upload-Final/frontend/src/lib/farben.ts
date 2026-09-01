/**
 * Frei konfigurierte Farben so aufbereiten, dass sie in beiden Fassungen lesbar sind.
 *
 * DAS PROBLEM
 * ===========
 * Die Farben der Mängel-Status und der Plan-Markierungen stehen in den
 * Stammdaten — das Büro wählt sie selbst (z. B. ``#B45309`` für "Nachfrist").
 * Gewählt wurden sie für einen weißen Hintergrund. Auf der dunklen Fläche
 * ergibt dasselbe Braunorange 2,5:1 gegen ``#16171A`` und fällt damit durch
 * WCAG AA — der Status wäre da, aber kaum zu lesen.
 *
 * DIE LÖSUNG
 * ==========
 * ``color-mix()`` hellt den gespeicherten Wert für die dunkle Fassung auf,
 * ohne ihn zu verändern: Die Stammdaten bleiben wie sie sind, und wer auf
 * "hell" schaltet, sieht wieder genau die gewählte Farbe (Anteil 0 %).
 *
 * Der Umweg über die CSS-Funktion statt einer Rechnung in JavaScript ist
 * Absicht: Beim Umschalten der Fassung ändert sich nur eine Variable, ohne
 * dass React etwas neu berechnen oder auch nur davon wissen muss.
 *
 * Kann ein Browser ``color-mix()`` nicht (vor Chrome/Edge 111, Safari 16.2),
 * verwirft er die Eigenschaft und es gilt die geerbte Textfarbe — lesbar,
 * nur ohne die farbige Zuordnung.
 */

export interface StatusFarben {
  /** Schrift und Punkt — aufgehellt, damit AA erreicht wird. */
  ton: string;
  /** Rand: dieselbe Farbe, stark verdünnt. */
  rand: string;
  /** Hinterlegte Fläche: nur ein Hauch, damit die Schrift trägt. */
  flaeche: string;
}

/** Ersatzton, wenn in den Stammdaten keine Farbe hinterlegt ist. */
export const STATUS_ERSATZTON = "#8A8B93";

export function statusFarben(farbe?: string | null): StatusFarben {
  const gewaehlt = (farbe || "").trim() || STATUS_ERSATZTON;
  return {
    ton: `color-mix(in srgb, ${gewaehlt}, var(--t-tint) var(--t-tint-anteil))`,
    rand: `color-mix(in srgb, ${gewaehlt} 42%, transparent)`,
    flaeche: `color-mix(in srgb, ${gewaehlt} 16%, transparent)`,
  };
}
