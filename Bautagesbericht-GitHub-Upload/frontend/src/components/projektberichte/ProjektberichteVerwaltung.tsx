"use client";

/**
 * Projektberichte (Monatsberichte): Liste und Formular.
 *
 * DAS FORMULAR BAUT SICH AUS DER GLIEDERUNG
 * =========================================
 * Die Kapitelstruktur kommt vom Server (``/projektberichte/gliederung``) und
 * ist nicht hier verdrahtet. Ein neues Kapitel wird im Backend ergänzt und
 * erscheint hier von selbst — genau so ist die Gliederung gedacht.
 *
 * WAS DIE VORSCHAU ZEIGT
 * ======================
 * Nicht das fertige Aussehen, sondern die **Nummerierung**: welche Kapitel
 * erscheinen, welche Nummer sie bekommen und welche mangels Inhalt entfallen.
 * Das ist die Stelle, an der die bisherige Word-Vorlage regelmäßig
 * auseinanderläuft (im Referenzbericht sagt das Verzeichnis „2.2 Fortschritt“,
 * der Text „2.2 Verzögerungen“). Wer hier hinsieht, sieht es vorher.
 *
 * ROTE ZEILEN
 * ===========
 * Eine Zeile, die mit „!“ beginnt, wird im Dokument rot gesetzt — für
 * terminkritische Aussagen wie „Voraussichtlich im Oktober 2026“. Bewusst eine
 * Textmarkierung und kein Editor mit Werkzeugleiste: Getippt wird auf der
 * Baustelle, oft mit einer Hand.
 */

import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronRight,
  Download,
  Eye,
  FileText,
  Images,
  ListOrdered,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { dateiSpeichern } from "@/lib/dateien";
import { formatDatumIso, heuteIso } from "@/lib/formate";
import type {
  Baubegehung,
  Besprechung,
  GliederungHauptkapitel,
  Projekt,
  Projektbericht,
  ProjektberichtListItem,
  ProjektberichtVorschau,
  SollIstZeile,
} from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  LeerHinweis,
  Plakette,
} from "@/components/dashboard";
import { Button, Field, Input, Meldung, Textarea } from "@/components/ui";

/** Markierung am Zeilenanfang, die im Dokument rot erscheint. */
const ROT_MARKE = "!";

