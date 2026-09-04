"use client";

/**
 * Dashboard der Website — der Stand der Baufotos eines Bauvorhabens.
 *
 * WARUM ES DIESES ZWEITE DASHBOARD GIBT
 * =====================================
 * Die Website kann nur eines (siehe lib/umfang.ts): Fotos von der Baustelle
 * hereinholen. Das große Dashboard nebenan rechnet Mängelquoten, Fristen und
 * Bautagesberichte — auf der Baustelle stünden davon lauter Nullen auf dem
 * Bildschirm, und eine Kachel mit einer Null ist schlimmer als keine Kachel.
 * Hier steht deshalb nur, was mit Fotos zu tun hat.
 *
 * GESTALTUNG: unverändert
 * =======================
 * Dieselben Bausteine aus components/dashboard, dieselbe Ordnung der Fragen
 * wie im großen Dashboard:
 *   1. Was will ich jetzt tun?    (das Hochladen-Feld, groß und links oben)
 *   2. Wie viel ist da?           (Fotos, Fotosätze, Abholstand)
 *   3. Was ist zuletzt passiert?  (Verlauf, Kategorien, letzte Sätze)
 *
 * GRUNDREGEL, WIE NEBENAN: Jede Zahl wird aus der übergebenen Liste gerechnet.
 * Kein eigener Statistik-Endpunkt, keine Platzhalterwerte. Wo nichts da ist,
 * steht ein Hinweis.
 */

import {
  ArrowRight,
  Camera,
  FolderCheck,
  Images,
  MapPin,
  Tags,
  TrendingUp,
} from "lucide-react";

import { api } from "@/lib/api";
import {
  alsZeitstempel,
  formatBytes,
  formatDatumIso,
  relativeZeit,
} from "@/lib/formate";
import type { FotosatzListItem, Projekt } from "@/lib/types";
import type { Ansicht } from "@/components/AppShell";
import {
  Initialen,
  Karte,
  KarteInhalt,
  KarteKopf,
  Kennzahl,
  Kurve,
  LeerHinweis,
  ListenZeile,
  Plakette,
  Quote,
  SeitenKopf,
  type TrendWert,
} from "@/components/dashboard";
import { Button } from "@/components/ui";

/** Zeitraum der Kennzahlen „der letzten Tage“. */
const FENSTER_TAGE = 30;
/** Wie viele Kategorien die Verteilung höchstens einzeln nennt. */
const MAX_KATEGORIEN = 5;
/** Wie viele Fotosätze die Liste der letzten Uploads zeigt. */
const MAX_LETZTE = 6;

function tageZurueck(tage: number): number {
  return Date.now() - tage * 24 * 60 * 60 * 1000;
}

/** Kurzname für die zentrale Zeitauslegung (naives UTC, siehe lib/formate). */
const alsZeit = alsZeitstempel;

/* ───────────────────────────── Das Hochladen-Feld ───────────────────────────── */

/**
 * Die große Fläche, mit der diese Seite anfängt.
 *
 * Ein Feld und kein bloßer Knopf: Auf der Baustelle wird die Seite mit dem
 * Daumen bedient, oft mit Handschuhen und in der Sonne. Die gestrichelte Kante
 * ist dieselbe Sprache wie beim Leerhinweis („hier gehört etwas hinein“) und
 * sagt ohne ein Wort, dass hier Bilder hineingehören. Ein echter Knopf und
 * keine anklickbare Fläche, damit Tastatur und Vorlesehilfe ihn finden.
 */
function HochladenFeld({
  projektName,
  onHochladen,
}: {
  projektName: string;
  onHochladen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onHochladen}
      className="group flex w-full cursor-pointer flex-col items-center gap-3 rounded-app border border-dashed border-app-linie-stark bg-app-flaeche-still px-5 py-7 text-center transition-colors hover:border-app-akzent hover:bg-app-flaeche-hoch"
    >
      <span className="flex size-14 items-center justify-center rounded-full bg-app-akzent-sanft text-app-text">
        <Camera size={24} strokeWidth={1.9} />
      </span>
      <span className="block">
        <span className="block text-[15px] font-semibold text-app-text">
          Fotos hochladen
        </span>
        <span className="mx-auto mt-1 block max-w-[46ch] text-[12.5px] text-app-text-still">
          für {projektName} — Kategorie und Bautag wählen, Bilder aufnehmen oder
          aus der Galerie auswählen. Umbenennen und Archiv macht die App.
        </span>
      </span>
      <span className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-app-text">
        Weiter zum Hochladen
        <ArrowRight
          size={14}
          className="transition-transform group-hover:translate-x-0.5"
        />
      </span>
    </button>
  );
}

/* ───────────────────────────── Dashboard ───────────────────────────── */

