/**
 * Fotos im Browser verkleinern, bevor sie hochgeladen werden.
 *
 * Warum das nötig ist: Ein Handyfoto ist 3–8 MB groß. Auf der Baustelle hängt
 * das Gerät oft an einer schwachen Mobilfunkverbindung — ein Upload in
 * Originalgröße dauert dort minutenlang und bricht regelmäßig ab. Nach dem
 * Verkleinern bleiben typischerweise 200–500 kB pro Foto übrig, ohne dass für
 * die Mängeldokumentation Erkennbarkeit verloren geht.
 *
 * Das Backend begrenzt die Größe zusätzlich (app/services/bilder.py) — hier
 * geht es allein darum, dass die Bytes überhaupt durch die Leitung kommen.
 */

export interface KompressionsOptionen {
  /** Längste Kante des Ergebnisses in Pixeln. */
  maxKante?: number;
  /** JPEG-Qualität zwischen 0 und 1. */
  qualitaet?: number;
  /** Dateien unter dieser Größe bleiben unangetastet. */
  minGroesseBytes?: number;
}

const STANDARD: Required<KompressionsOptionen> = {
  maxKante: 1600,
  qualitaet: 0.72,
  minGroesseBytes: 250 * 1024,
};

interface GeladenesBild {
  breite: number;
  hoehe: number;
  quelle: ImageBitmap | HTMLImageElement;
  /** Muss nach dem Zeichnen aufgerufen werden (Object-URL / Bitmap freigeben). */
  aufraeumen: () => void;
}

/** Lädt das Bild — bevorzugt per createImageBitmap (schneller, dreht nach EXIF). */
async function ladeBild(datei: File): Promise<GeladenesBild> {
  if (typeof createImageBitmap === "function") {
    try {
      const bitmap = await createImageBitmap(datei, { imageOrientation: "from-image" });
      return {
        breite: bitmap.width,
        hoehe: bitmap.height,
        quelle: bitmap,
        aufraeumen: () => bitmap.close(),
      };
    } catch {
      /* fällt unten auf das Image-Element zurück */
    }
  }

  const url = URL.createObjectURL(datei);
  try {
    const bild = await new Promise<HTMLImageElement>((fertig, fehler) => {
      const element = new Image();
      element.onload = () => fertig(element);
      element.onerror = () => fehler(new Error("Bild nicht lesbar"));
      element.src = url;
    });
    return {
      breite: bild.naturalWidth,
      hoehe: bild.naturalHeight,
      quelle: bild,
      aufraeumen: () => URL.revokeObjectURL(url),
    };
  } catch (err) {
    URL.revokeObjectURL(url);
    throw err;
  }
}

/**
 * Verkleinert ein Foto und gibt eine neue Datei zurück.
 *
 * Bei jedem Problem (kein Bild, Decoder streikt, Ergebnis wäre größer) kommt
 * die Originaldatei zurück — ein Foto darf nie deshalb verloren gehen, weil
 * die Komprimierung nicht klappt.
 */
export async function komprimiereBild(
  datei: File,
  optionen: KompressionsOptionen = {}
): Promise<File> {
  const { maxKante, qualitaet, minGroesseBytes } = { ...STANDARD, ...optionen };

  // HEIC kommt hier durch, ohne verkleinert zu werden: Chrome und Edge können
  // das Format nicht dekodieren, `ladeBild` scheitert und die Originaldatei
  // geht hinaus. Das ist gewollt — der Server wandelt sie in JPEG um (siehe
  // app/services/bildformate). Ein iPhone-Foto ist dann groß, kommt aber an;
  // es zurückzuweisen wäre schlechter.
  if (datei.type && !datei.type.startsWith("image/")) return datei;
  if (datei.size <= minGroesseBytes) return datei;

  try {
    const { breite, hoehe, quelle, aufraeumen } = await ladeBild(datei);
    if (!breite || !hoehe) {
      aufraeumen();
      return datei;
    }

    const faktor = Math.min(1, maxKante / Math.max(breite, hoehe));
    const zielBreite = Math.max(1, Math.round(breite * faktor));
    const zielHoehe = Math.max(1, Math.round(hoehe * faktor));

    const canvas = document.createElement("canvas");
    canvas.width = zielBreite;
    canvas.height = zielHoehe;
    const kontext = canvas.getContext("2d");
    if (!kontext) {
      aufraeumen();
      return datei;
    }
    kontext.drawImage(quelle as CanvasImageSource, 0, 0, zielBreite, zielHoehe);
    aufraeumen();

    const blob = await new Promise<Blob | null>((fertig) =>
      canvas.toBlob(fertig, "image/jpeg", qualitaet)
    );
    if (!blob || blob.size >= datei.size) return datei;

    const name = datei.name.replace(/\.[^.]+$/, "") || "foto";
    return new File([blob], `${name}.jpg`, {
      type: "image/jpeg",
      lastModified: datei.lastModified,
    });
  } catch {
    return datei;
  }
}

/** Komprimiert mehrere Fotos hintereinander (schont den Speicher des Handys). */
export async function komprimiereAlle(
  dateien: File[],
  optionen?: KompressionsOptionen
): Promise<File[]> {
  const ergebnis: File[] = [];
  for (const datei of dateien) {
    ergebnis.push(await komprimiereBild(datei, optionen));
  }
  return ergebnis;
}

/** "2,4 MB" — für die Anzeige an der Vorschau. */
export function formatiereGroesse(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}
