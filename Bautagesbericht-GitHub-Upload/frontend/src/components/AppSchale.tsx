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

    /* ── Warum hier neu geladen wird ───────────────────────────────────────
     *
     * Ohne diesen Block kommt ein Update nicht beim Anwender an, und zwar aus
     * einem Grund, den man der App nicht ansieht:
     *
     *   Der neue Service Worker installiert sich, ruft skipWaiting() und
     *   clients.claim() und steuert damit ab sofort die Seite. Das JavaScript
     *   der Oberfläche ist zu diesem Zeitpunkt aber längst geladen — und zwar
     *   das ALTE. Die Seite läuft also mit dem alten Bundle weiter, bis
     *   jemand von sich aus neu lädt.
     *
     * Genau so ist die neue Navigation "Baubesprechungen" nach dem Ausrollen
     * nicht aufgetaucht: ausgeliefert war sie, angezeigt wurde die alte
     * Fassung. Deshalb lädt die App jetzt selbst neu, sobald ein neuer
     * Service Worker das Ruder übernimmt.
     *
     * Zwei Vorsichtsmaßnahmen:
     *   - Nur, wenn vorher schon einer die Seite gesteuert hat. Beim allerersten
     *     Besuch übernimmt clients.claim() ebenfalls, aber da ist die Seite
     *     bereits die neueste — ein Neuladen wäre nur Flackern.
     *   - Nur einmal. Ohne den Riegel könnte aus einem Fehlerfall eine
     *     Schleife werden, und eine Baustellen-App, die sich im Kreis dreht,
     *     ist schlimmer als eine veraltete.
     */
    let neuLaden = false;
    const hatteSchonEinen = navigator.serviceWorker.controller !== null;

    const beiWechsel = () => {
      if (!hatteSchonEinen || neuLaden) return;
      neuLaden = true;
      window.location.reload();
    };
    navigator.serviceWorker.addEventListener("controllerchange", beiWechsel);

    const anmelden = () => {
      navigator.serviceWorker
        .register("/sw.js")
        .then((registrierung) => {
          // Sucht beim Start aktiv nach einer neuen Fassung. Ohne das prüft
          // der Browser je nach Laune erst Stunden später.
          registrierung.update().catch(() => undefined);
        })
        .catch(() => {
          // Kein Grund, die App zu stören — sie läuft auch ohne Offline-Speicher.
        });
    };

    if (document.readyState === "complete") anmelden();
    else window.addEventListener("load", anmelden, { once: true });

    return () => {
      navigator.serviceWorker.removeEventListener("controllerchange", beiWechsel);
    };
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
