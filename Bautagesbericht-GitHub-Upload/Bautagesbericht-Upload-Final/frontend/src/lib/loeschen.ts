import { konfliktAnzahl } from "./api";

/**
 * Löschen mit Rückfrage.
 *
 * Der Server lehnt den ersten Versuch mit 409 ab, wenn noch abhängige Daten
 * daran hängen, und nennt deren Anzahl. Erst nach dem ausdrücklichen OK wird
 * mit ``force=true`` wirklich gelöscht.
 *
 * Warum das zentral liegt: Genau dieses Muster brauchen Projekte, Empfänger,
 * Firmen und Pläne. Vier Kopien derselben Logik wären vier Gelegenheiten,
 * die Rückfrage zu vergessen — und dann verschwindet unbemerkt eine
 * Mängelhistorie.
 */
export async function loeschenMitRueckfrage(
  entfernen: (force: boolean) => Promise<void>,
  bezeichnung: string,
  /** Was beim Erzwingen mit gelöscht wird — wird in die Rückfrage eingebaut. */
  folgeText = "Sie werden dabei mit entfernt."
): Promise<string | null> {
  try {
    await entfernen(false);
    return null;
  } catch (err) {
    const anzahl = konfliktAnzahl(err);
    if (anzahl === null) {
      return err instanceof Error ? err.message : "Löschen fehlgeschlagen.";
    }
    const ok = window.confirm(
      `${bezeichnung} wird gelöscht.\n\n` +
        `Dazu gehören noch ${anzahl} abhängige Datensätze. ${folgeText}\n\n` +
        `Wirklich löschen?`
    );
    if (!ok) return null;
    try {
      await entfernen(true);
      return null;
    } catch (err2) {
      return err2 instanceof Error ? err2.message : "Löschen fehlgeschlagen.";
    }
  }
}