export function FotoDashboard({
  projekt,
  fotosaetze,
  laedt,
  onAnsicht,
}: {
  projekt: Projekt | null;
  fotosaetze: FotosatzListItem[];
  laedt: boolean;
  onAnsicht: (ansicht: Ansicht) => void;
}) {
  if (projekt === null) {
    return (
      <Karte>
        <KarteKopf titel="Kein Projekt gewählt" icon={MapPin} />
        <KarteInhalt className="flex flex-col items-start gap-3">
          <p className="text-[13px] text-app-text-still">
            Baufotos gehören immer zu einem Bauvorhaben — daraus entstehen der
            Dateiname, das Archiv und der Zielordner im Büro. Sobald ein Projekt
            angelegt ist, kann hier hochgeladen werden.
          </p>
          <Button onClick={() => onAnsicht("stamm-projekte")} icon={MapPin}>
            Projekt anlegen
          </Button>
        </KarteInhalt>
      </Karte>
    );
  }

  /* ───────── Kennzahlen aus der Liste ───────── */

  const gesamtFotos = fotosaetze.reduce((summe, f) => summe + f.anzahl_fotos, 0);
  const gesamtBytes = fotosaetze.reduce((summe, f) => summe + f.groesse_bytes, 0);
  const offeneAbholung = fotosaetze.filter((f) => !f.abgeholt_am);
  const abgeholt = fotosaetze.length - offeneAbholung.length;
  const letzter = fotosaetze[0];

  /* Gezählt wird nach ``datum``, dem Bautag — nicht nach dem Zeitpunkt des
     Hochladens. Wer abends fünf Tage nachreicht, hat fünf Bautage
     dokumentiert und nicht einen Ausschlag am Tag des Hochladens. */
  const bautage = fotosaetze.map((f) => alsZeit(f.datum));
  const grenze = tageZurueck(FENSTER_TAGE);
  const vorgrenze = tageZurueck(FENSTER_TAGE * 2);

  function imFenster(von: number, bis: number): number {
    return bautage.filter((z) => z >= von && z < bis).length;
  }

  const saetzeNeu = imFenster(grenze, Date.now() + 1);
  const saetzeVorher = imFenster(vorgrenze, grenze);
  const fotosNeu = fotosaetze
    .filter((f) => alsZeit(f.datum) >= grenze)
    .reduce((summe, f) => summe + f.anzahl_fotos, 0);

  /**
   * Trend aus zwei gleich langen Zeiträumen.
   *
   * Mehr hochgeladene Fotosätze sind hier immer die gute Richtung — anders als
   * bei den Mängeln nebenan gibt es keinen Wert, bei dem Zunahme schlecht
   * wäre. Sind beide Zeiträume leer, gibt es KEINEN Trend: „±0“ neben zwei
   * Nullen ist keine Aussage, sondern Zierde.
   */
  function trendAus(jetzt: number, vorher: number): TrendWert | undefined {
    if (jetzt === 0 && vorher === 0) return undefined;
    const differenz = jetzt - vorher;
    return {
      text: `${differenz > 0 ? "+" : differenz < 0 ? "−" : "±"}${Math.abs(differenz)}`,
      auf: differenz >= 0,
      gut: differenz >= 0,
      bezug: `zu den ${FENSTER_TAGE} Tagen davor`,
    };
  }

  // Fotosätze je Woche, acht Wochen — der Verlauf in der zweiten Reihe.
  const wochen = Array.from({ length: 8 }, (_, i) =>
    imFenster(tageZurueck((8 - i) * 7), tageZurueck((7 - i) * 7))
  );

  /* ───────── Kategorien ───────── */

  const kategorieZaehler = new Map<string, number>();
  for (const satz of fotosaetze) {
    kategorieZaehler.set(
      satz.kategorie,
      (kategorieZaehler.get(satz.kategorie) ?? 0) + satz.anzahl_fotos
    );
  }
  const kategorien = [...kategorieZaehler.entries()].sort((a, b) => b[1] - a[1]);
  const topKategorien = kategorien.slice(0, MAX_KATEGORIEN);

  const neuesteFotosaetze = fotosaetze.slice(0, 4);
  const letzteSaetze = fotosaetze.slice(0, MAX_LETZTE);

  /* ───────── Plakette im Seitenkopf ───────── */

  const plakette =
    fotosaetze.length === 0 ? (
      <Plakette art="neutral" gross>
        {laedt ? "Wird geladen" : "Noch keine Fotos"}
      </Plakette>
    ) : offeneAbholung.length > 0 ? (
      <Plakette art="info" gross>
        {offeneAbholung.length} zur Abholung
      </Plakette>
    ) : (
      <Plakette art="ok" gross>
        Alles abgeholt
      </Plakette>
    );

  return (
    <div className="flex flex-col gap-4">
      <SeitenKopf
        titel={`Dashboard: ${projekt.name}`}
        kennung={
          <>
            Projekt-ID: {String(projekt.id).padStart(3, "0")}
            {projekt.adresse ? ` · ${projekt.adresse}` : ""}
          </>
        }
        plakette={plakette}
        rechts={
          <span className="flex items-center gap-2">
            <Initialen name="HPP Architekten" groesse={26} />
            <span className="text-[12px] leading-tight text-app-text-still">
              HPP Architekten
              <span className="block text-app-text-leise">Baumanagement</span>
            </span>
          </span>
        }
      />

      {/* ───── Reihe 0: das Hochladen-Feld und die zwei Zahlen dazu ───── */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Karte hervorgehoben className="md:col-span-2">
          <KarteKopf
            titel="Fotos hochladen"
            unterzeile="Der kurze Weg von der Baustelle in den Projektordner"
            icon={Camera}
            aktion={
              <Button
                variante="sekundaer"
                onClick={() => onAnsicht("baufotos-galerie")}
              >
                Fotosätze
              </Button>
            }
          />
          <KarteInhalt className="flex flex-col gap-3">
            <HochladenFeld
              projektName={projekt.name}
              onHochladen={() => onAnsicht("baufotos-neu")}
            />
            <div className="flex flex-wrap items-baseline justify-between gap-2 border-t border-app-linie pt-2.5 text-[11.5px]">
              {letzter ? (
                <>
                  <span className="text-app-text-still">
                    Zuletzt: {letzter.kategorie} vom {formatDatumIso(letzter.datum)} ·{" "}
                    {letzter.anzahl_fotos} Foto(s)
                  </span>
                  <span className="text-app-text-leise">
                    {relativeZeit(letzter.erstellt_am ?? letzter.datum)}
                  </span>
                </>
              ) : (
                <span className="text-app-text-still">
                  {laedt
                    ? "Fotosätze werden geladen…"
                    : "Für dieses Bauvorhaben ist noch kein Fotosatz hochgeladen."}
                </span>
              )}
            </div>
          </KarteInhalt>
        </Karte>

        <Karte>
          <KarteKopf titel="Fotos im Projekt" icon={Images} />
          <KarteInhalt className="flex flex-col gap-3">
            <Kennzahl
              wert={gesamtFotos}
              label={`in ${fotosaetze.length} Fotosatz/Fotosätzen`}
              trend={trendAus(saetzeNeu, saetzeVorher)}
              hinweis={
                gesamtBytes > 0 ? `${formatBytes(gesamtBytes)} Bilddaten` : undefined
              }
            />
            <div className="flex items-baseline justify-between gap-2 border-t border-app-linie pt-2.5">
              <span className="text-[12px] text-app-text-still">
                Letzte {FENSTER_TAGE} Tage
              </span>
              <span className="text-[13px] font-semibold text-app-text">
                {fotosNeu} Foto(s)
              </span>
            </div>
          </KarteInhalt>
        </Karte>

        <Karte>
          <KarteKopf titel="Abholung ins Büro" icon={FolderCheck} />
          <KarteInhalt className="flex flex-col gap-3">
            <Kennzahl
              wert={offeneAbholung.length}
              art={
                fotosaetze.length > 0 && offeneAbholung.length === 0 ? "ok" : "normal"
              }
              label={
                fotosaetze.length === 0
                  ? laedt
                    ? "wird geladen…"
                    : "noch nichts hochgeladen"
                  : offeneAbholung.length > 0
                  ? "Fotosätze warten auf einen Bürorechner"
                  : "alle Sätze liegen im Projektordner"
              }
            />
            {/* Ein Bürorechner holt die Sätze ab und legt sie im Netzlaufwerk
                ab. Bis dahin liegen sie hier — die Quote sagt, wie weit das
                gediehen ist. */}
            <Quote
              label="abgeholt"
              prozent={fotosaetze.length > 0 ? (abgeholt / fotosaetze.length) * 100 : 0}
              rechts={`${abgeholt}/${fotosaetze.length}`}
              farbe="var(--color-app-ok)"
            />
          </KarteInhalt>
        </Karte>
      </div>

      {/* ───── Reihe 1: Verlauf und Kategorien ───── */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Karte className="xl:col-span-2">
          <KarteKopf
            titel="Dokumentierte Bautage"
            unterzeile="Fotosätze je Woche, acht Wochen"
            icon={TrendingUp}
          />
          <KarteInhalt className="flex flex-col gap-3">
            <div className="flex gap-6">
              <Kennzahl wert={saetzeNeu} label={`Fotosätze, ${FENSTER_TAGE} Tage`} />
              <Kennzahl wert={fotosNeu} label={`Fotos, ${FENSTER_TAGE} Tage`} />
            </div>
            <Kurve werte={wochen} hoehe={92} />
          </KarteInhalt>
        </Karte>

        <Karte>
          <KarteKopf
            titel="Kategorien"
            unterzeile={
              kategorien.length > 0
                ? `${kategorien.length} Kategorie(n) in diesem Projekt`
                : undefined
            }
            icon={Tags}
          />
          <KarteInhalt>
            {topKategorien.length === 0 ? (
              <LeerHinweis>
                {laedt
                  ? "Wird geladen…"
                  : "Die Kategorie entsteht beim Hochladen — sie wird Teil des Dateinamens."}
              </LeerHinweis>
            ) : (
              <div className="flex flex-col gap-3">
                {topKategorien.map(([name, anzahl]) => (
                  <Quote
                    key={name}
                    label={name}
                    prozent={gesamtFotos > 0 ? (anzahl / gesamtFotos) * 100 : 0}
                    rechts={`${anzahl}`}
                  />
                ))}
                {kategorien.length > topKategorien.length && (
                  <p className="text-[11.5px] text-app-text-leise">
                    {kategorien.length - topKategorien.length} weitere Kategorie(n)
                  </p>
                )}
              </div>
            )}
          </KarteInhalt>
        </Karte>
      </div>

      {/* ───── Reihe 2: Bilder und die letzten Sätze ───── */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Karte>
          <KarteKopf
            titel="Neueste Fotos"
            unterzeile={letzter ? `zuletzt ${formatDatumIso(letzter.datum)}` : undefined}
            icon={Camera}
            aktion={
              <Button
                variante="sekundaer"
                onClick={() => onAnsicht("baufotos-galerie")}
              >
                Öffnen
              </Button>
            }
          />
          <KarteInhalt className="flex flex-col gap-2.5">
            {neuesteFotosaetze.length === 0 ? (
              <LeerHinweis>
                Noch keine Baufotos. Beim Hochladen werden sie automatisch
                umbenannt und als ZIP bereitgestellt.
              </LeerHinweis>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-1.5">
                  {neuesteFotosaetze.map((satz) => (
                    <button
                      key={satz.id}
                      type="button"
                      onClick={() => onAnsicht("baufotos-galerie")}
                      className="relative aspect-[4/3] cursor-pointer overflow-hidden rounded-app-sm border border-app-linie bg-app-flaeche-still"
                      title={`${satz.kategorie} · ${formatDatumIso(satz.datum)}`}
                    >
                      {satz.titel_foto_id ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={api.baufotos.fotoUrl(satz.titel_foto_id, true)}
                          alt={`${satz.kategorie} vom ${formatDatumIso(satz.datum)}`}
                          className="size-full object-cover"
                          loading="lazy"
                        />
                      ) : (
                        <span className="flex size-full items-center justify-center text-app-text-leise">
                          <Images size={18} />
                        </span>
                      )}
                      <span className="absolute inset-x-0 bottom-0 truncate bg-black/50 px-1.5 py-0.5 text-left text-[10px] text-white">
                        {satz.kategorie}
                      </span>
                    </button>
                  ))}
                </div>
                <div className="flex items-center justify-between gap-2 text-[11.5px] text-app-text-still">
                  <span>
                    {fotosaetze.length} Fotosatz/Fotosätze · {gesamtFotos} Fotos
                  </span>
                  {letzter && <Plakette art="neutral">{letzter.kategorie}</Plakette>}
                </div>
              </>
            )}
          </KarteInhalt>
        </Karte>

        <Karte className="xl:col-span-2">
          <KarteKopf
            titel="Zuletzt hochgeladen"
            unterzeile="Ein Klick öffnet den Satz in der Galerie"
            icon={Images}
            menue
          />
          {letzteSaetze.length === 0 ? (
            <KarteInhalt>
              <LeerHinweis>
                {laedt
                  ? "Wird geladen…"
                  : "Noch keine Fotosätze in diesem Bauvorhaben."}
              </LeerHinweis>
            </KarteInhalt>
          ) : (
            <div className="border-t border-app-linie">
              {letzteSaetze.map((satz) => (
                <ListenZeile
                  key={satz.id}
                  vorne={<Initialen name={satz.kategorie} />}
                  titel={`${satz.kategorie} · ${satz.anzahl_fotos} Foto(s)`}
                  unterzeile={
                    <>
                      Bautag {formatDatumIso(satz.datum)}
                      {satz.groesse_bytes > 0
                        ? ` · ${formatBytes(satz.groesse_bytes)}`
                        : ""}
                      {satz.abgeholt_am ? " · abgeholt" : " · wartet auf Abholung"}
                    </>
                  }
                  rechts={
                    <span className="text-[11px] whitespace-nowrap text-app-text-leise">
                      {relativeZeit(satz.erstellt_am ?? satz.datum)}
                    </span>
                  }
                  onClick={() => onAnsicht("baufotos-galerie")}
                />
              ))}
            </div>
          )}
        </Karte>
      </div>
    </div>
  );
}
