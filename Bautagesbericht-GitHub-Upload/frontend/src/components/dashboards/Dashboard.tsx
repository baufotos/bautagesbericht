"use client";

/**
 * Dashboard — der Zustand eines Bauvorhabens auf einem Bildschirm.
 *
 * GRUNDREGEL DIESER SEITE: Jede Zahl wird aus den übergebenen Listen gerechnet.
 * Es gibt keinen eigenen Statistik-Endpunkt und keine Platzhalterwerte. Wo
 * Daten fehlen, steht ein Hinweis — eine erfundene Kurve in einer Mängelliste
 * wäre schlimmer als eine leere Fläche.
 *
 * Die Auswahl der Karten folgt der Frage, die man morgens im Büro stellt:
 *   1. Wie steht es um die Mängel?           (Ring, Fristen, Firmen)
 *   2. Was läuft mir davon?                  (Fristenplan, kritische Aufgaben)
 *   3. Was ist zuletzt passiert?             (Aktivitäten, Berichte, Fotos)
 * Überfälligkeit kommt vom Server (``ist_ueberfaellig``) und wird hier nicht
 * nachgerechnet — sonst gäbe es zwei Wahrheiten.
 */

import {
  AlertTriangle,
  CalendarClock,
  Camera,
  FileText,
  Images,
  ListChecks,
  MapPin,
  PieChart,
  TrendingUp,
  Users,
} from "lucide-react";

import { api } from "@/lib/api";
import {
  alsZeitstempel,
  formatDatumIso,
  formatDatumKurzIso,
  heuteIso,
  relativeZeit,
} from "@/lib/formate";
import type {
  Einreichung,
  FotosatzListItem,
  Gewerk,
  MangelListItem,
  Projekt,
} from "@/lib/types";
import type { Ansicht } from "@/components/AppShell";
import {
  BalkenGruppe,
  Karte,
  KarteInhalt,
  KarteKopf,
  KartenGitter,
  Kennzahl,
  Initialen,
  LeerHinweis,
  ListenZeile,
  Kurve,
  Plakette,
  Quote,
  Ring,
  SeitenKopf,
  Zeitleiste,
  type ZeitleisteEintrag,
} from "@/components/dashboard";
import { Button } from "@/components/ui";

/** Wie viele Balken der Fristenplan höchstens zeigt. */
const MAX_ZEITLEISTE = 8;
/** Zeitraum der Kennzahlen "der letzten Tage". */
const FENSTER_TAGE = 30;

function tageZurueck(tage: number): number {
  return Date.now() - tage * 24 * 60 * 60 * 1000;
}

/**
 * Kurzname für die zentrale Zeitauslegung. Wichtig: Die Zeitstempel des
 * Servers sind naives UTC — siehe alsZeitstempel in lib/formate.
 */
const alsZeit = alsZeitstempel;

