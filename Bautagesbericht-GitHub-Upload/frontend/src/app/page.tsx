"use client";

/**
 * Die Seite ist Router und Hülle — nicht mehr.
 *
 * Sie entscheidet, welche Ansicht zu sehen ist, hält die eine Ausnahme von der
 * Regel (die Mangel-Detailansicht legt sich über die gewählte Ansicht) und
 * verteilt die Daten aus ``useAppDaten`` an die Ansichten. Alles Fachliche
 * steckt in den Komponenten, alles Ladende im Hook.
 *
 * MERKEN UND VERLINKEN
 * ====================
 * Die zuletzt benutzte Ansicht wird im Browser gemerkt: Wer morgens die App
 * öffnet, landet dort, wo er aufgehört hat. Ein ausdrücklicher Link gewinnt
 * aber immer — die alten Links aus Teams-Nachrichten und aus dem App-Manifest
 * (``?tab=maengel``, ``?mangel=<id>``, ``?neu=1``) funktionieren deshalb
 * weiter; sie werden hier auf die neuen Ansichtsnamen abgebildet.
 *
 * ZWEI UMFÄNGE
 * ============
 * Die Website zeigt nur Baufotos und die Projekt-Stammdaten (lib/umfang.ts).
 * Der Router muss davon fast nichts wissen: Er prüft jede gemerkte und jede
 * verlinkte Ansicht gegen ``ALLE_EINTRAEGE``, und das ist dort schon die
 * gekürzte Liste. Was es nicht gibt, fällt aufs Dashboard zurück — kein
 * Sonderweg und keine zweite Wahrheit darüber, was diese Fassung kann.
 */

import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useAppDaten } from "@/lib/useAppDaten";
import type { Mangel } from "@/lib/types";
import {
  ALLE_EINTRAEGE,
  AppShell,
  eintragZu,
  type Ansicht,
} from "@/components/AppShell";
import { InstallierenHinweis, VerbindungsHinweis } from "@/components/AppSchale";
import { Karte, KarteInhalt, LeerHinweis, SeitenKopf } from "@/components/dashboard";
import { Meldung } from "@/components/ui";
import { NUR_FOTOS } from "@/lib/umfang";
import { Dashboard } from "@/components/dashboards/Dashboard";
import { FotoDashboard } from "@/components/dashboards/FotoDashboard";
import { BaufotosHochladen } from "@/components/baufotos/BaufotosHochladen";
import { FotosaetzeGalerie } from "@/components/baufotos/FotosaetzeGalerie";
import { BerichtEinreichen } from "@/components/bautagesberichte/BerichtEinreichen";
import { BerichteUebersicht } from "@/components/bautagesberichte/BerichteUebersicht";
import { ProjekteVerwaltung } from "@/components/stammdaten/ProjekteVerwaltung";
import { EmpfaengerVerwaltung } from "@/components/stammdaten/EmpfaengerVerwaltung";
import { MangelUebersicht } from "@/components/maengel/MangelUebersicht";
import { MangelErfassung } from "@/components/maengel/MangelErfassung";
import { MaengelanzeigeErstellen } from "@/components/maengel/MaengelanzeigeErstellen";
import { AnzeigeBeantworten } from "@/components/mehrkosten/AnzeigeBeantworten";
import { MangelDetail } from "@/components/maengel/MangelDetail";
import { ProjektberichteVerwaltung } from "@/components/projektberichte/ProjektberichteVerwaltung";
import { BesprechungenUebersicht } from "@/components/besprechungen/BesprechungenUebersicht";
import { BesprechungStammdaten } from "@/components/besprechungen/BesprechungStammdaten";
import { StammdatenGewerke } from "@/components/maengel/StammdatenGewerke";
import { StammdatenPlaene } from "@/components/maengel/StammdatenPlaene";
import { StammdatenListen } from "@/components/maengel/StammdatenListen";

const ANSICHT_SPEICHER = "hpp-app-ansicht";

/** Ansichten, die ihren Seitenkopf selbst setzen. */
const EIGENER_KOPF: Ansicht[] = ["dashboard"];

/**
 * Alte ``?tab=``-Links auf die heutigen Ansichtsnamen.
 *
 * Sie stehen in Teams-Nachrichten, in Lesezeichen und im App-Manifest und
 * dürfen nicht ins Leere laufen. Ob es die Ansicht in dieser Fassung
 * überhaupt gibt, entscheidet danach ``istAnsicht``.
 */