export function ProjektberichteVerwaltung({
  projekt,
}: {
  projekt: Projekt;
}) {
  const [berichte, setBerichte] = useState<ProjektberichtListItem[]>([]);
  const [gliederung, setGliederung] = useState<GliederungHauptkapitel[]>([]);
  const [offener, setOffener] = useState<Projektbericht | null>(null);
  const [laedt, setLaedt] = useState(true);
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);

  const laden = useCallback(async () => {
    setLaedt(true);
    try {
      const [liste, gl] = await Promise.all([
        api.projektberichte.list(projekt.id),
        api.projektberichte.gliederung(),
      ]);
      setBerichte(liste);
      setGliederung(gl);
      setFehler(null);
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Berichte nicht ladbar.");
    } finally {
      setLaedt(false);
    }
  }, [projekt.id]);

  useEffect(() => {
    setOffener(null);
    void laden();
  }, [laden]);

  async function neu(ausLetztem: boolean) {
    setFehler(null);
    setMeldung(null);
    try {
      const vorlage = await api.projektberichte.vorlage(projekt.id);
      const angelegt = await api.projektberichte.create({
        ...vorlage,
        projekt_id: projekt.id,
        aus_letztem_bericht: ausLetztem,
      });
      setOffener(angelegt);
      await laden();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Anlegen fehlgeschlagen.");
    }
  }

  async function oeffnen(id: number) {
    setFehler(null);
    setMeldung(null);
    try {
      setOffener(await api.projektberichte.get(id));
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Bericht nicht ladbar.");
    }
  }

  async function loeschen(bericht: ProjektberichtListItem) {
    if (
      !window.confirm(
        `Projektbericht Nr. ${bericht.nummer} vom ` +
          `${formatDatumIso(bericht.berichtsdatum)} endgültig löschen? ` +
          `Fotos und erzeugte Dokumente werden mit entfernt.`
      )
    ) {
      return;
    }
    try {
      await api.projektberichte.delete(bericht.id);
      if (offener?.id === bericht.id) setOffener(null);
      await laden();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Löschen fehlgeschlagen.");
    }
  }

  if (offener) {
    return (
      <BerichtFormular
        bericht={offener}
        gliederung={gliederung}
        onZurueck={() => {
          setOffener(null);
          void laden();
        }}
        onGespeichert={(neuer) => setOffener(neuer)}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}
      {meldung && <Meldung art="erfolg">{meldung}</Meldung>}

      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-app-text-still">
          {berichte.length} Bericht(e) · {projekt.name}
        </span>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button
            variante="sekundaer"
            onClick={() => neu(true)}
            disabled={berichte.length === 0}
          >
            Aus letztem fortschreiben
          </Button>
          <Button icon={Plus} onClick={() => neu(false)}>
            Neuer Bericht
          </Button>
        </div>
      </div>

      {berichte.length === 0 ? (
        <LeerHinweis>
          {laedt
            ? "Berichte werden geladen…"
            : "Für dieses Projekt gibt es noch keinen Monatsbericht. Der erste " +
              "bekommt die Nummer 1; jeder weitere zählt hoch und kann die " +
              "Inhalte des vorigen übernehmen."}
        </LeerHinweis>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {berichte.map((bericht) => (
            <Karte key={bericht.id}>
              <KarteKopf
                titel={`Monatsbericht Nr. ${bericht.nummer}`}
                unterzeile={
                  <>
                    {formatDatumIso(bericht.berichtsdatum)}
                    {bericht.ersteller ? ` · ${bericht.ersteller}` : ""}
                  </>
                }
                icon={FileText}
                aktion={
                  bericht.hat_dokument ? (
                    <Plakette art="ok">erzeugt</Plakette>
                  ) : (
                    <Plakette art="neutral">Entwurf</Plakette>
                  )
                }
              />
              <KarteInhalt className="flex flex-col gap-2.5">
                <div className="text-[12px] text-app-text-still">
                  {bericht.anzahl_kapitel} Kapitel · {bericht.anzahl_fotos} Foto(s)
                  {bericht.erzeugt_am && " · zuletzt erzeugt"}
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Button onClick={() => oeffnen(bericht.id)}>Bearbeiten</Button>
                  {bericht.hat_dokument && (
                    <Button
                      variante="sekundaer"
                      icon={Download}
                      onClick={async () => {
                        try {
                          const { blob, dateiname } =
                            await api.projektberichte.abrufen(bericht.id, "docx");
                          dateiSpeichern(blob, dateiname || "bericht.docx");
                        } catch (err) {
                          setFehler(
                            err instanceof Error ? err.message : "Abruf fehlgeschlagen."
                          );
                        }
                      }}
                    >
                      Word
                    </Button>
                  )}
                  <button
                    type="button"
                    onClick={() => loeschen(bericht)}
                    aria-label={`Bericht Nr. ${bericht.nummer} löschen`}
                    className="ml-auto cursor-pointer p-1.5 text-app-text-leise transition-colors hover:text-app-gefahr"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </KarteInhalt>
            </Karte>
          ))}
        </div>
      )}
    </div>
  );
}

/* ───────────────────────────── Formular ───────────────────────────── */

