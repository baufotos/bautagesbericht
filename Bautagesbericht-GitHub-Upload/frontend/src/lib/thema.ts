/**
 * Hell oder dunkel — eine Entscheidung, die der Kollege trifft.
 *
 * Dunkel ist die Hausfassung und deshalb der Standard. Die Systemeinstellung
 * wird ABSICHTLICH nicht gelesen: Wer die App im Büro dunkel kennt, soll sie
 * auf der Baustelle nicht plötzlich hell vorfinden, nur weil das Tablet
 * anders eingestellt ist. Hell ist der ausdrückliche Griff zum Umschalter,
 * wenn draußen die Sonne aufs Display knallt.
 *
 * Technisch hängt alles an einem Attribut am <html>: ``data-theme="hell"``.
 * Die Tokens in globals.css tauschen daran ihre Werte, siehe dort. Kein
 * ``dark:``-Präfix in den Views, keine zweite Klassenwelt.
 */

"use client";

import { useCallback, useEffect, useState } from "react";

export type Thema = "dunkel" | "hell";

/** Schlüssel im localStorage. Auch vom Startskript in layout.tsx gelesen. */
export const THEMA_SPEICHER = "hpp-thema";

/** Farbe der Browser-/Systemleiste je Fassung (meta[name=theme-color]). */
const LEISTENFARBE: Record<Thema, string> = {
  dunkel: "#0D0E10",
  hell: "#F2F3F5",
};

export function themaLesen(): Thema {
  if (typeof window === "undefined") return "dunkel";
  return window.localStorage.getItem(THEMA_SPEICHER) === "hell" ? "hell" : "dunkel";
}

/** Setzt die Fassung am Dokument, merkt sie und zieht die Leistenfarbe mit. */
export function themaAnwenden(thema: Thema, merken = true): void {
  if (typeof document === "undefined") return;

  const wurzel = document.documentElement;
  if (thema === "hell") wurzel.setAttribute("data-theme", "hell");
  else wurzel.removeAttribute("data-theme");

  const marke = document.querySelector('meta[name="theme-color"]');
  if (marke) marke.setAttribute("content", LEISTENFARBE[thema]);

  if (merken) {
    try {
      window.localStorage.setItem(THEMA_SPEICHER, thema);
    } catch {
      /* Privater Modus ohne Speicher: dann gilt die Wahl nur für diese Sitzung */
    }
  }
}

/**
 * Zustand für den Umschalter in der Kopfzeile.
 *
 * Der erste Renderdurchlauf muss serverseitig und im Browser gleich aussehen,
 * deshalb startet der Zustand immer auf "dunkel" und wird erst im Effekt auf
 * den gemerkten Wert gezogen. Das Attribut selbst sitzt zu diesem Zeitpunkt
 * längst richtig — dafür sorgt das Startskript in layout.tsx, sonst würde die
 * App bei hell gewählter Fassung kurz dunkel aufblitzen.
 */
export function useThema(): { thema: Thema; umschalten: () => void } {
  const [thema, setThema] = useState<Thema>("dunkel");

  useEffect(() => {
    const gemerkt = themaLesen();
    setThema(gemerkt);
    themaAnwenden(gemerkt, false);
  }, []);

  const umschalten = useCallback(() => {
    setThema((alt) => {
      const neu: Thema = alt === "dunkel" ? "hell" : "dunkel";
      themaAnwenden(neu);
      return neu;
    });
  }, []);

  return { thema, umschalten };
}
