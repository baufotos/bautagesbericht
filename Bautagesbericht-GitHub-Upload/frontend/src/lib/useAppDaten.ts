"use client";

/**
 * Datenschicht der App an einer Stelle.
 *
 * WARUM ALS HOOK UND NICHT IN DER SEITE
 * =====================================
 * ``app/page.tsx`` ist jetzt Router und Hülle: Sie entscheidet, welche Ansicht
 * zu sehen ist. Das Laden von Projekten, Mängeln, Berichten und Fotosätzen hat
 * damit nichts zu tun — und wäre dort zwischen dem Verzweigen kaum noch
 * lesbar. Hier liegt es zusammen, mit klaren Nachlade-Funktionen, die jede
 * Ansicht nach einer Änderung aufrufen kann.
 *
 * ZWEI EBENEN VON DATEN
 * =====================
 * Global (projektunabhängig): Projekte, Empfänger, Einreichungen, Wertelisten.
 * Je Projekt: Gewerke, Pläne, Mängel, Fotosätze, Foto-Kategorien.
 * Der Projektwechsel lädt nur die zweite Ebene neu — das ist der Unterschied
 * zwischen einem flüssigen Umschalten und einem kompletten Neuaufbau.
 *
 * Das gewählte Projekt wird im Browser gemerkt: Auf der Baustelle arbeitet man
 * einen Tag lang am selben Bauvorhaben und soll es nicht bei jedem Aufruf neu
 * heraussuchen müssen.
 */

import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import type {
  Einreichung,
  Empfaenger,
  FotosatzListItem,
  Gewerk,
  MangelFilter,
  MangelListItem,
  MangelStammdaten,
  Projekt,
  ProjektPlan,
} from "./types";

const PROJEKT_SPEICHER = "hpp-app-projekt";

/** Status, in denen eine Einreichung noch in Arbeit ist. */
const IN_ARBEIT = ["eingereicht", "wird_verarbeitet"];

export interface AppDaten {
  projekte: Projekt[];
  empfaenger: Empfaenger[];
  einreichungen: Einreichung[];

  projektId: number | null;
  projekt: Projekt | null;
  setzeProjekt: (id: number) => void;

  gewerke: Gewerk[];
  plaene: ProjektPlan[];
  maengel: MangelListItem[];
  fotosaetze: FotosatzListItem[];
  fotoKategorien: string[];
  stammdaten: MangelStammdaten | null;

  maengelFilter: MangelFilter;
  setzeMaengelFilter: (filter: MangelFilter) => void;

  laedt: boolean;
  laedtMaengel: boolean;
  laedtFotos: boolean;
  fehler: string | null;

  ladeAlles: () => void;
  ladeGlobal: () => Promise<void>;
  ladeEinreichungen: () => Promise<void>;
  ladeProjektDaten: () => Promise<void>;
  ladeMaengel: () => Promise<void>;
  ladeFotosaetze: () => Promise<void>;
  ladeStammdaten: () => Promise<void>;
}

