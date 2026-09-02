"use client";

/**
 * Standort eines Projekts festlegen — suchen, auswählen, notfalls eintippen.
 *
 * Warum es das gibt: Vorher wurde die Adresse beim Speichern still
 * nachgeschlagen. Ging das schief, stand auf der Karte „ohne Standort", und
 * es gab keinen Weg, etwas dagegen zu tun — kein Knopf, keine Begründung,
 * keine zweite Chance. Wer eine richtige Adresse eingetippt hatte, tippte sie
 * ratlos noch einmal.
 *
 * Deshalb hier drei Dinge, die vorher fehlten:
 *
 *  1. **Suchen auf Knopfdruck**, mit allen Kandidaten im Klartext. Die
 *     Baustelle kennt der Mensch, nicht der Kartendienst — also wählt der
 *     Mensch.
 *  2. **Der Unterschied zwischen „nicht gefunden“ und „Dienst nicht
 *     erreichbar“.** Das eine heißt „Adresse prüfen“, das andere „später
 *     nochmal, liegt nicht an dir“. Beides sah bisher gleich aus.
 *  3. **Koordinaten von Hand.** Für Baustellen auf der grünen Wiese, die in
 *     keiner Karte stehen. Rechtsklick in OpenStreetMap oder Google Maps
 *     liefert die zwei Zahlen.
 */

import {
  Check,
  Crosshair,
  ExternalLink,
  Loader2,
  MapPin,
  Search,
  X,
} from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import type { StandortSucheAntwort, StandortTreffer } from "@/lib/types";
import { Plakette, type PlakettenArt } from "@/components/dashboard";
import { Button, Field, Input, Meldung } from "@/components/ui";

/** Wie ein Standort in einem Wort zu beschreiben ist. */
export function standortGuete(guete: string): {
  art: PlakettenArt;
  text: string;
  erklaerung: string;
} {
  switch (guete) {
    case "adresse":
      return {
        art: "ok",
        text: "hausnummergenau",
        erklaerung: "Die Adresse wurde bis zur Hausnummer gefunden.",
      };
    case "manuell":
      return {
        art: "ok",
        text: "von Hand",
        erklaerung: "Die Koordinaten wurden hier eingetragen oder ausgewählt.",
      };
    case "strasse":
      return {
        art: "info",
        text: "straßengenau",
        erklaerung:
          "Die Straße wurde gefunden, die Hausnummer nicht. Für die Wetterdaten genügt das.",
      };
    case "ort":
      return {
        art: "info",
        text: "ortsgenau",
        erklaerung:
          "Nur der Ort wurde gefunden. Für die Wetterdaten genügt das — die " +
          "DWD-Station liegt ohnehin einige Kilometer entfernt.",
      };
    default:
      return {
        art: "neutral",
        text: "Standort gesetzt",
        erklaerung: "Angelegt, bevor die Genauigkeit mitgeschrieben wurde.",
      };
  }
}

const GUETE_KURZ: Record<string, string> = {
  adresse: "Hausnummer",
  strasse: "Straße",
  ort: "Ort",
};

