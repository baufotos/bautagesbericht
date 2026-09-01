/*
 * Stempelt vor jedem Build eine frische Kennung in public/sw.js.
 *
 * WARUM ES DIESES SKRIPT GIBT
 * ===========================
 * Der Service Worker legt die Programmhülle in den Cache. Ob der Browser eine
 * neue Fassung überhaupt installiert, entscheidet er allein daran, ob sich die
 * Datei sw.js **byteweise** geändert hat — nicht daran, ob die App neu gebaut
 * wurde. Stand die Kennung fest im Code, passierte genau das hier:
 *
 *   Neue Ansicht eingebaut  ->  App neu gebaut und ausgeliefert  ->  sw.js
 *   unverändert  ->  Browser behält den alten Service Worker  ->  Anwender
 *   sieht weiter die alte Navigation und meldet "die neue Funktion fehlt".
 *
 * Beim Einbau der Baubesprechungsprotokolle ist genau das passiert. Sich
 * vorzunehmen, die Zahl von Hand hochzuzählen, hat nicht funktioniert —
 * deshalb erledigt es jetzt der Build.
 *
 * Eingehängt als "prebuild" in package.json, damit es sowohl beim
 * Windows-Paket (erstellen.ps1 ruft npm run build) als auch im Docker-Build
 * der Website (RUN npm run build) automatisch läuft.
 *
 * Die Kennung ist der Zeitpunkt des Builds. Sie muss nur *anders* sein als
 * vorher, nicht schön.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HIER = dirname(fileURLToPath(import.meta.url));
const SW = join(HIER, "..", "public", "sw.js");

// Erkennt die Zeile unabhängig von ihrem bisherigen Wert.
const MUSTER = /^const VERSION = "[^"]*";$/m;

const jetzt = new Date();
const stempel =
  jetzt.getFullYear().toString().slice(2) +
  String(jetzt.getMonth() + 1).padStart(2, "0") +
  String(jetzt.getDate()).padStart(2, "0") +
  "-" +
  String(jetzt.getHours()).padStart(2, "0") +
  String(jetzt.getMinutes()).padStart(2, "0") +
  String(jetzt.getSeconds()).padStart(2, "0");

const inhalt = readFileSync(SW, "utf8");

if (!MUSTER.test(inhalt)) {
  // Lieber laut scheitern als still eine App ausliefern, die bei den Kollegen
  // auf dem alten Stand kleben bleibt.
  console.error(
    `sw-version: In ${SW} wurde keine Zeile 'const VERSION = "…";' gefunden. ` +
      `Der Service Worker würde nicht aktualisiert — Build abgebrochen.`
  );
  process.exit(1);
}

const neu = inhalt.replace(MUSTER, `const VERSION = "hpp-${stempel}";`);
writeFileSync(SW, neu);
console.log(`sw-version: Service Worker auf hpp-${stempel} gestempelt.`);