const ALT_TAB: Record<string, Ansicht> = {
  maengel: "maengel-uebersicht",
  einreichen: "btb-einreichen",
  uebersicht: "btb-uebersicht",
  projekte: "stamm-projekte",
  emails: "stamm-empfaenger",
};

function istAnsicht(wert: string | null): wert is Ansicht {
  return wert !== null && ALLE_EINTRAEGE.some((e) => e.key === wert);
}

export default function Home() {
  const daten = useAppDaten();
  const [ansicht, setAnsicht] = useState<Ansicht>("dashboard");
  const [offeneMangelId, setOffeneMangelId] = useState<number | null>(null);
  const [offenerMangel, setOffenerMangel] = useState<Mangel | null>(null);
  const [detailHinweis, setDetailHinweis] = useState<string | undefined>();
  // Suchbegriff aus der Kopfzeile für die Fotosatz-Galerie. Nur im Umfang
  // "fotos" belegt — sonst sucht die Kopfzeile in den Mängeln.
  const [fotoSuche, setFotoSuche] = useState("");

  /* ───────── Startansicht: Link, dann Gedächtnis ───────── */

  useEffect(() => {
    const parameter = new URLSearchParams(window.location.search);
    const mangel = Number(parameter.get("mangel"));
    const neu = parameter.get("neu") === "1";

    /* Die Reihenfolge ist die Rangfolge: ausdrücklicher Link, dann alter
       Link, zuletzt das Gedächtnis. Jeder Kandidat wird gegen die Navigation
       DIESER Fassung geprüft (ALLE_EINTRAEGE in AppShell) — auf der Website
       landet ein alter Mängel-Link damit ruhig auf dem Dashboard. */
    const kandidaten = [
      parameter.get("ansicht"),
      neu ? "maengel-neu" : null,
      mangel ? "maengel-uebersicht" : null,
      ALT_TAB[parameter.get("tab") ?? ""] ?? null,
      window.localStorage.getItem(ANSICHT_SPEICHER),
    ];
    const ziel = kandidaten.find(istAnsicht);
    if (ziel) setAnsicht(ziel);

    if (mangel && istAnsicht("maengel-uebersicht")) setOffeneMangelId(mangel);
  }, []);

  const wechsle = useCallback((ziel: Ansicht) => {
    setAnsicht(ziel);
    setOffeneMangelId(null);
    setDetailHinweis(undefined);
    // Der Suchbegriff aus der Kopfzeile gehört zur Galerie. Wer sie verlässt,
    // soll sie beim nächsten Öffnen nicht gefiltert vorfinden.
    if (ziel !== "baufotos-galerie") setFotoSuche("");
    window.localStorage.setItem(ANSICHT_SPEICHER, ziel);
  }, []);

  /* ───────── Mangel-Detail nachladen ───────── */

  const ladeMangel = useCallback(async (id: number) => {
    try {
      setOffenerMangel(await api.maengel.get(id));
    } catch {
      setOffeneMangelId(null);
      setOffenerMangel(null);
    }
  }, []);

  useEffect(() => {
    if (offeneMangelId === null) {
      setOffenerMangel(null);
      return;
    }
    ladeMangel(offeneMangelId);
  }, [offeneMangelId, ladeMangel]);

  function oeffneMangel(id: number) {
    setOffeneMangelId(id);
    setAnsicht("maengel-uebersicht");
  }

  /* ───────── Hülle ───────── */

  const eintrag = eintragZu(ansicht);

  const banner = (
    <>
      <InstallierenHinweis />
      <VerbindungsHinweis />
      {daten.fehler && (
        <div className="px-3 pt-3 sm:px-5">
          <Meldung art="fehler">{daten.fehler}</Meldung>
        </div>
      )}
    </>
  );

  return (
    <AppShell
      ansicht={ansicht}
      onAnsicht={wechsle}
      projekte={daten.projekte}
      projektId={daten.projektId}
      onProjekt={(id) => {
        daten.setzeProjekt(id);
        setOffeneMangelId(null);
      }}
      onSuche={(begriff) => {
        if (NUR_FOTOS) {
          // Auf der Website ist die Galerie die einzige Liste, in der es
          // etwas zu suchen gibt.
          setFotoSuche(begriff);
          wechsle("baufotos-galerie");
          return;
        }
        daten.setzeMaengelFilter({ ...daten.maengelFilter, suche: begriff || undefined });
        setOffeneMangelId(null);
        setAnsicht("maengel-uebersicht");
      }}
      onAktualisieren={daten.ladeAlles}
      // Zahl auf der Glocke in der Kopfzeile. Überfälligkeit rechnet der
      // Server aus (ist_ueberfaellig) — hier wird nur gezählt.
      ueberfaellig={daten.maengel.filter((m) => m.ist_ueberfaellig).length}
      laedt={daten.laedt || daten.laedtMaengel}
      banner={banner}
    >
      {/* Die Detailansicht eines Mangels legt sich über alles andere — auf dem
          Handy ist sie die ganze Fläche, und genau das ist beim Bearbeiten
          richtig. */}
      {offeneMangelId !== null ? (
        offenerMangel ? (
          <MangelDetail
            mangel={offenerMangel}
            gewerke={daten.gewerke}
            plaene={daten.plaene}
            stammdaten={daten.stammdaten}
            hinweis={detailHinweis}
            onZurueck={() => {
              setOffeneMangelId(null);
              setDetailHinweis(undefined);
              daten.ladeMaengel();
            }}
            onAktualisiert={() => {
              ladeMangel(offeneMangelId);
              daten.ladeMaengel();
            }}
            onGeloescht={() => {
              setOffeneMangelId(null);
              setDetailHinweis(undefined);
              daten.ladeMaengel();
            }}
            onDupliziert={(neueId) => {
              setDetailHinweis(
                "Duplikat angelegt. Bitte zuständige Firma und Frist prüfen — " +
                  "Autosend ist im Duplikat bewusst ausgeschaltet."
              );
              setOffeneMangelId(neueId);
              daten.ladeMaengel();
            }}
            onOeffnen={(id) => {
              setDetailHinweis(undefined);
              setOffeneMangelId(id);
            }}
          />
        ) : (
          <Karte>
            <KarteInhalt className="flex items-center gap-2 pt-4 text-[13px] text-app-text-still">
              <Loader2 size={15} className="animate-spin" />
              Mangel wird geladen…
            </KarteInhalt>
          </Karte>
        )
      ) : (
        <>
          {!EIGENER_KOPF.includes(ansicht) && (
            <SeitenKopf
              titel={eintrag.titel}
              kennung={
                <>
                  {eintrag.bereich}
                  {daten.projekt ? ` · ${daten.projekt.name}` : ""}
                </>
              }
            />
          )}

          <Inhalt
            ansicht={ansicht}
            daten={daten}
            fotoSuche={fotoSuche}
            onAnsicht={wechsle}
            onMangel={oeffneMangel}
            onMangelHinweis={setDetailHinweis}
          />
        </>
      )}
    </AppShell>
  );
}

