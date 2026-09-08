import type { Metadata, Viewport } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { ServiceWorkerRegistrierung } from "@/components/AppSchale";
import { Anmeldeschutz } from "@/components/Anmeldeschutz";
// Absichtlich aus umfang.ts und nicht aus lib/thema.ts: Diese Datei ist eine
// Server-Komponente, thema.ts trägt "use client". Die drei Werte hier
// abzuleiten kostet drei Zeilen und erspart eine Client-Grenze.
import { NUR_FOTOS } from "@/lib/umfang";

/** Fassung ohne gemerkte Wahl — muss zu THEMA_STANDARD in lib/thema.ts passen. */
const STANDARD_THEMA = NUR_FOTOS ? "dunkel" : "hpp";
/** Die zweite wählbare Fassung — muss zu THEMA_ALTERNATIVE passen. */
const ZWEITE_FASSUNG = NUR_FOTOS ? "hell" : "dunkel";
/** Leistenfarbe der Standardfassung. */
const STANDARD_LEISTE = NUR_FOTOS ? "#0D0E10" : "#FFFFFF";

const ibmPlexSans = IBM_Plex_Sans({
  variable: "--font-ibm-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-ibm-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "HPP Baumanagement",
  description: "Bautagesberichte und Mängelmanagement",
  robots: { index: false, follow: false },
  // Macht aus der Seite eine installierbare App: Symbol auf dem
  // Home-Bildschirm, Start im Vollbild ohne Browserleiste.
  manifest: "/manifest.webmanifest",
  applicationName: "HPP Baumanagement",
  appleWebApp: {
    capable: true,
    title: "HPP Bau",
    // "default" behält die Statusleiste in Lesefarbe — bei "black-translucent"
    // würde der Inhalt unter die Uhr rutschen.
    statusBarStyle: "default",
  },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Zoom bleibt erlaubt — auf der Baustelle wird in Fotos und Pläne
  // hineingezoomt, und Barrierefreiheit gilt auch für ein Werkzeug.
  maximumScale: 5,
  userScalable: true,
  // Randloses Layout auf Geräten mit Aussparung; die Navigation unten
  // berücksichtigt den Sicherheitsabstand selbst.
  viewportFit: "cover",
  // Je Auslieferung verschieden: Die Büro-App startet im weißen HPP-Design,
  // die Baustellen-App dunkel. Beim Umschalten zieht lib/thema.ts diese
  // Marke mit, damit die Systemleiste am Handy nicht aus dem Rahmen fällt.
  themeColor: STANDARD_LEISTE,
};

/**
 * Läuft vor dem ersten Anzeigen und setzt die geltende Fassung.
 *
 * Ohne dieses Skript sähe jeder für einen Wimpernschlag die falsche Fassung —
 * React schaltet erst nach dem ersten Rendern um, und der Sprung von Weiß auf
 * Schwarz (oder umgekehrt) ist genau der Fehler, den niemand übersieht.
 * Deshalb synchron im <head>, klein gehalten und ohne Abhängigkeiten.
 *
 * Die Werte werden beim Bauen eingesetzt; welche Auslieferung läuft, steht
 * dann längst fest. Eine gemerkte Fassung aus der jeweils anderen
 * Auslieferung wird verworfen — sonst öffnete die Baustellen-App weiß, nur
 * weil derselbe Browser einmal die Büro-App gesehen hat.
 */
const THEMA_STARTSKRIPT = `
try {
  var standard = ${JSON.stringify(STANDARD_THEMA)};
  var zweite = ${JSON.stringify(ZWEITE_FASSUNG)};
  var gemerkt = localStorage.getItem("hpp-thema");
  var gilt = (gemerkt === standard || gemerkt === zweite) ? gemerkt : standard;
  if (gilt === "dunkel") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", gilt);
} catch (e) {
  var s = ${JSON.stringify(STANDARD_THEMA)};
  if (s !== "dunkel") document.documentElement.setAttribute("data-theme", s);
}
`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="de"
      className={`${ibmPlexSans.variable} ${ibmPlexMono.variable} h-full antialiased`}
      // Die Standardfassung steht schon im ausgelieferten HTML, damit die
      // Seite nie in der falschen aufblitzt. Das Startskript korrigiert
      // gleich darauf nur noch, wenn jemand die andere gewählt hat.
      data-theme={STANDARD_THEMA === "dunkel" ? undefined : STANDARD_THEMA}
      // Das Startskript ändert das data-theme, bevor React übernimmt.
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEMA_STARTSKRIPT }} />
      </head>
      <body className="min-h-full flex flex-col font-sans overscroll-y-none">
        <ServiceWorkerRegistrierung />
        <Anmeldeschutz>{children}</Anmeldeschutz>
      </body>
    </html>
  );
}
