"use client";

/**
 * Alles, was aus der Seite eine App macht — ohne eigene Inhalte.
 *
 *   • ``ServiceWorkerRegistrierung`` — meldet ``public/sw.js`` an. Erst damit
 *     startet die App offline und lädt Fotos aus dem Gerätespeicher.
 *   • ``VerbindungsHinweis``        — schmaler Balken, wenn das Netz weg ist.
 *     Wichtig auf der Baustelle: Sonst wundert man sich, warum das Speichern
 *     scheitert, obwohl die Liste noch da ist (die kommt aus dem Speicher).
 *   • ``InstallierenHinweis``       — einmaliger Hinweis "als App installieren"
 *     (Android/Chrome/Edge über das Browser-Angebot, iOS mit Anleitung, weil
 *     Safari dafür keine Schnittstelle anbietet).
 *
 * Alle drei sind stumm, sobald es nichts zu sagen gibt, und alle drei
 * funktionieren auch dann, wenn der Browser nichts davon unterstützt.
 */

import { Download, Share, WifiOff, X } from "lucide-react";
import { useEffect, useState } from "react";

const INSTALL_ABGELEHNT = "hpp-app-install-abgelehnt";

/* ───────── Service Worker ───────── */

export function ServiceWorkerRegistrierung() {
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    // Nur im gebauten Stand: Im Entwicklungsmodus würde der Zwischenspeicher
    // beim Programmieren dauernd veraltete Dateien ausliefern.
    if (process.env.NODE_ENV !== "production") return;

    const anmelden = () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // Kein Grund, die App zu stören — sie läuft auch ohne Offline-Speicher.
      });
    };

    if (document.readyState === "complete") anmelden();
    else window.addEventListener("load", anmelden, { once: true });
  }, []);

  return null;
}

/* ───────── Verbindungszustand ───────── */

export function VerbindungsHinweis() {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const aktualisieren = () => setOffline(!navigator.onLine);
    aktualisieren();
    window.addEventListener("online", aktualisieren);
    window.addEventListener("offline", aktualisieren);
    return () => {
      window.removeEventListener("online", aktualisieren);
      window.removeEventListener("offline", aktualisieren);
    };
  }, []);

  if (!offline) return null;

  return (
    <div className="flex items-center gap-2 bg-ui-warn-soft px-5 py-2 text-[12.5px] text-ui-warn">
      <WifiOff size={14} className="shrink-0" />
      <span className="min-w-0">
        Keine Verbindung — angezeigt wird der letzte geladene Stand. Erfassen und
        Ändern ist erst mit Empfang wieder möglich.
      </span>
    </div>
  );
}

/* ───────── Installationshinweis ───────── */

interface InstallEreignis extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: string }>;
}

function laeuftAlsApp(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.matchMedia("(display-mode: window-controls-overlay)").matches ||
    // Safari auf dem iPhone kennt nur diese ältere Kennzeichnung.
    (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

export function InstallierenHinweis() {
  const [ereignis, setEreignis] = useState<InstallEreignis | null>(null);
  const [iosHinweis, setIosHinweis] = useState(false);

  useEffect(() => {
    if (laeuftAlsApp()) return;
    if (window.localStorage.getItem(INSTALL_ABGELEHNT) === "1") return;

    const merken = (event: Event) => {
      event.preventDefault();
      setEreignis(event as InstallEreignis);
    };
    window.addEventListener("beforeinstallprompt", merken);

    // iPhone/iPad: Safari bietet kein Installations-Ereignis an, dort muss der
    // Weg über "Teilen" erklärt werden.
    const istIOS = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
    if (istIOS) setIosHinweis(true);

    return () => window.removeEventListener("beforeinstallprompt", merken);
  }, []);

  function ablehnen() {
    window.localStorage.setItem(INSTALL_ABGELEHNT, "1");
    setEreignis(null);
    setIosHinweis(false);
  }

  if (!ereignis && !iosHinweis) return null;

  return (
    <div className="flex items-center gap-2 border-b border-ui-line bg-ui-accent-soft px-5 py-2 text-[12.5px] text-ui-accent">
      {ereignis ? (
        <>
          <Download size={14} className="shrink-0" />
          <span className="mr-auto min-w-0">
            Als App installieren — Symbol und Vollbild.
          </span>
          <button
            type="button"
            onClick={async () => {
              await ereignis.prompt();
              setEreignis(null);
            }}
            className="shrink-0 cursor-pointer rounded-full bg-ui-accent px-2.5 py-1 font-medium text-ui-accent-text"
          >
            Installieren
          </button>
        </>
      ) : (
        <>
          <Share size={14} className="shrink-0" />
          <span className="mr-auto min-w-0">
            Als App: „Teilen“ → „Zum Home-Bildschirm“.
          </span>
        </>
      )}
      <button
        type="button"
        onClick={ablehnen}
        aria-label="Hinweis ausblenden"
        className="shrink-0 cursor-pointer p-0.5 opacity-70 hover:opacity-100"
      >
        <X size={14} />
      </button>
    </div>
  );
}
