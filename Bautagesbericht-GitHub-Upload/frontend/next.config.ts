import type { NextConfig } from "next";

// Ziel-Backend. Standard: lokales FastAPI auf demselben Rechner.
// Über BACKEND_URL überschreibbar (z. B. anderer Host/Port).
// Render liefert per fromService nur den Hostnamen ohne Schema — fehlt das
// Präfix, ergänzen wir https:// automatisch, damit der Rewrite gültig ist.
const RAW_BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";
const BACKEND_URL = /^https?:\/\//.test(RAW_BACKEND_URL)
  ? RAW_BACKEND_URL
  : `https://${RAW_BACKEND_URL}`;

const nextConfig: NextConfig = {
  // Alle /api-Aufrufe werden serverseitig an das FastAPI-Backend
  // weitergeleitet. Dadurch muss für Team-Mitglieder nur Port 3000
  // erreichbar sein, es gibt keine CORS-Probleme, und das Backend
  // bleibt auf localhost gebunden.
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
