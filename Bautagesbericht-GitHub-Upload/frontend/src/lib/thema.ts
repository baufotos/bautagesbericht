/**
 * Welche Fassung die Oberfläche trägt — eine Entscheidung, die der Kollege trifft.
 *
 * DREI FASSUNGEN, ZWEI AUSLIEFERUNGEN
 * ===================================
 * Es gibt drei Fassungen, aber nie alle drei gleichzeitig zur Auswahl. Was
 * angeboten wird, hängt daran, welche Auslieferung läuft (siehe lib/umfang.ts):
 *
 *   Baumanagement ("voll")   hpp  ⇄  dunkel     Standard: hpp
 *   Baufotos      ("fotos")  dunkel ⇄ hell      Standard: dunkel
 *
 * "hpp" ist das Hausdesign von hpp.com: weiß, schwarz, Helvetica, keine
 * Rundungen. Es gehört zur Büro-App, die am großen Bildschirm neben Word und
 * Outlook steht und sich dort einfügen soll.
 *
 * Die Baustellen-App bleibt bewusst dunkel: Sie wird auf dem Handy in der
 * Hand gehalten, oft im Rohbau oder in der Dämmerung, und ein weißes Vollbild
 * blendet dort. Ihre Alternative bleibt "hell" für draußen bei Sonne.
 *
 * Die Systemeinstellung wird ABSICHTLICH nicht gelesen: Wer die App in einer
 * Fassung kennt, soll sie nicht plötzlich anders vorfinden, nur weil ein
 * Gerät anders eingestellt ist.
 *
 * Technisch hängt alles an einem Attribut am <html>: ``data-theme``. Die
 * Tokens in globals.css tauschen daran ihre Werte — Farben, Schrift UND
 * Rundungen. Kein ``dark:``-Präfix in den Views, keine zweite Klassenwelt.
 */

"use client";

import { useCallback, useEffect, useState } from "react";

import { NUR_FOTOS } from "@/lib/umfang";

export type Thema = "dunkel" | "hell" | "hpp";

/** Schlüssel im localStorage. Auch vom Startskript in layout.tsx gelesen. */
export const THEMA_SPEICHER = "hpp-thema";

/**
 * Die Fassung, die ohne gemerkte Wahl gilt.
 *
 * Eine Konstante, kein Funktionsaufruf: ``NUR_FOTOS`` steht beim Bauen fest,
 * damit das Startskript im <head> denselben Wert einsetzen kann.
 */
export const THEMA_STANDARD: Thema = NUR_FOTOS ? "dunkel" : "hpp";

/** Die Fassung, auf die der Umschalter wechselt. */
export const THEMA_ALTERNATIVE: Thema = NUR_FOTOS ? "hell" : "dunkel";

/** Farbe der Browser-/Systemleiste je Fassung (meta[name=theme-color]). */
const LEISTENFARBE: Record<Thema, string> = {
  dunkel: "#0D0E10",
  hell: "#F2F3F5",
  hpp: "#FFFFFF",
};

/** Was am <html> stehen muss. "dunkel" ist der Grundzustand ohne Attribut. */
const ATTRIBUT: Record<Thema, string | null> = {
  dunkel: null,
  hell: "hell",
  hpp: "hpp",
};

/** Nur die beiden Fassungen, die diese Auslieferung überhaupt kennt. */
function gueltig(wert: string | null): wert is Thema {
  return wert === THEMA_STANDARD || wert === THEMA_ALTERNATIVE;
}

export function themaLesen(): Thema {
  if (typeof window === "undefined") return THEMA_STANDARD;
  try {
    const gemerkt = window.localStorage.getItem(THEMA_SPEICHER);
    // Eine gemerkte Fassung aus der jeweils anderen Auslieferung wird
    // verworfen — sonst stünde die Baustellen-App plötzlich in Weiß da,
    // nur weil derselbe Browser einmal die Büro-App geöffnet hatte.
    return gueltig(gemerkt) ? gemerkt : THEMA_STANDARD;
  } catch {
    return THEMA_STANDARD;
  }
}

/** Setzt die Fassung am Dokument, merkt sie und zieht die Leistenfarbe mit. */
export function themaAnwenden(thema: Thema, merken = true): void {
  if (typeof document === "undefined") return;

  const wurzel = document.documentElement;
  const attribut = ATTRIBUT[thema];
  if (attribut) wurzel.setAttribute("data-theme", attribut);
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
 * deshalb startet der Zustand immer auf der Standardfassung und wird erst im
 * Effekt auf den gemerkten Wert gezogen. Das Attribut selbst sitzt zu diesem
 * Zeitpunkt längst richtig — dafür sorgt das Startskript in layout.tsx, sonst
 * würde die App bei anderer Wahl kurz falsch aufblitzen.
 */
export function useThema(): { thema: Thema; umschalten: () => void } {
  const [thema, setThema] = useState<Thema>(THEMA_STANDARD);

  useEffect(() => {
    const gemerkt = themaLesen();
    setThema(gemerkt);
    themaAnwenden(gemerkt, false);
  }, []);

  const umschalten = useCallback(() => {
    setThema((alt) => {
      const neu: Thema =
        alt === THEMA_STANDARD ? THEMA_ALTERNATIVE : THEMA_STANDARD;
      themaAnwenden(neu);
      return neu;
    });
  }, []);

  return { thema, umschalten };
}
