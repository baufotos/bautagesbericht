import type { NextConfig } from "next";

// Ziel-Backend. Standard: lokales FastAPI auf demselben Rechner.
// Über BACKEND_URL überschreibbar (z. B. anderer Host/Port).
// Render liefert per fromService nur den Hostnamen ohne Schema — fehlt das
// Präfix, ergänzen wir https:// automatisch, damit der Rewrite gültig ist.
const RAW_BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";
const BACKEND_URL = /^https?:\/\//.test(RAW_BACKEND_URL)
  ? RAW_BACKEND_URL
  : `https://${RAW_BACKEND_URL}`;

/**
 * ZWEI BETRIEBSARTEN — dieselbe Oberfläche, zwei Auslieferungswege.
 *
 * 1. Server (Standard, so läuft es auf Render)
 *    Next.js liefert die Seite aus und leitet /api serverseitig an FastAPI
 *    weiter. Ein öffentlicher Port, kein CORS.
 *
 * 2. Statischer Export (NEXT_EXPORT=1, für das Windows-Paket)
 *    Die Seite wird zu reinen HTML/JS/CSS-Dateien gebaut, die FastAPI selbst
 *    mit ausliefert. Damit braucht das Programm auf dem Bürorechner KEIN
 *    Node.js — ein Grund, warum das Paket überhaupt handlich bleibt.
 *    Ein Rewrite ist hier weder möglich noch nötig: Oberfläche und /api
 *    kommen dann aus demselben Prozess und damit von derselben Adresse.
 *
 * Möglich ist das nur, weil die App eine einzige clientseitige Seite ist —
 * es gibt keine serverseitig gerenderte Route, die beim Export fehlen würde.
 */
const STATISCHER_EXPORT = process.env.NEXT_EXPORT === "1";

/**
 * ZWEI UMFÄNGE — wie viel von der Oberfläche überhaupt erscheint.
 *
 *   "voll"    alle Bereiche (Windows-Paket, lokale Entwicklung) — Standard
 *   "buero"   alle Bereiche AUSSER Baufotos (die Büro-Website)
 *   "fotos"   nur Dashboard, Baufotos und Stammdaten · Projekte (Baustelle)
 *
 * Gesetzt wird der Wert beim Bauen: render.yaml trägt ihn je Dienst ein
 * ("buero" bzw. der Dockerfile-Standard "fotos"), das Windows-Paket setzt
 * nichts und bekommt "voll". Er wandert als NEXT_PUBLIC_UMFANG ins Bündel;
 * ausgewertet wird er an einer einzigen Stelle, in src/lib/umfang.ts.
 *
 * Die Liste unten MUSS zu der in src/lib/umfang.ts passen. Stand hier einmal
 * nur "fotos", wurde aus einem unbekannten Wert stillschweigend "voll" — die
 * Büro-Website zeigte dann trotz APP_UMFANG=buero wieder ihre Baufotos, ohne
 * dass irgendwo ein Fehler erschien.
 *
 * Absichtlich NICHT an NEXT_EXPORT gekoppelt, obwohl heute beides
 * zusammenfällt: Das sind zwei verschiedene Fragen ("wie wird ausgeliefert"
 * und "was ist zu sehen"), und wer die Website einmal wieder vollständig
 * braucht, soll dafür kein Auslieferungsverfahren umstellen müssen.
 */
const UMFAENGE = ["voll", "buero", "fotos"] as const;
const UMFANG = (UMFAENGE as readonly string[]).includes(
  process.env.APP_UMFANG ?? ""
)
  ? (process.env.APP_UMFANG as string)
  : "voll";

/**
 * WIE LANGE NEXT.JS SEINEM BACKEND ZEIT GIBT.
 *
 * Das ist die wichtigste Zahl in dieser Datei, und sie stand hier lange
 * nicht: Ohne Angabe gibt Next.js einer weitergeleiteten /api-Anfrage
 * genau 30 Sekunden (nachgesehen in
 * node_modules/next/dist/server/lib/router-utils/proxy-request.js:
 * "proxyTimeout || 30000"; nachgemessen am 10.09.2026: 29 s gehen durch,
 * 31 s brechen nach 30,04 s ab).
 *
 * Danach antwortet Next.js NICHT mit einer Zeitüberschreitung, sondern mit
 * "HTTP 500 Internal Server Error" als nacktem Text. Genau diese Meldung
 * stand in der App, wenn man beim Wochenpaket auf "Tage erkennen" drückte:
 * Ein handschriftlicher Wochenstapel wird Seite für Seite gelesen und
 * geprüft (services/seitenlesung) und braucht dafür Minuten — nach 30
 * Sekunden war die Leitung weg, während das Backend ruhig weiterarbeitete.
 *
 * Auf dem Bürorechner fiel das nie auf: Das Windows-Paket ist ein
 * statischer Export, den FastAPI selbst ausliefert (NEXT_EXPORT=1, siehe
 * unten). Dort gibt es keinen Zwischenweg und damit keine Grenze — der
 * Fehler trat NUR im Netz auf.
 *
 * Betroffen war nicht nur das Wochenpaket, sondern alles, was länger als
 * eine halbe Minute rechnet: die Analyse einer Baubesprechung
 * (ZEITGRENZE_SEKUNDEN dort 180 s), das Formulieren einer Anzeige, das
 * Auslesen einer Beauftragungsmail und der PDF-Export über LibreOffice.
 *
 * Zehn Minuten sind mit Absicht großzügig und nicht "unbegrenzt": Die
 * Grenzen sollen im Backend liegen, wo sie je Aufgabe begründet sind
 * (siehe die ZEITGRENZE_SEKUNDEN der einzelnen Dienste), nicht hier.
 */
const BACKEND_GEDULD_MS = 600_000;

/** Was in beiden Betriebsarten gleich ist. */
const GEMEINSAM = {
  // Wird zur Bauzeit in den Code eingesetzt, siehe src/lib/umfang.ts.
  env: { NEXT_PUBLIC_UMFANG: UMFANG },
} satisfies NextConfig;

const nextConfig: NextConfig = STATISCHER_EXPORT
  ? {
      ...GEMEINSAM,
      output: "export",
      // Ordnerweise Ausgabe, damit auch der Aufruf ohne abschließenden
      // Schrägstrich die richtige Datei findet.
      trailingSlash: true,
    }
  : {
      ...GEMEINSAM,
      // Gilt nur hier: Der statische Export hat keinen Rewrite (siehe oben).
      experimental: { proxyTimeout: BACKEND_GEDULD_MS },
      async rewrites() {
        return [
          {
            source: "/api/:path*",
            destination: `${BACKEND_URL}/api/:path*`,
          },
        ];
      },
    };

export default nextConfig;
