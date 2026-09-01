/**
 * Anzeigeformate an einer Stelle.
 *
 * Warum zentral: In einer Liste aus Mängeln, Berichten und Fotosätzen fällt
 * sofort auf, wenn dasselbe Datum an drei Stellen unterschiedlich geschrieben
 * steht. Und "vor 3 Tagen" ist beim Überfliegen einer Aktivitätenliste
 * schneller zu erfassen als "17.08.2026" — deshalb gibt es beides.
 *
 * Hinweis: ``components/ui.tsx`` hat noch die älteren ``formatDatum`` /
 * ``formatDatumKurz``. Sie sind dort in den Formularbausteinen verwurzelt und
 * bleiben; neue Ansichten nehmen dieses Modul.
 */

/**
 * Zeitangabe des Servers in Millisekunden umrechnen — die einzige richtige
 * Stelle dafür.
 *
 * Das Backend liefert **naive** Zeitstempel in UTC ("2026-08-20T19:02:42",
 * ohne Zeitzonen-Kennung). JavaScript liest so etwas als *Ortszeit* — in
 * Deutschland also zwei Stunden zu früh, wodurch ein gerade angelegter
 * Eintrag als "vor 2 Std." erscheint. Deshalb wird hier ausdrücklich als UTC
 * ausgelegt.
 *
 * Reine Datumsangaben ("2026-08-19") bekommen die lokale Mittagszeit: Ein
 * Datum hat keine Uhrzeit, und Mitternacht würde durch die Zeitzone leicht auf
 * den Vortag kippen.
 *
 * Gibt 0 zurück, wenn nichts Verwertbares übergeben wurde.
 */
export function alsZeitstempel(iso: string | null | undefined): number {
  if (!iso) return 0;
  const text = iso.trim();
  if (text.length === 0) return 0;

  let wert: number;
  if (text.length <= 10) {
    wert = Date.parse(`${text}T12:00:00`);
  } else if (/[Zz]$|[+-]\d{2}:?\d{2}$/.test(text)) {
    wert = Date.parse(text);
  } else {
    wert = Date.parse(`${text}Z`);
  }
  return Number.isFinite(wert) ? wert : 0;
}

/** "2026-08-19" → "19.08.2026". Leere Werte werden zu "". */
export function formatDatumIso(iso: string | null | undefined): string {
  if (!iso) return "";
  const [jahr, monat, tag] = iso.slice(0, 10).split("-");
  if (!jahr || !monat || !tag) return "";
  return `${tag}.${monat}.${jahr}`;
}

/** "2026-08-19" → "19.08.26" — für enge Stellen wie Kartenkopfzeilen. */
export function formatDatumKurzIso(iso: string | null | undefined): string {
  const lang = formatDatumIso(iso);
  return lang ? `${lang.slice(0, 6)}${lang.slice(8)}` : "";
}

const WOCHENTAGE = [
  "Sonntag", "Montag", "Dienstag", "Mittwoch",
  "Donnerstag", "Freitag", "Samstag",
];

/** "Mittwoch, 19.08.2026" — für Datumsüberschriften in Gruppen. */
export function formatDatumLang(iso: string | null | undefined): string {
  if (!iso) return "";
  const datum = new Date(`${iso.slice(0, 10)}T12:00:00`);
  if (Number.isNaN(datum.getTime())) return formatDatumIso(iso);
  return `${WOCHENTAGE[datum.getDay()]}, ${formatDatumIso(iso)}`;
}

/**
 * Dateigröße in der Schreibweise, die im Explorer steht: "840 kB", "2,4 MB".
 * Dezimalkomma, weil das Ergebnis in deutschen Oberflächentexten landet.
 */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 kB";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

/**
 * Grobe Zeitangabe relativ zu jetzt: "gerade eben", "vor 3 Std.",
 * "vor 2 Tagen". Absichtlich ohne Bibliothek — es sind sechs Fälle, und jede
 * zusätzliche Abhängigkeit müsste beim Start auf der Baustelle mitgeladen
 * werden.
 */
export function relativeZeit(iso: string | null | undefined): string {
  const zeitpunkt = alsZeitstempel(iso);
  if (zeitpunkt === 0) return "";
  const millis = Date.now() - zeitpunkt;
  // Kleine Vorlaufzeiten (Uhrenabweichung zwischen Server und Gerät) nicht als
  // Zukunft ausgeben — "in 3 Minuten hochgeladen" wäre nur verwirrend.
  if (millis < 0) return "gerade eben";

  const minuten = Math.floor(millis / 60000);
  if (minuten < 2) return "gerade eben";
  if (minuten < 60) return `vor ${minuten} Min.`;

  const stunden = Math.floor(minuten / 60);
  if (stunden < 24) return `vor ${stunden} Std.`;

  const tage = Math.floor(stunden / 24);
  if (tage === 1) return "gestern";
  if (tage < 7) return `vor ${tage} Tagen`;

  const wochen = Math.floor(tage / 7);
  if (wochen < 5) return `vor ${wochen} Woche${wochen === 1 ? "" : "n"}`;

  const monate = Math.floor(tage / 30);
  if (monate < 12) return `vor ${monate} Monat${monate === 1 ? "" : "en"}`;
  // Älter als ein Jahr: Ein Datum sagt dann mehr als "vor 14 Monaten".
  return formatDatumIso(new Date(zeitpunkt).toISOString());
}

/** Heutiges Datum als ISO-Zeichenkette (lokale Zeitzone, nicht UTC). */
export function heuteIso(): string {
  const jetzt = new Date();
  const monat = String(jetzt.getMonth() + 1).padStart(2, "0");
  const tag = String(jetzt.getDate()).padStart(2, "0");
  return `${jetzt.getFullYear()}-${monat}-${tag}`;
}