export function Dashboard({
  projekt,
  maengel,
  einreichungen,
  fotosaetze,
  gewerke,
  laedt,
  onAnsicht,
  onMangel,
}: {
  projekt: Projekt | null;
  maengel: MangelListItem[];
  einreichungen: Einreichung[];
  fotosaetze: FotosatzListItem[];
  gewerke: Gewerk[];
  laedt: boolean;
  onAnsicht: (ansicht: Ansicht) => void;
  onMangel: (id: number) => void;
}) {
  if (projekt === null) {
    return (
      <Karte>
        <KarteKopf titel="Kein Projekt gewählt" icon={MapPin} />
        <KarteInhalt className="flex flex-col items-start gap-3">
          <p className="text-[13px] text-app-text-still">
            Die App arbeitet immer an einem Bauvorhaben. Sobald ein Projekt
            angelegt ist, steht hier sein Zustand: Mängel, Fristen, Berichte und
            Baufotos.
          </p>
          <Button onClick={() => onAnsicht("stamm-projekte")} icon={MapPin}>
            Projekt anlegen
          </Button>
        </KarteInhalt>
      </Karte>
    );
  }

  /* ───────── Kennzahlen aus den Listen ───────── */

  const gesamt = maengel.length;
  const erledigt = maengel.filter((m) => m.ist_abgeschlossen).length;
  const ueberfaellig = maengel.filter((m) => m.ist_ueberfaellig);
  const offen = maengel.filter((m) => !m.ist_abgeschlossen);
  const anteilErledigt = gesamt > 0 ? (erledigt / gesamt) * 100 : 0;

  const prioZahlen = (["hoch", "mittel", "niedrig"] as const).map((stufe) => ({
    stufe,
    anzahl: offen.filter((m) => m.prioritaet === stufe).length,
  }));

  // Firmen mit den meisten offenen Mängeln — drei genügen, mehr liest niemand.
  const firmenZaehler = new Map<string, number>();
  for (const mangel of offen) {
    const name = mangel.firma_name || "ohne Firma";
    firmenZaehler.set(name, (firmenZaehler.get(name) ?? 0) + 1);
  }
  const topFirmen = [...firmenZaehler.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);

  const einreichungenProjekt = einreichungen.filter((e) => e.projekt_id === projekt.id);
  const grenze = tageZurueck(FENSTER_TAGE);
  const vorgrenze = tageZurueck(FENSTER_TAGE * 2);
  const berichteNeu = einreichungenProjekt.filter(
    (e) => alsZeit(e.eingereicht_am) >= grenze
  ).length;
  const fotosaetzeNeu = fotosaetze.filter((f) => alsZeit(f.datum) >= grenze).length;
  const fotosGesamt = fotosaetze.reduce((summe, f) => summe + f.anzahl_fotos, 0);

  /* ───────── Trends: dieser Zeitraum gegen den davor ─────────
     Beide Fenster sind gleich lang, damit der Vergleich etwas heißt. Wo in
     keinem der beiden Fenster etwas passiert ist, wird KEIN Trend angezeigt —
     "±0" neben zwei Nullen ist keine Aussage, sondern Zierde. */

  function imFenster(zeiten: number[], von: number, bis: number): number {
    return zeiten.filter((z) => z >= von && z < bis).length;
  }

  const mangelZeiten = maengel.map((m) => alsZeit(m.erstellt_am));
  const neuMaengel = imFenster(mangelZeiten, grenze, Date.now() + 1);
  const neuMaengelVorher = imFenster(mangelZeiten, vorgrenze, grenze);

  const fotoZeiten = fotosaetze.map((f) => alsZeit(f.datum));
  const neuFotosVorher = imFenster(fotoZeiten, vorgrenze, grenze);

  /**
   * Trend aus zwei Zählungen.
   *
   * ``wenigerIstBesser`` trennt Richtung und Bewertung: Neu erfasste Mängel
   * sind ein schlechtes Zeichen, wenn sie zunehmen; hochgeladene Fotosätze ein
   * gutes. Ohne diese Trennung wäre jeder steigende Wert grün.
   */
  function trendAus(jetzt: number, vorher: number, wenigerIstBesser: boolean) {
    if (jetzt === 0 && vorher === 0) return undefined;
    const differenz = jetzt - vorher;
    const auf = differenz >= 0;
    return {
      text: `${differenz > 0 ? "+" : differenz < 0 ? "−" : "±"}${Math.abs(differenz)}`,
      auf,
      gut: wenigerIstBesser ? differenz <= 0 : differenz >= 0,
      bezug: `zu den ${FENSTER_TAGE} Tagen davor`,
    };
  }

  // Neu erfasste Mängel je Woche, acht Wochen — der Verlauf in der Hauptkachel.
  const mangelWochen = Array.from({ length: 8 }, (_, i) =>
    imFenster(mangelZeiten, tageZurueck((8 - i) * 7), tageZurueck((7 - i) * 7))
  );

  // Dokumentierte Bautage je Woche der letzten acht Wochen. Bewusst nach
  // ``datum`` (dem Bautag) und nicht nach dem Einreichungszeitpunkt: Wer eine
  // Woche später fünf Tage nachreicht, hat fünf Bautage dokumentiert — nicht
  // einen Ausschlag am Tag des Hochladens.
  const wochen = Array.from({ length: 8 }, (_, i) => {
    const von = tageZurueck((8 - i) * 7);
    const bis = tageZurueck((7 - i) * 7);
    return einreichungenProjekt.filter((e) => {
      const zeit = alsZeit(e.datum);
      return zeit >= von && zeit < bis;
    }).length;
  });

  /* ───────── Fristenplan ───────── */

  const mitFrist = offen
    .filter((m) => m.aktuelle_frist)
    .sort((a, b) => alsZeit(a.aktuelle_frist) - alsZeit(b.aktuelle_frist));
  const zeitleiste: ZeitleisteEintrag[] = mitFrist
    .slice(0, MAX_ZEITLEISTE)
    .map((m) => ({
      label: `${m.nummer} ${m.kurzbezeichnung}`,
      von: m.erstellt_am,
      bis: m.aktuelle_frist as string,
      // Überfällig sticht rot heraus, alles andere bleibt ruhig grau: Bei acht
      // Balken in Akzenthelligkeit sähe man das eine Rot nicht mehr.
      farbe: m.ist_ueberfaellig
        ? "var(--color-app-gefahr)"
        : "var(--color-app-chart-still)",
      hinweis: `${m.firma_name || "ohne Firma"} · Frist ${formatDatumIso(
        m.aktuelle_frist
      )}`,
    }));
  const gekuerzt = Math.max(0, mitFrist.length - MAX_ZEITLEISTE);

  /* ───────── Letzte Aktivitäten ───────── */

  type Aktivitaet = {
    schluessel: string;
    zeit: number;
    person: string;
    titel: string;
    unterzeile: string;
    ziel: () => void;
  };

  const aktivitaeten: Aktivitaet[] = [
    ...maengel.map((m) => ({
      schluessel: `m-${m.id}`,
      zeit: alsZeit(m.erstellt_am),
      person: m.firma_name || "HPP",
      titel: `Mangel ${m.nummer} ${m.kurzbezeichnung}`,
      unterzeile: m.firma_name || "ohne Firma",
      ziel: () => onMangel(m.id),
    })),
    ...einreichungenProjekt.map((e) => ({
      schluessel: `e-${e.id}`,
      zeit: alsZeit(e.eingereicht_am),
      person: e.empfaenger_label || "Bericht",
      titel: `Bautagesbericht ${formatDatumIso(e.datum)}`,
      unterzeile: `für ${e.empfaenger_label}`,
      ziel: () => onAnsicht("btb-uebersicht"),
    })),
    ...fotosaetze.map((f) => ({
      schluessel: `f-${f.id}`,
      zeit: alsZeit(f.erstellt_am ?? f.datum),
      person: f.kategorie,
      titel: `Baufotos ${f.kategorie}`,
      unterzeile: `${f.anzahl_fotos} Foto(s) vom ${formatDatumIso(f.datum)}`,
      ziel: () => onAnsicht("baufotos-galerie"),
    })),
  ]
    .filter((a) => a.zeit > 0)
    .sort((a, b) => b.zeit - a.zeit)
    .slice(0, 6);

  const neuesteFotosaetze = fotosaetze.slice(0, 4);

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
        plakette={
          <Plakette art={ueberfaellig.length > 0 ? "gefahr" : "ok"} gross>
            {ueberfaellig.length > 0
              ? `${ueberfaellig.length} überfällig`
              : "Aktiv"}
          </Plakette>
        }
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

      {/* ───── Reihe 0: die eine Zahl, die morgens zählt ─────
          Links groß, was noch offen ist, mit Verlauf der Neuaufnahmen; rechts
          daneben zwei Kacheln mit den Zahlen, die man dazu braucht. */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Karte hervorgehoben className="md:col-span-2">
          <KarteKopf
            titel="Offene Mängel"
            unterzeile={`von ${gesamt} erfassten in diesem Projekt`}
            icon={ListChecks}
            aktion={
              <Button
                variante="sekundaer"
                onClick={() => onAnsicht("maengel-uebersicht")}
              >
                Übersicht
              </Button>
            }
          />
          <KarteInhalt className="flex flex-col gap-4">
            <Kennzahl
              gross
              wert={offen.length}
              label={
                gesamt === 0
                  ? laedt
                    ? "wird geladen…"
                    : "noch keine Mängel erfasst"
                  : `${erledigt} erledigt · ${Math.round(anteilErledigt)} % abgearbeitet`
              }
              trend={trendAus(neuMaengel, neuMaengelVorher, true)}
              hinweis={
                neuMaengel > 0
                  ? `${neuMaengel} in den letzten ${FENSTER_TAGE} Tagen neu aufgenommen`
                  : undefined
              }
            />
            <div>
              <div className="mb-1.5 text-[11px] text-app-text-still">
                Neu aufgenommene Mängel je Woche (8 Wochen)
              </div>
              <Kurve werte={mangelWochen} hoehe={92} />
            </div>
          </KarteInhalt>
        </Karte>

        <Karte>
          <KarteKopf titel="Überfällig" icon={AlertTriangle} />
          <KarteInhalt className="flex flex-col gap-3">
            <Kennzahl
              wert={ueberfaellig.length}
              art={ueberfaellig.length > 0 ? "gefahr" : "ok"}
              label={
                ueberfaellig.length > 0
                  ? "Frist verstrichen, nicht erledigt"
                  : "alle Fristen gehalten"
              }
            />
            <Quote
              label="Anteil an den offenen"
              prozent={offen.length > 0 ? (ueberfaellig.length / offen.length) * 100 : 0}
              rechts={`${ueberfaellig.length}/${offen.length}`}
              farbe="var(--color-app-gefahr)"
            />
          </KarteInhalt>
        </Karte>

        <Karte>
          <KarteKopf titel="Dokumentation" icon={Camera} />
          <KarteInhalt className="flex flex-col gap-3">
            <Kennzahl
              wert={fotosGesamt}
              label={`Fotos in ${fotosaetze.length} Fotosatz/Fotosätzen`}
              trend={trendAus(fotosaetzeNeu, neuFotosVorher, false)}
            />
            {/* Absichtlich keine Quote: Es gibt keine sinnvolle Bezugsgröße
                für "wie viele Berichte sollten es sein" — ein erfundener
                Prozentwert wäre schlimmer als die nackte Zahl. */}
            <div className="flex items-baseline justify-between gap-2 border-t border-app-linie pt-2.5">
              <span className="text-[12px] text-app-text-still">
                Bautagesberichte, letzte {FENSTER_TAGE} Tage
              </span>
              <span className="text-[13px] font-semibold text-app-text">
                {berichteNeu}
              </span>
            </div>
          </KarteInhalt>
        </Karte>
      </div>

      {/* ───── Reihe 1: Mängelstand ───── */}
      <KartenGitter spalten={3}>
        <Karte>
          <KarteKopf titel="Mängelstand" icon={PieChart} menue />
          <KarteInhalt>
            {gesamt === 0 ? (
              <LeerHinweis>
                {laedt ? "Wird geladen…" : "Für dieses Projekt sind keine Mängel erfasst."}
              </LeerHinweis>
            ) : (
              <div className="flex flex-col items-center gap-4 sm:flex-row">
                <Ring
                  prozent={anteilErledigt}
                  label={`${erledigt} von ${gesamt} erledigt`}
                />
                <div className="flex w-full flex-1 flex-col gap-2.5">
                  {prioZahlen.map(({ stufe, anzahl }) => (
                    <Quote
                      key={stufe}
                      label={`Priorität ${stufe}`}
                      prozent={offen.length > 0 ? (anzahl / offen.length) * 100 : 0}
                      rechts={`${anzahl}`}
                      farbe={
                        stufe === "hoch"
                          ? "var(--color-app-gefahr)"
                          : stufe === "mittel"
                          ? "var(--color-app-warn)"
                          : "var(--color-app-chart-still)"
                      }
                    />
                  ))}
                </div>
              </div>
            )}
          </KarteInhalt>
        </Karte>

        <Karte>
          <KarteKopf
            titel="Fristen"
            icon={CalendarClock}
            aktion={
              ueberfaellig.length > 0 ? (
                <Plakette art="gefahr">{ueberfaellig.length} überfällig</Plakette>
              ) : (
                <Plakette art="ok">In Zeit</Plakette>
              )
            }
          />
          <KarteInhalt>
            {gesamt === 0 ? (
              <LeerHinweis>Keine Fristen vorhanden.</LeerHinweis>
            ) : (
              <BalkenGruppe
                werte={[
                  {
                    // Grau statt Akzent: Der Akzent ist in der dunklen Fassung
                    // fast weiß, und ein weißer Balken in dieser Größe zieht
                    // alle Aufmerksamkeit auf den unauffälligsten Zustand.
                    label: "offen",
                    wert: offen.length - ueberfaellig.length,
                    farbe: "var(--color-app-chart-still)",
                  },
                  {
                    label: "überfällig",
                    wert: ueberfaellig.length,
                    farbe: "var(--color-app-gefahr)",
                  },
                  {
                    label: "erledigt",
                    wert: erledigt,
                    farbe: "var(--color-app-ok)",
                  },
                ]}
              />
            )}
          </KarteInhalt>
        </Karte>

        <Karte>
          <KarteKopf
            titel="Offene Mängel nach Firma"
            unterzeile={`${gewerke.length} Firma/Firmen im Projekt`}
            icon={Users}
            menue
          />
          <KarteInhalt>
            {topFirmen.length === 0 ? (
              <LeerHinweis>Keine offenen Mängel.</LeerHinweis>
            ) : (
              <div className="flex flex-col gap-3">
                {topFirmen.map(([name, anzahl]) => (
                  <Quote
                    key={name}
                    label={name}
                    prozent={offen.length > 0 ? (anzahl / offen.length) * 100 : 0}
                    rechts={`${anzahl}`}
                  />
                ))}
                {firmenZaehler.size > topFirmen.length && (
                  <p className="text-[11.5px] text-app-text-leise">
                    {firmenZaehler.size - topFirmen.length} weitere Firma/Firmen mit
                    offenen Mängeln
                  </p>
                )}
              </div>
            )}
          </KarteInhalt>
        </Karte>
      </KartenGitter>

      {/* ───── Reihe 2: Fristenplan + Berichte/Fotos ───── */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Karte className="xl:col-span-2">
          <KarteKopf
            titel="Fristenplan"
            unterzeile="Von der Aufnahme bis zur aktuellen Frist"
            icon={CalendarClock}
            aktion={
              <Button
                variante="sekundaer"
                onClick={() => onAnsicht("maengel-uebersicht")}
              >
                Alle Mängel
              </Button>
            }
          />
          <KarteInhalt>
            <Zeitleiste eintraege={zeitleiste} heute={heuteIso()} />
            {gekuerzt > 0 && (
              <p className="mt-2 text-[11.5px] text-app-text-leise">
                {gekuerzt} weitere Mängel mit Frist sind hier nicht dargestellt —
                die Übersicht zeigt alle.
              </p>
            )}
          </KarteInhalt>
        </Karte>

        <Karte>
          <KarteKopf
            titel="Berichte und Fotos"
            unterzeile={`letzte ${FENSTER_TAGE} Tage`}
            icon={TrendingUp}
          />
          <KarteInhalt className="flex flex-col gap-3">
            <div className="flex gap-6">
              <Kennzahl wert={berichteNeu} label="Bautagesberichte" />
              <Kennzahl wert={fotosaetzeNeu} label="Fotosätze" />
            </div>
            <div>
              <div className="mb-1 text-[11px] text-app-text-still">
                Dokumentierte Bautage je Woche (8 Wochen)
              </div>
              <Kurve werte={wochen} />
            </div>
            <div className="flex flex-wrap gap-2 border-t border-app-linie pt-2.5">
              <Button
                variante="still"
                icon={FileText}
                onClick={() => onAnsicht("btb-uebersicht")}
              >
                Berichte
              </Button>
              <Button
                variante="still"
                icon={Images}
                onClick={() => onAnsicht("baufotos-galerie")}
              >
                {fotosGesamt} Fotos
              </Button>
            </div>
          </KarteInhalt>
        </Karte>
      </div>

      {/* ───── Reihe 3: Aktivitäten, kritische Aufgaben, Fotos ───── */}
      <KartenGitter spalten={3}>
        <Karte>
          <KarteKopf titel="Letzte Aktivitäten" icon={ListChecks} menue />
          {aktivitaeten.length === 0 ? (
            <KarteInhalt>
              <LeerHinweis>Noch keine Vorgänge in diesem Projekt.</LeerHinweis>
            </KarteInhalt>
          ) : (
            <div className="border-t border-app-linie">
              {aktivitaeten.map((eintrag) => (
                <ListenZeile
                  key={eintrag.schluessel}
                  vorne={<Initialen name={eintrag.person} />}
                  titel={eintrag.titel}
                  unterzeile={eintrag.unterzeile}
                  rechts={
                    <span className="text-[11px] whitespace-nowrap text-app-text-leise">
                      {relativeZeit(new Date(eintrag.zeit).toISOString())}
                    </span>
                  }
                  onClick={eintrag.ziel}
                />
              ))}
            </div>
          )}
        </Karte>

        <Karte>
          <KarteKopf
            titel="Kritische Aufgaben"
            icon={AlertTriangle}
            aktion={
              ueberfaellig.length > 0 ? (
                <Plakette art="gefahr">{ueberfaellig.length}</Plakette>
              ) : undefined
            }
          />
          {ueberfaellig.length === 0 ? (
            <KarteInhalt>
              <LeerHinweis>
                Keine überfälligen Mängel. Alle Fristen sind eingehalten.
              </LeerHinweis>
            </KarteInhalt>
          ) : (
            <div className="border-t border-app-linie">
              {[...ueberfaellig]
                .sort((a, b) => {
                  const rang = { hoch: 0, mittel: 1, niedrig: 2 } as Record<string, number>;
                  const unterschied =
                    (rang[a.prioritaet] ?? 3) - (rang[b.prioritaet] ?? 3);
                  return unterschied !== 0
                    ? unterschied
                    : alsZeit(a.aktuelle_frist) - alsZeit(b.aktuelle_frist);
                })
                .slice(0, 6)
                .map((mangel) => (
                  <ListenZeile
                    key={mangel.id}
                    titel={`${mangel.nummer} ${mangel.kurzbezeichnung}`}
                    unterzeile={`${mangel.firma_name || "ohne Firma"} · Frist ${formatDatumKurzIso(
                      mangel.aktuelle_frist
                    )}`}
                    rechts={
                      <Plakette
                        art={
                          mangel.prioritaet === "hoch"
                            ? "gefahr"
                            : mangel.prioritaet === "mittel"
                            ? "warn"
                            : "neutral"
                        }
                      >
                        {mangel.prioritaet}
                      </Plakette>
                    }
                    onClick={() => onMangel(mangel.id)}
                  />
                ))}
            </div>
          )}
        </Karte>

        <Karte>
          <KarteKopf
            titel="Fotodokumentation"
            unterzeile={
              fotosaetze.length > 0
                ? `zuletzt ${formatDatumIso(fotosaetze[0].datum)}`
                : undefined
            }
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
                Noch keine Baufotos. Fotos werden beim Hochladen automatisch
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
                    {fotosaetze.length} Fotosatz/Fotosätze · {fotosGesamt} Fotos
                  </span>
                  {fotosaetze[0] && (
                    <Plakette art="neutral">{fotosaetze[0].kategorie}</Plakette>
                  )}
                </div>
              </>
            )}
          </KarteInhalt>
        </Karte>
      </KartenGitter>
    </div>
  );
}