/* ───────────────────────────── Verzweigung ───────────────────────────── */

function Inhalt({
  ansicht,
  daten,
  fotoSuche,
  onAnsicht,
  onMangel,
  onMangelHinweis,
}: {
  ansicht: Ansicht;
  daten: ReturnType<typeof useAppDaten>;
  /** Suchbegriff aus der Kopfzeile für die Galerie (nur Umfang "fotos"). */
  fotoSuche: string;
  onAnsicht: (ansicht: Ansicht) => void;
  onMangel: (id: number) => void;
  onMangelHinweis: (hinweis?: string) => void;
}) {
  const { projekt } = daten;

  /** Ansichten, die ohne Projekt sinnlos sind, bekommen einen klaren Hinweis. */
  function mitProjekt(inhalt: (p: NonNullable<typeof projekt>) => React.ReactNode) {
    if (projekt === null) {
      return (
        <LeerHinweis>
          Für diesen Bereich wird ein Projekt gebraucht. Bitte oben in der
          Kopfzeile ein Projekt wählen — oder unter „Stammdaten → Projekte“ eins
          anlegen.
        </LeerHinweis>
      );
    }
    return inhalt(projekt);
  }

  switch (ansicht) {
    case "dashboard":
      // Zwei Dashboards, ein Platz: Auf der Website hätte das große nichts zu
      // rechnen — Mängelquoten und Fristen stünden dort als lauter Nullen.
      return NUR_FOTOS ? (
        <FotoDashboard
          projekt={projekt}
          fotosaetze={daten.fotosaetze}
          laedt={daten.laedt || daten.laedtFotos}
          onAnsicht={onAnsicht}
        />
      ) : (
        <Dashboard
          projekt={projekt}
          maengel={daten.maengel}
          einreichungen={daten.einreichungen}
          fotosaetze={daten.fotosaetze}
          gewerke={daten.gewerke}
          laedt={daten.laedt}
          onAnsicht={onAnsicht}
          onMangel={onMangel}
        />
      );

    case "baufotos-neu":
      return mitProjekt((p) => (
        <BaufotosHochladen
          projekt={p}
          kategorien={daten.fotoKategorien}
          empfaenger={daten.empfaenger}
          gewerke={daten.gewerke}
          onFertig={() => {
            daten.ladeFotosaetze();
            onAnsicht("baufotos-galerie");
          }}
        />
      ));

    case "baufotos-galerie":
      return mitProjekt((p) => (
        <FotosaetzeGalerie
          projekt={p}
          fotosaetze={daten.fotosaetze}
          empfaenger={daten.empfaenger}
          gewerke={daten.gewerke}
          laedt={daten.laedtFotos}
          startSuche={fotoSuche}
          onAendern={daten.ladeFotosaetze}
          onNeu={() => onAnsicht("baufotos-neu")}
        />
      ));

    case "maengel-uebersicht":
      return mitProjekt((p) => (
        <MangelUebersicht
          maengel={daten.maengel}
          gewerke={daten.gewerke}
          stammdaten={daten.stammdaten}
          filter={{ ...daten.maengelFilter, projekt_id: p.id }}
          onFilter={daten.setzeMaengelFilter}
          onOeffnen={onMangel}
          onNeu={() => onAnsicht("maengel-neu")}
          laden={daten.laedtMaengel}
        />
      ));

    case "maengel-neu":
      return mitProjekt((p) => (
        <MangelErfassung
          projektId={p.id}
          projektName={p.name}
          gewerke={daten.gewerke}
          plaene={daten.plaene}
          stammdaten={daten.stammdaten}
          onGespeichert={(id, hinweis) => {
            onMangelHinweis(hinweis);
            daten.ladeMaengel();
            onMangel(id);
          }}
          onAbbrechen={() => onAnsicht("maengel-uebersicht")}
        />
      ));

    case "maengel-anzeige":
      return mitProjekt((p) => (
        <MaengelanzeigeErstellen
          projekt={p}
          gewerke={daten.gewerke}
          maengel={daten.maengel}
          laedt={daten.laedtMaengel}
          onAnsicht={onAnsicht}
        />
      ));

    case "anzeigen-beantworten":
      // Bewusst ohne ``mitProjekt``: Eine Anzeige laesst sich vollstaendig aus
      // dem hochgeladenen Schreiben beantworten. Wer auf ein Bauvorhaben
      // antworten muss, das in der App noch nicht angelegt ist, soll das
      // koennen, statt erst Stammdaten zu pflegen.
      return (
        <AnzeigeBeantworten
          projekt={projekt}
          onAnsicht={onAnsicht}
        />
      );

    case "projektberichte":
      return mitProjekt((p) => <ProjektberichteVerwaltung projekt={p} />);

    case "besprechungen":
      return mitProjekt((p) => (
        <BesprechungenUebersicht
          projekt={p}
          bearbeiter={daten.stammdaten?.bearbeiter ?? []}
        />
      ));

    case "stamm-besprechung":
      return mitProjekt((p) => <BesprechungStammdaten projekt={p} />);

    case "btb-einreichen":
      return (
        <BerichtEinreichen
          projekte={daten.projekte}
          empfaenger={daten.empfaenger}
          projektId={daten.projektId}
          einreichungen={daten.einreichungen}
          onEingereicht={daten.ladeEinreichungen}
        />
      );

    case "btb-uebersicht":
      return (
        <BerichteUebersicht
          einreichungen={daten.einreichungen}
          onAendern={daten.ladeEinreichungen}
        />
      );

    case "stamm-projekte":
      return (
        <ProjekteVerwaltung projekte={daten.projekte} onAendern={daten.ladeGlobal} />
      );

    case "stamm-firmen":
      return mitProjekt((p) => (
        <StammdatenGewerke
          projektId={p.id}
          projektName={p.name}
          gewerke={daten.gewerke}
          onAendern={daten.ladeProjektDaten}
        />
      ));

    case "stamm-plaene":
      return mitProjekt((p) => (
        <StammdatenPlaene
          projektId={p.id}
          projektName={p.name}
          plaene={daten.plaene}
          onAendern={daten.ladeProjektDaten}
        />
      ));

    case "stamm-empfaenger":
      return (
        <EmpfaengerVerwaltung
          empfaenger={daten.empfaenger}
          onAendern={daten.ladeGlobal}
        />
      );

    case "stamm-listen":
      return (
        <StammdatenListen
          stammdaten={daten.stammdaten}
          onAendern={daten.ladeStammdaten}
        />
      );

    default:
      return <LeerHinweis>Diese Ansicht gibt es nicht.</LeerHinweis>;
  }
}
