/**
 * Umfang der Oberfläche — welche Bereiche diese Fassung überhaupt zeigt.
 *
 * WARUM ES DIESE DATEI GIBT
 * =========================
 * Dieselbe Oberfläche wird dreimal ausgeliefert. Gebraucht wird an jedem der
 * drei Orte etwas anderes, und was man nicht braucht, steht im Weg:
 *
 *   "voll"    Windows-Paket auf dem Bürorechner — alles.
 *   "buero"   Büro-Website — alles AUSSER Baufotos.
 *   "fotos"   Baustellen-Website — Dashboard, Baufotos, Projekte.
 *
 * WARUM DIE BÜRO-WEBSITE KEINE BAUFOTOS HAT
 * =========================================
 * Weil es dafür die Baustellen-Website gibt. Fotos entstehen am Bau, mit dem
 * Handy in der Hand; sie im Büro ein zweites Mal anzubieten heißt nur, dass
 * es zwei Wege für dieselbe Sache gibt und niemand weiß, welcher der richtige
 * ist. Beide Websites hängen ohnehin an derselben Datenbank — was auf der
 * Baustelle hochgeladen wird, ist im Büro sofort da, und abgeholt wird es vom
 * Skript auf dem Bürorechner, nicht von Hand aus der Oberfläche.
 *
 * WARUM DAS WINDOWS-PAKET TROTZDEM ALLES BEHÄLT
 * =============================================
 * Es ist der Notweg. Wenn das Netz weg ist oder Render schläft, muss auf dem
 * Bürorechner alles gehen — auch Fotos ansehen. Ein Paket, das im Ernstfall
 * weniger kann als die Website, ist kein Notweg.
 *
 * WIE DER WERT HINEINKOMMT
 * ========================
 * Beim Bauen über ``APP_UMFANG``; render.yaml setzt "buero" bzw. lässt der
 * Dockerfile-Standard "fotos" stehen, das Windows-Paket setzt nichts und
 * bekommt "voll". Next.js backt den Wert als ``NEXT_PUBLIC_UMFANG`` ins
 * Bündel — zur Laufzeit ist er eine Konstante.
 *
 * Bewusst kein Schalter in der Oberfläche: Das sind nicht drei Zustände
 * desselben Programms, sondern drei Auslieferungen. Ein Schalter würde nur
 * dazu führen, dass jemand auf der Baustelle versehentlich die Büroansicht
 * einschaltet und sich dann durch eine Navigation kämpft, deren Bereiche
 * ohne Netzlaufwerk und Vorlagen ohnehin nicht zu Ende zu bedienen sind.
 */

export type Umfang = "voll" | "buero" | "fotos";

function gelesen(): Umfang {
  switch (process.env.NEXT_PUBLIC_UMFANG) {
    case "fotos":
      return "fotos";
    case "buero":
      return "buero";
    default:
      // Auch bei Tippfehlern: lieber zu viel zeigen als eine Oberfläche, in
      // der ohne erkennbaren Grund halbe Bereiche fehlen.
      return "voll";
  }
}

export const UMFANG: Umfang = gelesen();

/** Nur Baufotos und Projekte — die Baustellen-Website. */
export const NUR_FOTOS = UMFANG === "fotos";

/** Alles außer Baufotos — die Büro-Website. */
export const OHNE_FOTOS = UMFANG === "buero";

/** Gibt es die Baufoto-Bereiche in dieser Fassung? */
export const MIT_FOTOS = UMFANG !== "buero";
