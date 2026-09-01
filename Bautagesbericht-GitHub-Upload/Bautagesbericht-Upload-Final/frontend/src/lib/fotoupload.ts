import { api } from "./api";
import { komprimiereBild } from "./bildkompression";
import type { MangelFoto } from "./types";

/**
 * Fotos einzeln und mit Wiederholung hochladen.
 *
 * Auf der Baustelle bricht die Verbindung mitten im Upload ab. Deshalb geht
 * jedes Foto in einem eigenen Aufruf raus: Ein Abbruch kostet dann höchstens
 * dieses eine Foto, nicht die ganze Aufnahme. Fehlgeschlagene Fotos werden
 * zurückgemeldet, damit die Oberfläche gezielt zum Wiederholen anbieten kann,
 * statt alles noch einmal zu schicken.
 */

export interface UploadFortschritt {
  /** 1-basierter Index des Fotos, das gerade läuft. */
  aktuell: number;
  gesamt: number;
  dateiname: string;
}

export interface UploadErgebnis {
  hochgeladen: MangelFoto[];
  fehlgeschlagen: { datei: File; fehler: string }[];
}

const VERSUCHE = 2;

export async function ladeFotosHoch(
  mangelId: number,
  dateien: File[],
  onFortschritt?: (stand: UploadFortschritt) => void
): Promise<UploadErgebnis> {
  const hochgeladen: MangelFoto[] = [];
  const fehlgeschlagen: UploadErgebnis["fehlgeschlagen"] = [];

  for (let i = 0; i < dateien.length; i++) {
    const datei = dateien[i];
    onFortschritt?.({ aktuell: i + 1, gesamt: dateien.length, dateiname: datei.name });

    // Erst verkleinern, dann senden — das ist der Unterschied zwischen
    // "geht durch" und "läuft in den Timeout".
    const klein = await komprimiereBild(datei);

    let letzterFehler = "Upload fehlgeschlagen";
    let erfolg = false;
    for (let versuch = 1; versuch <= VERSUCHE && !erfolg; versuch++) {
      try {
        const neue = await api.maengel.uploadFotos(mangelId, [klein]);
        hochgeladen.push(...neue);
        erfolg = true;
      } catch (err) {
        letzterFehler = err instanceof Error ? err.message : "Upload fehlgeschlagen";
      }
    }
    if (!erfolg) fehlgeschlagen.push({ datei, fehler: letzterFehler });
  }

  return { hochgeladen, fehlgeschlagen };
}
