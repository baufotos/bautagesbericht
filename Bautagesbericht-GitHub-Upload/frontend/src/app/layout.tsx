import type { Metadata, Viewport } from "next";
import { IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { ServiceWorkerRegistrierung } from "@/components/AppSchale";

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
  // Dunkel ist die Hausfassung; beim Umschalten zieht lib/thema.ts diese
  // Marke mit, damit die Systemleiste am Handy nicht aus dem Rahmen fällt.
  themeColor: "#0D0E10",
};

/**
 * Läuft vor dem ersten Anzeigen und setzt die gemerkte Fassung.
 *
 * Ohne dieses Skript sähe jeder, der "hell" gewählt hat, für einen Wimpernschlag
 * die dunkle Fassung — React schaltet erst nach dem ersten Rendern um. Deshalb
 * synchron im <head>, klein gehalten und ohne Abhängigkeiten.
 */
const THEMA_STARTSKRIPT = `
try {
  if (localStorage.getItem("hpp-thema") === "hell") {
    document.documentElement.setAttribute("data-theme", "hell");
  }
} catch (e) {}
`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="de"
      className={`${ibmPlexSans.variable} ${ibmPlexMono.variable} h-full antialiased`}
      // Das Startskript ändert das data-theme, bevor React übernimmt.
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEMA_STARTSKRIPT }} />
      </head>
      <body className="min-h-full flex flex-col font-sans overscroll-y-none">
        <ServiceWorkerRegistrierung />
        {children}
      </body>
    </html>
  );
}