/** Link auf die Karte, damit man den Punkt mit eigenen Augen prüfen kann. */
export function kartenLink(lat: number, lon: number) {
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=17/${lat}/${lon}`;
}

export function StandortFeld({
  adresse,
  lat,
  lon,
  guete,
  label,
  onWaehlen,
  einklappbar = true,
}: {
  adresse: string;
  lat: number | null;
  lon: number | null;
  guete?: string;
  label?: string;
  /** Übernimmt die Wahl. ``null, null`` heißt „Standort entfernen“. */
  onWaehlen: (lat: number | null, lon: number | null) => void | Promise<void>;
  /** Im Anlegen-Formular ist das Feld immer offen, auf der Karte aufklappbar. */
  einklappbar?: boolean;
}) {
  const [offen, setOffen] = useState(!einklappbar);
  const [laeuft, setLaeuft] = useState(false);
  const [ergebnis, setErgebnis] = useState<StandortSucheAntwort | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [handLat, setHandLat] = useState("");
  const [handLon, setHandLon] = useState("");
  const [details, setDetails] = useState(false);

  async function suchen() {
    if (!adresse.trim()) {
      setFehler("Erst eine Adresse eintragen, dann lässt sich danach suchen.");
      return;
    }
    setLaeuft(true);
    setFehler(null);
    setErgebnis(null);
    try {
      const gefunden = await api.projekte.standortSuche(adresse.trim());
      setErgebnis(gefunden);
      // Die Handeingabe nur aufklappen, wenn sie gebraucht wird. Wurde etwas
      // gefunden, ist die Trefferliste der naechste Schritt, nicht ein
      // Zahlenfeld.
      if (gefunden.treffer.length === 0) setOffen(true);
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Suche fehlgeschlagen.");
    } finally {
      setLaeuft(false);
    }
  }

  async function waehlen(treffer: StandortTreffer) {
    await onWaehlen(treffer.lat, treffer.lon);
    setErgebnis(null);
    if (einklappbar) setOffen(false);
  }

  async function handEintragen() {
    // Komma als Dezimaltrennzeichen zulassen — auf einer deutschen Tastatur
    // ist das die naheliegende Eingabe, und „53,55“ als Fehler abzuweisen
    // wäre kleinlich.
    const a = Number(handLat.replace(",", ".").trim());
    const b = Number(handLon.replace(",", ".").trim());
    if (!Number.isFinite(a) || !Number.isFinite(b)) {
      setFehler("Zwei Zahlen erwartet, z. B. 53.5731 und 9.8817.");
      return;
    }
    if (a < -90 || a > 90 || b < -180 || b > 180) {
      setFehler("Breite liegt zwischen -90 und 90, Länge zwischen -180 und 180.");
      return;
    }
    setFehler(null);
    await onWaehlen(a, b);
    setHandLat("");
    setHandLon("");
    setErgebnis(null);
  }

  const beschreibung = lat !== null && lon !== null ? standortGuete(guete || "") : null;

  return (
    <div className="flex flex-col gap-2">
      {/* ── Was gerade hinterlegt ist ── */}
      <div className="flex flex-wrap items-center gap-2">
        {lat !== null && lon !== null ? (
          <>
            <Plakette art={beschreibung!.art}>{beschreibung!.text}</Plakette>
            <span className="font-mono text-[11px] text-app-text-leise">
              {lat.toFixed(4)}, {lon.toFixed(4)}
            </span>
            <a
              href={kartenLink(lat, lon)}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11.5px] text-app-info hover:underline"
              title="Punkt in OpenStreetMap ansehen"
            >
              auf der Karte <ExternalLink size={11} />
            </a>
          </>
        ) : (
          <Plakette art="warn">ohne Standort</Plakette>
        )}
        <Button
          variante="still"
          icon={laeuft ? Loader2 : Search}
          onClick={suchen}
          disabled={laeuft}
          className="!px-3 !py-1.5 !text-[12px]"
        >
          {laeuft ? "sucht…" : lat === null ? "Standort suchen" : "neu suchen"}
        </Button>
        {einklappbar && (
          <button
            type="button"
            onClick={() => setOffen(!offen)}
            className="cursor-pointer text-[11.5px] text-app-text-leise hover:text-app-text"
          >
            {offen ? "zuklappen" : "von Hand setzen"}
          </button>
        )}
      </div>

      {label && lat !== null && (
        <p className="text-[11.5px] text-app-text-leise">
          Gefunden als: <span className="text-app-text-still">{label}</span>
        </p>
      )}
      {beschreibung && beschreibung.art === "info" && (
        <p className="text-[11.5px] text-app-text-leise">{beschreibung.erklaerung}</p>
      )}

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {/* ── Ergebnis der Suche ── */}
      {ergebnis && ergebnis.treffer.length > 0 && (
        <div className="flex flex-col gap-1.5 rounded-md border border-app-linie bg-app-flaeche-still p-2">
          <p className="text-[11.5px] text-app-text-still">
            {ergebnis.treffer.length === 1
              ? "Ein Treffer — stimmt der?"
              : `${ergebnis.treffer.length} Treffer — welcher ist die Baustelle?`}
          </p>
          {ergebnis.treffer.map((t, i) => (
            <button
              key={`${t.lat}-${t.lon}-${i}`}
              type="button"
              onClick={() => waehlen(t)}
              className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-app-flaeche"
            >
              <MapPin size={13} className="mt-0.5 shrink-0 text-app-text-leise" />
              <span className="min-w-0 flex-1">
                <span className="block text-[12.5px] text-app-text">{t.label}</span>
                <span className="block text-[11px] text-app-text-leise">
                  {GUETE_KURZ[t.guete] || t.guete} · {t.lat.toFixed(4)},{" "}
                  {t.lon.toFixed(4)}
                  {t.hinweis && (
                    <span className="text-app-warn"> · {t.hinweis}</span>
                  )}
                </span>
              </span>
              <Check size={14} className="mt-0.5 shrink-0 text-app-text-leise" />
            </button>
          ))}
        </div>
      )}

      {/* ── Nichts gefunden: die beiden Fälle sagen Verschiedenes ── */}
      {ergebnis && ergebnis.treffer.length === 0 && (
        <Meldung art={ergebnis.dienst_erreichbar ? "hinweis" : "fehler"}>
          {ergebnis.dienst_erreichbar ? (
            <>
              Zu dieser Adresse wurde nichts gefunden. Meist fehlt die
              Postleitzahl oder der Ort — „Notkestraße 85, 22607 Hamburg“ findet
              sich, „Notkestraße 85“ allein nicht. Sonst unten die Koordinaten
              eintragen.
            </>
          ) : (
            <>
              Der Kartendienst war nicht erreichbar — das liegt nicht an der
              Adresse. Im Bürorechner kann eine Firewall dazwischenstehen.
              Später erneut suchen oder unten die Koordinaten eintragen.
            </>
          )}
        </Meldung>
      )}

      {/* Wie die Eingabe gelesen wurde. Zeigt auf einen Blick, wenn der Ort im
          Feld „Straße“ gelandet ist — der häufigste Grund für einen Fehlschlag. */}
      {ergebnis && Object.keys(ergebnis.erkannt).length > 0 && (
        <div className="text-[11px] text-app-text-leise">
          <button
            type="button"
            onClick={() => setDetails(!details)}
            className="cursor-pointer hover:text-app-text"
          >
            So wurde die Eingabe gelesen {details ? "▴" : "▾"}
          </button>
          {details && (
            <div className="mt-1 flex flex-col gap-0.5 font-mono">
              {Object.entries(ergebnis.erkannt).map(([k, v]) => (
                <span key={k}>
                  {k}: {v}
                </span>
              ))}
              {ergebnis.versuche.map((v, i) => (
                <span key={i} className="opacity-70">
                  {v}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Koordinaten von Hand ── */}
      {offen && (
        <div className="flex flex-col gap-2 rounded-md border border-app-linie bg-app-flaeche-still p-2">
          <p className="text-[11.5px] text-app-text-still">
            Koordinaten von Hand — für Baustellen ohne Adresse. In
            OpenStreetMap oder Google Maps mit der rechten Maustaste auf die
            Stelle klicken, die beiden Zahlen erscheinen dort.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Breite (lat)" className="w-32">
              <Input
                value={handLat}
                onChange={(e) => setHandLat(e.target.value)}
                placeholder="53.5731"
                inputMode="decimal"
                onKeyDown={(e) => e.key === "Enter" && handEintragen()}
              />
            </Field>
            <Field label="Länge (lon)" className="w-32">
              <Input
                value={handLon}
                onChange={(e) => setHandLon(e.target.value)}
                placeholder="9.8817"
                inputMode="decimal"
                onKeyDown={(e) => e.key === "Enter" && handEintragen()}
              />
            </Field>
            <Button
              variante="sekundaer"
              icon={Crosshair}
              onClick={handEintragen}
              disabled={!handLat.trim() || !handLon.trim()}
              className="!py-2"
            >
              Übernehmen
            </Button>
            {lat !== null && (
              <Button
                variante="still"
                icon={X}
                onClick={() => onWaehlen(null, null)}
                className="!py-2"
                title="Standort entfernen — der Bautagesbericht holt dann kein Wetter"
              >
                Entfernen
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
