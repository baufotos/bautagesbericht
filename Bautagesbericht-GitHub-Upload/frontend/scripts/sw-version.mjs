/*
 * Stempelt vor jedem Build zwei Dinge in public/:
 *   1. eine frische Kennung in sw.js,
 *   2. Beschreibung und Verknüpfungen im Manifest, passend zum Umfang.
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
 *
 * UND WARUM AUCH DAS MANIFEST
 * ===========================
 * Das Manifest ist eine statische Datei und wird deshalb in beide Fassungen
 * gleich ausgeliefert (siehe src/lib/umfang.ts). Seine Verknüpfungen landen
 * aber im Startmenü und im Kontextmenü des Symbols auf dem Handy — und ein
 * "Mangel erfassen" auf der Website führt zu einer Ansicht, die es dort nicht
 * gibt. Weil derselbe prebuild-Lauf ohnehin die Umgebung kennt, wird das
 * Manifest hier gleich mitgestempelt. Der Eingriff ist eng: nur description
 * und shortcuts, alles andere bleibt, wie es in der Datei steht.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HIER = dirname(fileURLToPath(import.meta.url));
const SW = join(HIER, "..", "public", "sw.js");
const MANIFEST = join(HIER, "..", "public", "manifest.webmanifest");

/** Muss zu next.config.ts passen: alles außer "fotos" ist der volle Umfang. */
const UMFANG = process.env.APP_UMFANG === "fotos" ? "fotos" : "voll";

/* ───────────────────────────── 1. Service Worker ───────────────────────────── */

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

/* ───────────────────────────── 2. Manifest ───────────────────────────── */

const SYMBOL = [{ src: "/icons/icon-192.png", sizes: "192x192" }];

const BESCHREIBUNG = {
  voll: "Bautagesberichte und Mängelmanagement für HPP Architekten Baumanagement",
  fotos: "Baufotos der Baustelle hochladen — HPP Architekten Baumanagement",
};

const VERKNUEPFUNGEN = {
  voll: [
    {
      name: "Mangel erfassen",
      short_name: "Mangel",
      description: "Direkt zum Erfassungsformular für einen neuen Mangel",
      url: "/?tab=maengel&neu=1",
      icons: SYMBOL,
    },
    {
      name: "Mängel-Übersicht",
      short_name: "Mängel",
      description: "Offene und überfällige Mängel des Projekts",
      url: "/?tab=maengel",
      icons: SYMBOL,
    },
    {
      name: "Bericht einreichen",
      short_name: "Bericht",
      description: "Bautagesbericht einreichen",
      url: "/?tab=einreichen",
      icons: SYMBOL,
    },
  ],
  fotos: [
    {
      name: "Fotos hochladen",
      short_name: "Fotos",
      description: "Direkt zum Hochladen der Baufotos",
      url: "/?ansicht=baufotos-neu",
      icons: SYMBOL,
    },
    {
      name: "Fotosätze",
      short_name: "Sätze",
      description: "Die hochgeladenen Fotosätze des Projekts",
      url: "/?ansicht=baufotos-galerie",
      icons: SYMBOL,
    },
  ],
};

const manifestRoh = readFileSync(MANIFEST, "utf8");
// Zeilenenden der vorhandenen Datei behalten: Der Quellordner ist durchgängig
// CRLF, und eine mit LF zurückgeschriebene Datei erzeugt beim Spiegeln ins
// Git-Verzeichnis einen Commit, der nichts als Zeilenenden ändert.
const zeilenende = manifestRoh.includes("\r\n") ? "\r\n" : "\n";

let manifest;
try {
  manifest = JSON.parse(manifestRoh);
} catch (fehler) {
  console.error(`sw-version: ${MANIFEST} ist kein gültiges JSON — Build abgebrochen.`);
  console.error(fehler.message);
  process.exit(1);
}

manifest.description = BESCHREIBUNG[UMFANG];
manifest.shortcuts = VERKNUEPFUNGEN[UMFANG];

writeFileSync(
  MANIFEST,
  JSON.stringify(manifest, null, 2).replace(/\n/g, zeilenende) + zeilenende
);
console.log(
  `sw-version: Manifest auf Umfang "${UMFANG}" gestempelt ` +
    `(${manifest.shortcuts.length} Verknüpfungen).`
);