export function useAppDaten(): AppDaten {
  const [projekte, setProjekte] = useState<Projekt[]>([]);
  const [empfaenger, setEmpfaenger] = useState<Empfaenger[]>([]);
  const [einreichungen, setEinreichungen] = useState<Einreichung[]>([]);

  const [projektId, setProjektId] = useState<number | null>(null);
  const [gewerke, setGewerke] = useState<Gewerk[]>([]);
  const [plaene, setPlaene] = useState<ProjektPlan[]>([]);
  const [maengel, setMaengel] = useState<MangelListItem[]>([]);
  const [fotosaetze, setFotosaetze] = useState<FotosatzListItem[]>([]);
  const [fotoKategorien, setFotoKategorien] = useState<string[]>([]);
  const [stammdaten, setStammdaten] = useState<MangelStammdaten | null>(null);

  const [maengelFilter, setMaengelFilter] = useState<MangelFilter>({});

  const [laedt, setLaedt] = useState(true);
  const [laedtMaengel, setLaedtMaengel] = useState(false);
  const [laedtFotos, setLaedtFotos] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  /* ───────── Globale Daten ───────── */

  const ladeGlobal = useCallback(async () => {
    setLaedt(true);
    try {
      const [p, e, s] = await Promise.all([
        api.projekte.list(),
        api.empfaenger.list(),
        api.einreichungen.list(),
      ]);
      setProjekte(p);
      setEmpfaenger(e);
      setEinreichungen(s);
      setFehler(null);
    } catch {
      setFehler(
        "Verbindung zum Server fehlgeschlagen. Läuft das Backend? Angezeigte " +
          "Daten können veraltet sein."
      );
    } finally {
      setLaedt(false);
    }
  }, []);

  const ladeEinreichungen = useCallback(async () => {
    try {
      setEinreichungen(await api.einreichungen.list());
    } catch {
      /* Der globale Fehlerhinweis steht schon; hier nicht überschreiben. */
    }
  }, []);

  const ladeStammdaten = useCallback(async () => {
    try {
      setStammdaten(await api.mangelStammdaten.alle());
    } catch {
      /* Wertelisten sind nicht kritisch — die Ansichten zeigen dann nur die
         bereits gespeicherten Werte. */
    }
  }, []);

  useEffect(() => {
    ladeGlobal();
    ladeStammdaten();
  }, [ladeGlobal, ladeStammdaten]);

  /* ───────── Projektwahl mit Gedächtnis ───────── */

  useEffect(() => {
    if (projekte.length === 0) return;
    setProjektId((alt) => {
      if (alt !== null && projekte.some((p) => p.id === alt)) return alt;
      const gemerkt = Number(window.localStorage.getItem(PROJEKT_SPEICHER));
      return projekte.some((p) => p.id === gemerkt) ? gemerkt : projekte[0].id;
    });
  }, [projekte]);

  const setzeProjekt = useCallback((id: number) => {
    setProjektId(id);
    window.localStorage.setItem(PROJEKT_SPEICHER, String(id));
    // Filter zurücksetzen: Ein Status- oder Firmenfilter des alten Projekts
    // passt im neuen fast nie und würde eine leere Liste vortäuschen.
    setMaengelFilter({});
  }, []);

  /* ───────── Daten des gewählten Projekts ───────── */

  const ladeProjektDaten = useCallback(async () => {
    if (projektId === null) return;
    try {
      const [g, p] = await Promise.all([
        api.gewerke.list(projektId),
        api.plaene.list(projektId),
      ]);
      setGewerke(g);
      setPlaene(p);
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Projektdaten nicht ladbar.");
    }
  }, [projektId]);

  const ladeMaengel = useCallback(async () => {
    if (projektId === null) return;
    setLaedtMaengel(true);
    try {
      setMaengel(await api.maengel.list({ ...maengelFilter, projekt_id: projektId }));
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Mängel nicht ladbar.");
    } finally {
      setLaedtMaengel(false);
    }
  }, [projektId, maengelFilter]);

  const ladeFotosaetze = useCallback(async () => {
    if (projektId === null) return;
    setLaedtFotos(true);
    try {
      const [saetze, kategorien] = await Promise.all([
        api.baufotos.list({ projekt_id: projektId }),
        api.baufotos.kategorien(projektId),
      ]);
      setFotosaetze(saetze);
      setFotoKategorien(kategorien);
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Baufotos nicht ladbar.");
    } finally {
      setLaedtFotos(false);
    }
  }, [projektId]);

  useEffect(() => {
    ladeProjektDaten();
  }, [ladeProjektDaten]);

  useEffect(() => {
    ladeMaengel();
  }, [ladeMaengel]);

  useEffect(() => {
    ladeFotosaetze();
  }, [ladeFotosaetze]);

  /* ───────── Verarbeitung beobachten ───────── */

  const inArbeit = einreichungen.some((e) => IN_ARBEIT.includes(e.status));

  useEffect(() => {
    // Solange ein Bericht verarbeitet wird, alle vier Sekunden nachsehen. Die
    // Verarbeitung läuft im Hintergrund des Servers und meldet sich nicht von
    // selbst; ohne dieses Nachfragen bliebe die Übersicht auf "wird
    // verarbeitet" stehen, obwohl das Dokument längst fertig ist.
    if (!inArbeit) return;
    const zeitgeber = setInterval(() => {
      ladeEinreichungen();
    }, 4000);
    return () => clearInterval(zeitgeber);
  }, [inArbeit, ladeEinreichungen]);

  const ladeAlles = useCallback(() => {
    ladeGlobal();
    ladeStammdaten();
    ladeProjektDaten();
    ladeMaengel();
    ladeFotosaetze();
  }, [ladeGlobal, ladeStammdaten, ladeProjektDaten, ladeMaengel, ladeFotosaetze]);

  return {
    projekte,
    empfaenger,
    einreichungen,

    projektId,
    projekt: projekte.find((p) => p.id === projektId) ?? null,
    setzeProjekt,

    gewerke,
    plaene,
    maengel,
    fotosaetze,
    fotoKategorien,
    stammdaten,

    maengelFilter,
    setzeMaengelFilter: setMaengelFilter,

    laedt,
    laedtMaengel,
    laedtFotos,
    fehler,

    ladeAlles,
    ladeGlobal,
    ladeEinreichungen,
    ladeProjektDaten,
    ladeMaengel,
    ladeFotosaetze,
    ladeStammdaten,
  };
}