function BerichtFormular({
  bericht,
  gliederung,
  onZurueck,
  onGespeichert,
}: {
  bericht: Projektbericht;
  gliederung: GliederungHauptkapitel[];
  onZurueck: () => void;
  onGespeichert: (bericht: Projektbericht) => void;
}) {
  const [entwurf, setEntwurf] = useState<Projektbericht>(bericht);
  const [offeneGruppen, setOffeneGruppen] = useState<string[]>(
    gliederung.slice(0, 2).map((g) => g.schluessel)
  );
  const [vorschau, setVorschau] = useState<ProjektberichtVorschau | null>(null);
  const [laeuft, setLaeuft] = useState<"" | "speichern" | "docx" | "pdf" | "vorschau">("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [ungespeichert, setUngespeichert] = useState(false);

  useEffect(() => {
    setEntwurf(bericht);
    setUngespeichert(false);
  }, [bericht]);

  // Gliederung gleich beim Öffnen holen: Sie ist die eigentliche Auskunft
  // dieses Formulars (welche Kapitel erscheinen, mit welcher Nummer) — und sie
  // sagt nebenbei, ob auf diesem Rechner eine PDF möglich ist.
  useEffect(() => {
    let abgebrochen = false;
    api.projektberichte
      .vorschau(bericht.id)
      .then((v) => {
        if (!abgebrochen) setVorschau(v);
      })
      .catch(() => {
        /* Vorschau ist Beiwerk — das Formular funktioniert auch ohne. */
      });
    return () => {
      abgebrochen = true;
    };
  }, [bericht.id]);

  function aendern<K extends keyof Projektbericht>(feld: K, wert: Projektbericht[K]) {
    setEntwurf((alt) => ({ ...alt, [feld]: wert }));
    setUngespeichert(true);
    setVorschau(null);
  }

  function kapitelAendern(schluessel: string, text: string) {
    setEntwurf((alt) => ({ ...alt, kapitel: { ...alt.kapitel, [schluessel]: text } }));
    setUngespeichert(true);
    setVorschau(null);
  }

  function meldeFehler(err: unknown, standard: string) {
    if (err instanceof ApiError && typeof err.detail === "string") setFehler(err.detail);
    else setFehler(err instanceof Error ? err.message : standard);
  }

  const speichern = useCallback(async (): Promise<Projektbericht | null> => {
    setFehler(null);
    setLaeuft("speichern");
    try {
      const gespeichert = await api.projektberichte.update(entwurf.id, {
        nummer: entwurf.nummer,
        berichtsdatum: entwurf.berichtsdatum,
        zeitraum_von: entwurf.zeitraum_von,
        zeitraum_bis: entwurf.zeitraum_bis,
        ersteller: entwurf.ersteller,
        projektname: entwurf.projektname,
        projektkuerzel: entwurf.projektkuerzel,
        buero: entwurf.buero,
        kapitel: entwurf.kapitel,
        baubegehungen: entwurf.baubegehungen,
        besprechungen: entwurf.besprechungen,
        soll_ist: entwurf.soll_ist,
      });
      setUngespeichert(false);
      onGespeichert(gespeichert);
      return gespeichert;
    } catch (err) {
      meldeFehler(err, "Speichern fehlgeschlagen.");
      return null;
    } finally {
      setLaeuft("");
    }
  }, [entwurf, onGespeichert]);

  async function zeigeVorschau() {
    setMeldung(null);
    if (ungespeichert && !(await speichern())) return;
    setLaeuft("vorschau");
    try {
      setVorschau(await api.projektberichte.vorschau(entwurf.id));
    } catch (err) {
      meldeFehler(err, "Vorschau fehlgeschlagen.");
    } finally {
      setLaeuft("");
    }
  }

  async function erzeugen(format: "docx" | "pdf") {
    setMeldung(null);
    setFehler(null);
    if (ungespeichert && !(await speichern())) return;
    setLaeuft(format);
    try {
      const { blob, dateiname } = await api.projektberichte.erzeugen(entwurf.id, format);
      dateiSpeichern(blob, dateiname || `bericht.${format}`);
      setMeldung(
        format === "pdf"
          ? "PDF erzeugt und am Bericht abgelegt."
          : "Word-Dokument erzeugt und am Bericht abgelegt."
      );
      setVorschau(await api.projektberichte.vorschau(entwurf.id));
    } catch (err) {
      meldeFehler(err, "Erzeugen fehlgeschlagen.");
    } finally {
      setLaeuft("");
    }
  }

  const gefuellt = useMemo(() => {
    const anzahl = Object.values(entwurf.kapitel || {}).filter(
      (t) => (t || "").trim()
    ).length;
    return anzahl;
  }, [entwurf.kapitel]);

  return (
    <div className="flex flex-col gap-4">
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}
      {meldung && <Meldung art="erfolg">{meldung}</Meldung>}

      {/* Kopfleiste */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variante="still" icon={ArrowLeft} onClick={onZurueck}>
          Alle Berichte
        </Button>
        <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-app-text-still">
          Nr. {entwurf.nummer} · {gefuellt} Kapitel befüllt ·{" "}
          {entwurf.fotos.length} Foto(s)
        </span>
        <div className="ml-auto flex flex-wrap gap-2">
          {ungespeichert && (
            <span className="self-center text-[11.5px] text-app-warn">
              nicht gespeichert
            </span>
          )}
          <Button
            variante="sekundaer"
            icon={Save}
            onClick={speichern}
            disabled={laeuft !== ""}
          >
            {laeuft === "speichern" ? "Speichert…" : "Speichern"}
          </Button>
          <Button
            variante="sekundaer"
            icon={Eye}
            onClick={zeigeVorschau}
            disabled={laeuft !== ""}
          >
            Vorschau
          </Button>
          <Button icon={FileText} onClick={() => erzeugen("docx")} disabled={laeuft !== ""}>
            {laeuft === "docx" ? "Wird erzeugt…" : "Word erzeugen"}
          </Button>
          {vorschau?.pdf_moeglich !== false && (
            <Button
              variante="sekundaer"
              icon={Download}
              onClick={() => erzeugen("pdf")}
              disabled={laeuft !== ""}
            >
              {laeuft === "pdf" ? "Wird erzeugt…" : "PDF"}
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* ───── Kapitel ───── */}
        <div className="flex flex-col gap-4 xl:col-span-2">
          <Karte>
            <KarteKopf titel="Stammdaten" icon={FileText} />
            <KarteInhalt className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Berichtsnummer (Pflicht)">
                <Input
                  type="number"
                  min={1}
                  value={entwurf.nummer}
                  onChange={(e) => aendern("nummer", Number(e.target.value))}
                />
              </Field>
              <Field label="Berichtsdatum (Pflicht)">
                <Input
                  type="date"
                  value={entwurf.berichtsdatum || heuteIso()}
                  onChange={(e) => aendern("berichtsdatum", e.target.value)}
                />
              </Field>
              <Field label="Zeitraum von">
                <Input
                  type="date"
                  value={entwurf.zeitraum_von || ""}
                  onChange={(e) => aendern("zeitraum_von", e.target.value || null)}
                />
              </Field>
              <Field label="Zeitraum bis">
                <Input
                  type="date"
                  value={entwurf.zeitraum_bis || ""}
                  onChange={(e) => aendern("zeitraum_bis", e.target.value || null)}
                />
              </Field>
              <Field label="Ersteller/in">
                <Input
                  value={entwurf.ersteller}
                  onChange={(e) => aendern("ersteller", e.target.value)}
                />
              </Field>
              <Field
                label="Projektkürzel"
                hinweis="Steht in der Fußzeile und im Dateinamen („BoB“)."
              >
                <Input
                  value={entwurf.projektkuerzel}
                  onChange={(e) => aendern("projektkuerzel", e.target.value)}
                />
              </Field>
              <Field
                label="Projektname (Kopfzeile)"
                className="sm:col-span-2"
                hinweis="Steht oben links auf der ersten Seite."
              >
                <Input
                  value={entwurf.projektname}
                  onChange={(e) => aendern("projektname", e.target.value)}
                />
              </Field>
            </KarteInhalt>
          </Karte>

          {gliederung.map((haupt) => {
            const offen = offeneGruppen.includes(haupt.schluessel);
            return (
              <Karte key={haupt.schluessel}>
                <button
                  type="button"
                  onClick={() =>
                    setOffeneGruppen((alt) =>
                      alt.includes(haupt.schluessel)
                        ? alt.filter((s) => s !== haupt.schluessel)
                        : [...alt, haupt.schluessel]
                    )
                  }
                  className="flex w-full cursor-pointer items-center gap-2 px-4 py-3 text-left sm:px-5"
                >
                  {offen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                  <span className="text-[13px] font-semibold text-app-text">
                    {haupt.titel}
                  </span>
                  <span className="ml-auto text-[11.5px] text-app-text-still">
                    {haupt.unterkapitel.length || 1} Kapitel
                  </span>
                </button>

                {offen && (
                  <KarteInhalt className="flex flex-col gap-4 border-t border-app-linie pt-4">
                    {(haupt.unterkapitel.length
                      ? haupt.unterkapitel
                      : [{
                          schluessel: haupt.schluessel,
                          titel: haupt.titel,
                          art: haupt.art,
                          immer_zeigen: false,
                        }]
                    ).map((unter) => (
                      <KapitelFeld
                        key={unter.schluessel}
                        titel={unter.titel}
                        art={unter.art}
                        immerZeigen={unter.immer_zeigen}
                        text={entwurf.kapitel?.[unter.schluessel] || ""}
                        onText={(t) => kapitelAendern(unter.schluessel, t)}
                        bericht={entwurf}
                        onBericht={(neuer) => {
                          setEntwurf(neuer);
                          setUngespeichert(true);
                          setVorschau(null);
                        }}
                        onFotosGeaendert={async () => {
                          const frisch = await api.projektberichte.get(entwurf.id);
                          setEntwurf(frisch);
                          onGespeichert(frisch);
                          setVorschau(null);
                        }}
                      />
                    ))}
                  </KarteInhalt>
                )}
              </Karte>
            );
          })}
        </div>

        {/* ───── Vorschau der Nummerierung ───── */}
        <div className="flex flex-col gap-4">
          <Karte hervorgehoben>
            <KarteKopf
              titel="Gliederung des Dokuments"
              unterzeile="Leere Kapitel entfallen und die Nummern rücken nach"
              icon={ListOrdered}
            />
            <KarteInhalt className="flex flex-col gap-3">
              {!vorschau ? (
                <LeerHinweis>
                  Auf „Vorschau“ tippen — dann steht hier, welche Kapitel im
                  Dokument erscheinen und welche Nummer sie tragen.
                </LeerHinweis>
              ) : (
                <>
                  <div className="font-mono text-[11.5px] break-all text-app-text-still">
                    {vorschau.dateiname_docx}
                  </div>
                  <div className="flex max-h-[380px] flex-col gap-0.5 overflow-y-auto">
                    {vorschau.kapitel.map((k) => (
                      <div
                        key={k.schluessel}
                        className={`flex items-baseline gap-2 text-[12px] ${
                          k.ebene === 1 ? "mt-1.5 font-semibold text-app-text" : "text-app-text-still"
                        }`}
                      >
                        <span className="w-9 shrink-0 font-mono">{k.nummer}</span>
                        <span className="min-w-0 flex-1 truncate">{k.titel}</span>
                        {!k.hat_inhalt && (
                          <span className="shrink-0 text-[10px] text-app-text-leise">
                            ohne Text
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                  {vorschau.entfallen.length > 0 && (
                    <details className="border-t border-app-linie pt-2">
                      <summary className="cursor-pointer text-[11.5px] text-app-text-still">
                        {vorschau.entfallen.length} Kapitel entfallen (leer)
                      </summary>
                      <ul className="mt-1.5 flex flex-col gap-0.5 text-[11px] text-app-text-leise">
                        {vorschau.entfallen.map((e) => (
                          <li key={e}>{e}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                  {vorschau.pdf_moeglich === false && (
                    <Meldung art="hinweis">
                      <span className="flex items-start gap-2">
                        <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                        <span>
                          PDF entsteht über Word — auf diesem Rechner ist keines
                          erreichbar. Das Word-Dokument geht trotzdem.
                        </span>
                      </span>
                    </Meldung>
                  )}
                </>
              )}
            </KarteInhalt>
          </Karte>

          <Karte>
            <KarteKopf
              titel="Terminkritisches hervorheben"
              icon={AlertTriangle}
            />
            <KarteInhalt className="text-[12px] leading-relaxed text-app-text-still">
              Eine Zeile, die mit <span className="font-mono text-app-text">!</span>{" "}
              beginnt, erscheint im Bericht <span className="text-app-gefahr">rot</span> —
              so wie „Voraussichtlich im Oktober 2026“ in der Vorlage. Das
              Ausrufezeichen selbst wird nicht gedruckt.
            </KarteInhalt>
          </Karte>
        </div>
      </div>
    </div>
  );
}

/* ───────────────────────────── Ein Kapitelfeld ───────────────────────────── */

function KapitelFeld({
  titel,
  art,
  immerZeigen,
  text,
  onText,
  bericht,
  onBericht,
  onFotosGeaendert,
}: {
  titel: string;
  art: string;
  immerZeigen: boolean;
  text: string;
  onText: (text: string) => void;
  bericht: Projektbericht;
  onBericht: (bericht: Projektbericht) => void;
  onFotosGeaendert: () => void | Promise<void>;
}) {
  if (art === "baubegehungen") {
    return (
      <ListenFeld
        titel={titel}
        spalten={["Datum", "Teilnehmer", "Firma"]}
        zeilen={bericht.baubegehungen.map((b) => [b.datum, b.teilnehmer, b.firma])}
        onAendern={(zeilen) =>
          onBericht({
            ...bericht,
            baubegehungen: zeilen.map(
              ([datum, teilnehmer, firma]): Baubegehung => ({ datum, teilnehmer, firma })
            ),
          })
        }
      />
    );
  }

  if (art === "besprechungen") {
    return (
      <ListenFeld
        titel={titel}
        spalten={["Bezeichnung", "Rhythmus", "Uhrzeit"]}
        zeilen={bericht.besprechungen.map((b) => [b.bezeichnung, b.rhythmus, b.uhrzeit])}
        onAendern={(zeilen) =>
          onBericht({
            ...bericht,
            besprechungen: zeilen.map(
              ([bezeichnung, rhythmus, uhrzeit]): Besprechung => ({
                bezeichnung, rhythmus, uhrzeit,
              })
            ),
          })
        }
      />
    );
  }

  if (art === "sollist") {
    return (
      <ListenFeld
        titel={titel}
        spalten={["Bezeichnung", "SOLL", "IST (Starttermin)", "Verzug"]}
        zeilen={bericht.soll_ist.map((z) => [z.bezeichnung, z.soll, z.ist, z.verzug])}
        onAendern={(zeilen) =>
          onBericht({
            ...bericht,
            soll_ist: zeilen.map(
              ([bezeichnung, soll, ist, verzug]): SollIstZeile => ({
                bezeichnung, soll, ist, verzug,
              })
            ),
          })
        }
      />
    );
  }

  if (art === "fotos") {
    return <FotoFeld titel={titel} bericht={bericht} onGeaendert={onFotosGeaendert} />;
  }

  return (
    <Field
      label={titel}
      hinweis={
        immerZeigen
          ? "Erscheint auch ohne Text (wie in der Vorlage)."
          : "Bleibt das Feld leer, entfällt das Kapitel und die Nummern rücken nach."
      }
    >
      <Textarea
        value={text}
        onChange={(e) => onText(e.target.value)}
        rows={4}
        placeholder="…"
      />
    </Field>
  );
}

/* ───────────────────────── Wiederholbare Listen ───────────────────────── */

function ListenFeld({
  titel,
  spalten,
  zeilen,
  onAendern,
}: {
  titel: string;
  spalten: string[];
  zeilen: string[][];
  onAendern: (zeilen: string[][]) => void;
}) {
  function setzen(zeile: number, spalte: number, wert: string) {
    const kopie = zeilen.map((z) => [...z]);
    kopie[zeile][spalte] = wert;
    onAendern(kopie);
  }

  return (
    <div>
      <div className="mb-1.5 font-mono text-[10.5px] uppercase tracking-[0.1em] text-app-text-still">
        {titel}
      </div>
      <div className="flex flex-col gap-1.5">
        {zeilen.map((zeile, i) => (
          <div key={i} className="flex flex-wrap items-center gap-1.5">
            {spalten.map((spalte, s) => (
              <div key={spalte} className="min-w-[120px] flex-1">
                <Input
                  value={zeile[s] ?? ""}
                  placeholder={spalte}
                  onChange={(e) => setzen(i, s, e.target.value)}
                />
              </div>
            ))}
            <button
              type="button"
              onClick={() => onAendern(zeilen.filter((_, x) => x !== i))}
              aria-label="Zeile entfernen"
              className="cursor-pointer p-1.5 text-app-text-leise transition-colors hover:text-app-gefahr"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        <div>
          <Button
            variante="sekundaer"
            icon={Plus}
            onClick={() => onAendern([...zeilen, spalten.map(() => "")])}
          >
            Zeile
          </Button>
        </div>
      </div>
    </div>
  );
}

/* ───────────────────────────── Fotos ───────────────────────────── */

function FotoFeld({
  titel,
  bericht,
  onGeaendert,
}: {
  titel: string;
  bericht: Projektbericht;
  onGeaendert: () => void | Promise<void>;
}) {
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  async function hochladen(dateien: FileList | null) {
    if (!dateien || dateien.length === 0) return;
    setLaeuft(true);
    setFehler(null);
    try {
      await api.projektberichte.fotosHochladen(bericht.id, Array.from(dateien));
      await onGeaendert();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Hochladen fehlgeschlagen.");
    } finally {
      setLaeuft(false);
    }
  }

  async function beschriften(fotoId: number, text: string) {
    try {
      await api.projektberichte.fotoAendern(fotoId, { bildunterschrift: text });
      await onGeaendert();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Speichern fehlgeschlagen.");
    }
  }

  async function verschieben(index: number, richtung: -1 | 1) {
    const sortiert = [...bericht.fotos];
    const ziel = index + richtung;
    if (ziel < 0 || ziel >= sortiert.length) return;
    const a = sortiert[index];
    const b = sortiert[ziel];
    try {
      await api.projektberichte.fotoAendern(a.id, { reihenfolge: b.reihenfolge });
      await api.projektberichte.fotoAendern(b.id, { reihenfolge: a.reihenfolge });
      await onGeaendert();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Sortieren fehlgeschlagen.");
    }
  }

  async function entfernen(fotoId: number) {
    if (!window.confirm("Foto aus dem Bericht entfernen?")) return;
    try {
      await api.projektberichte.fotoLoeschen(fotoId);
      await onGeaendert();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Löschen fehlgeschlagen.");
    }
  }

  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2">
        <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-app-text-still">
          {titel}
        </span>
        <label className="ml-auto cursor-pointer text-[12px] text-app-akzent underline">
          <input
            type="file"
            accept="image/*,.heic,.heif,.avif,.tif,.tiff"
            multiple
            className="hidden"
            onChange={(e) => hochladen(e.target.files)}
          />
          {laeuft ? "Wird geladen…" : "Fotos hinzufügen"}
        </label>
      </div>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {bericht.fotos.length === 0 ? (
        <LeerHinweis>
          Noch keine Fotos. Ohne Fotos entfällt das Kapitel im Bericht.
        </LeerHinweis>
      ) : (
        <div className="flex flex-col gap-2">
          {bericht.fotos.map((foto, i) => (
            <div
              key={foto.id}
              className="flex items-start gap-2.5 rounded-app-sm border border-app-linie p-2"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={api.projektberichte.fotoUrl(foto.id)}
                alt={foto.bildunterschrift || "Berichtsfoto"}
                className="h-16 w-16 shrink-0 rounded-app-sm object-cover"
                loading="lazy"
              />
              <div className="min-w-0 flex-1">
                <Input
                  defaultValue={foto.bildunterschrift}
                  placeholder="Bildunterschrift"
                  onBlur={(e) => beschriften(foto.id, e.target.value)}
                />
                <div className="mt-1 flex items-center gap-1 text-[11px] text-app-text-leise">
                  <button
                    type="button"
                    onClick={() => verschieben(i, -1)}
                    disabled={i === 0}
                    className="cursor-pointer px-1 disabled:opacity-40"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    onClick={() => verschieben(i, 1)}
                    disabled={i === bericht.fotos.length - 1}
                    className="cursor-pointer px-1 disabled:opacity-40"
                  >
                    ↓
                  </button>
                  <span>Position {i + 1}</span>
                  <button
                    type="button"
                    onClick={() => entfernen(foto.id)}
                    aria-label="Foto entfernen"
                    className="ml-auto cursor-pointer p-1 transition-colors hover:text-app-gefahr"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
