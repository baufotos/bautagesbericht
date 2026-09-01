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

const nextConfig: NextConfig = STATISCHER_EXPORT
  ? {
      output: "export",
      // Ordnerweise Ausgabe, damit auch der Aufruf ohne abschließenden
      // Schrägstrich die richtige Datei findet.
      trailingSlash: true,
    }
  : {
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
