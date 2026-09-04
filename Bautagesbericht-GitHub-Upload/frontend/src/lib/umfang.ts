/**
 * Umfang der Oberfläche — welche Bereiche diese Fassung überhaupt zeigt.
 *
 * WARUM ES DIESE DATEI GIBT
 * =========================
 * Dieselbe Oberfläche wird zweimal ausgeliefert (siehe next.config.ts): als
 * statischer Export im Windows-Paket für den Bürorechner und als Website auf
 * Render. Gebraucht wird von der Website aber nur eines — Fotos hochladen.
 * Mängel, Bautagesberichte, Protokolle und Schreiben entstehen im Büro am
 * großen Bildschirm; sie auf dem Handy mit anzubieten heißt nur, dass man sich
 * auf der Baustelle durch acht Einträge scrollt, um an die Kamera zu kommen.
 *
 * Zwei Umfänge:
 *
 *   "voll"    alle Bereiche — Windows-Paket und lokale Entwicklung
 *   "fotos"   Dashboard, Baufotos, Stammdaten · Projekte — die Website
 *
 * WIE DER WERT HINEINKOMMT
 * ========================
 * Beim Bauen über ``APP_UMFANG``; die Dockerfile der Website setzt "fotos",
 * überall sonst gilt der Standard "voll". Next.js backt den Wert als
 * ``NEXT_PUBLIC_UMFANG`` ins Bündel — zur Laufzeit ist er eine Konstante.
 * Bewusst kein Schalter in der Oberfläche: Das sind nicht zwei Zustände
 * desselben Programms, sondern zwei Auslieferungen. Ein Schalter würde nur
 * dazu führen, dass jemand auf der Baustelle versehentlich die Büroansicht
 * einschaltet und sich dann durch eine Navigation kämpft, deren Bereiche
 * ohne Netzlaufwerk und Vorlagen ohnehin nicht zu Ende zu bedienen sind.
 */

export type Umfang = "voll" | "fotos";

export const UMFANG: Umfang =
  process.env.NEXT_PUBLIC_UMFANG === "fotos" ? "fotos" : "voll";

/** Kurzform für den häufigen Fall — liest sich in Bedingungen besser. */
export const NUR_FOTOS = UMFANG === "fotos";
