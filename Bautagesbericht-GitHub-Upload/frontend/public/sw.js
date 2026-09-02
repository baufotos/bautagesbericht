/*
 * Service Worker der HPP-Baumanagement-App.
 *
 * Aufgabe: Die App soll sich wie ein Programm verhalten — sofort starten und
 * auf der Baustelle auch dann noch etwas zeigen, wenn das Netz weg ist.
 *
 * Was zwischengespeichert wird, und warum:
 *
 *   1. Programmdateien (/_next/static/…)  → cache-first.
 *      Diese Dateien haben einen Hash im Namen und ändern sich nie. Sie aus
 *      dem Speicher zu laden ist der Grund, warum die App auch bei einem
 *      Balken Empfang in unter einer Sekunde steht.
 *
 *   2. Startseite (Navigation)            → network-first mit Rückfall.
 *      Es gibt nur eine Seite; die letzte erfolgreiche Fassung wird behalten,
 *      damit die App offline überhaupt startet.
 *
 *   3. Fotos und Planvorschauen           → cache-first.
 *      Beides ändert sich nach dem Hochladen nicht mehr. So kostet das
 *      Durchblättern der Mängelliste nur beim ersten Mal Datenvolumen.
 *
 *   4. Übrige GET-Aufrufe an /api         → network-first mit Rückfall.
 *      Im Funkloch zeigt die Übersicht den letzten geladenen Stand, deutlich
 *      als "offline" gekennzeichnet (siehe OfflineHinweis im Frontend).
 *
 *   5. POST/PATCH/PUT/DELETE              → NIE zwischengespeichert.
 *      Änderungen gehen ausschließlich mit echter Verbindung raus. Ein
 *      Offline-Schreibpuffer ist bewusst NICHT eingebaut: Er bräuchte
 *      Konfliktauflösung (zwei Bauleiter ändern denselben Mangel) und würde
 *      mehr Schaden anrichten als nutzen. Stattdessen meldet die Oberfläche
 *      den Fehlschlag klar und der Nutzer versucht es erneut.
 *
 * Aktualisierung: skipWaiting + clients.claim, das heißt eine neue Fassung
 * greift beim nächsten Start der App. Für ein internes Werkzeug ist das die
 * einfachste verlässliche Regel.
 */

// NICHT VON HAND ÄNDERN — scripts/sw-version.mjs stempelt hier vor jedem
// Build den Zeitpunkt hinein (npm-Skript "prebuild").
//
// Der Browser installiert einen neuen Service Worker nur, wenn sich DIESE
// DATEI ändert. Blieb die Kennung stehen, sah der Anwender nach einem Update
// weiter die alte Oberfläche — genau so ist beim Einbau der
// Baubesprechungsprotokolle die neue Navigation nicht angekommen.
const VERSION = "hpp-260902-171129";
const SHELL_CACHE = `${VERSION}-shell`;
const ASSET_CACHE = `${VERSION}-assets`;
const MEDIEN_CACHE = `${VERSION}-medien`;
const DATEN_CACHE = `${VERSION}-daten`;

const OFFLINE_ANTWORT = new Response(
  JSON.stringify({
    detail: {
      grund: "offline",
      nachricht:
        "Keine Verbindung. Die Änderung wurde nicht gespeichert — bitte mit " +
        "Empfang erneut versuchen.",
    },
  }),
  { status: 503, headers: { "Content-Type": "application/json" } }
);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.add("/").catch(() => undefined))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const namen = await caches.keys();
      await Promise.all(
        namen
          .filter((name) => !name.startsWith(VERSION))
          .map((name) => caches.delete(name))
      );
      await self.clients.claim();
    })()
  );
});

/** Immer erst aus dem Speicher; fehlt es dort, aus dem Netz und ablegen. */
async function cacheZuerst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const treffer = await cache.match(request);
  if (treffer) return treffer;
  const antwort = await fetch(request);
  if (antwort && antwort.ok) cache.put(request, antwort.clone());
  return antwort;
}

/** Erst das Netz (frische Daten); scheitert es, der letzte bekannte Stand. */
async function netzZuerst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const antwort = await fetch(request);
    if (antwort && antwort.ok) cache.put(request, antwort.clone());
    return antwort;
  } catch (fehler) {
    const treffer = await cache.match(request);
    if (treffer) return treffer;
    throw fehler;
  }
}

function istMedien(pfad) {
  // Fotos und Planvorschauen sind nach dem Hochladen unveränderlich.
  return (
    /^\/api\/maengel\/fotos\/\d+\/bild$/.test(pfad) ||
    /^\/api\/plaene\/\d+\/vorschau$/.test(pfad)
  );
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Fremde Hosts (z. B. Google Fonts) unangetastet lassen.
  if (url.origin !== self.location.origin) return;

  // Schreibende Aufrufe niemals abfangen oder puffern.
  if (request.method !== "GET") {
    event.respondWith(fetch(request).catch(() => OFFLINE_ANTWORT.clone()));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      netzZuerst(request, SHELL_CACHE).catch(async () => {
        const cache = await caches.open(SHELL_CACHE);
        return (
          (await cache.match("/")) ||
          new Response(
            "<!doctype html><meta charset=utf-8><title>Offline</title>" +
              "<body style=\"font-family:system-ui;padding:2rem;color:#171717;" +
              'background:#F7F7F5">' +
              "<h1>Keine Verbindung</h1><p>Die App war auf diesem Gerät noch " +
              "nicht online. Bitte einmal mit Empfang öffnen.</p>",
            { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } }
          )
        );
      })
    );
    return;
  }

  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    event.respondWith(cacheZuerst(request, ASSET_CACHE));
    return;
  }

  if (istMedien(url.pathname)) {
    event.respondWith(cacheZuerst(request, MEDIEN_CACHE));
    return;
  }

  if (url.pathname.startsWith("/api/")) {
    // Word-Export nie zwischenspeichern: Das Dokument wird bei jedem Abruf
    // neu erzeugt und soll den aktuellen Stand zeigen.
    if (url.pathname.startsWith("/api/maengel/export")) return;
    event.respondWith(
      netzZuerst(request, DATEN_CACHE).catch(() => OFFLINE_ANTWORT.clone())
    );
  }
});
