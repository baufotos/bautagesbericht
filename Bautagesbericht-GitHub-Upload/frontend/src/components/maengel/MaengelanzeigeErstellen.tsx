"use client";

/**
 * Mängelanzeige erstellen — zwei Word-Dateien aus erfassten Mängeln.
 *
 * DER ABLAUF FOLGT DEM BÜRO
 * =========================
 * Firma wählen → Mängel ankreuzen → Termine prüfen → erzeugen. Alles andere
 * kommt aus den Stammdaten: Anschrift der Firma, Vergabeeinheit und das
 * Dokumentkürzel schlägt der Server vor (``/maengelanzeige/vorbelegung``), und
 * jedes Feld bleibt änderbar — Projektnamen folgen keiner Norm.
 *
 * ZWEI DATEIEN, NIE EINE
 * ======================
 * „Beide erzeugen“ lädt ein ZIP mit Anschreiben **und** Anlage. Die
 * Einzeldownloads darunter sind für den Nachschub, wenn eines davon schon
 * verschickt ist. Zusammengeführt wird nichts — so verschickt es das Büro
 * auch nicht.
 *
 * WAS DIE VORSCHAU LEISTET
 * ========================
 * Sie zeigt vor dem Erzeugen, welche Bereiche mit welchen Bildunterschriften
 * in der Anlage stehen, und nennt die Mängel, die **ohne Foto** sind und
 * deshalb fehlen würden. Diese Kontrolle ist der Grund für den Zwischenschritt:
 * Das Schreiben setzt eine Rechtsfrist, da will man vorher hinsehen.
 */

import {
  AlertTriangle,
  Building2,
  CalendarClock,
  Check,
  Eye,
  FileText,
  Images,
  Package,
  RefreshCw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { dateiSpeichern } from "@/lib/dateien";
import { heuteIso } from "@/lib/formate";
import type {
  Gewerk,
  MaengelanzeigeAnfrage,
  MaengelanzeigeSachbearbeiter,
  MaengelanzeigeVorbelegung,
  MaengelanzeigeVorschau,
  MangelListItem,
  Projekt,
} from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  LeerHinweis,
  Plakette,
} from "@/components/dashboard";
import { Button, Field, Input, Meldung, Select } from "@/components/ui";

/** Der Sachbearbeiter ändert sich nicht bei jedem Schreiben — also merken. */
const SPEICHER_SACHBEARBEITER = "hpp-maengelanzeige-sachbearbeiter";

const LEERER_SACHBEARBEITER: MaengelanzeigeSachbearbeiter = {
  name: "",
  funktion: "-Baumanagement-",
  zeichen: "",
  auftragsnummer: "",
  email: "",
};

function sachbearbeiterLesen(): MaengelanzeigeSachbearbeiter {
  if (typeof window === "undefined") return LEERER_SACHBEARBEITER;
  try {
    const roh = window.localStorage.getItem(SPEICHER_SACHBEARBEITER);
    if (!roh) return LEERER_SACHBEARBEITER;
    return { ...LEERER_SACHBEARBEITER, ...(JSON.parse(roh) as object) };
  } catch {
    return LEERER_SACHBEARBEITER;
  }
}

export function MaengelanzeigeErstellen({
  projekt,
  gewerke,
  maengel,
  laedt,
  onAnsicht,
}: {
  projekt: Projekt;
  gewerke: Gewerk[];
  maengel: MangelListItem[];
  laedt: boolean;
  onAnsicht: (ansicht: "maengel-uebersicht" | "stamm-firmen") => void;
}) {
  const [gewerkId, setGewerkId] = useState<number | null>(null);
  const [gewaehlt, setGewaehlt] = useState<number[]>([]);
  const [vorbelegung, setVorbelegung] = useState<MaengelanzeigeVorbelegung | null>(null);
  const [sachbearbeiter, setSachbearbeiter] = useState(LEERER_SACHBEARBEITER);
  const [anlagedatum, setAnlagedatum] = useState("");
  const [vorschau, setVorschau] = useState<MaengelanzeigeVorschau | null>(null);
  const [laeuft, setLaeuft] = useState<"" | "vorschau" | "beide" | "anschreiben" | "anlage">("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [erfolg, setErfolg] = useState<string | null>(null);

  useEffect(() => {
    setSachbearbeiter(sachbearbeiterLesen());
  }, []);

  /* ───────── Vorbelegung vom Server ───────── */

  const ladeVorbelegung = useCallback(
    async (fuerGewerk: number | null) => {
      setFehler(null);
      try {
        const daten = await api.maengelanzeige.vorbelegung(projekt.id, fuerGewerk);
        setVorbelegung(daten);
      } catch (err) {
        setFehler(err instanceof Error ? err.message : "Vorbelegung nicht ladbar.");
      }
    },
    [projekt.id]
  );

  useEffect(() => {
    setVorschau(null);
    void ladeVorbelegung(gewerkId);
  }, [gewerkId, ladeVorbelegung]);

  // Projektwechsel: Auswahl verwerfen, sonst schickt man Mängel eines anderen
  // Bauvorhabens an eine Firma.
  useEffect(() => {
    setGewerkId(null);
    setGewaehlt([]);
    setVorschau(null);
  }, [projekt.id]);

  /* ───────── Auswahlliste ───────── */

  const auswaehlbar = useMemo(() => {
    const passend = maengel.filter(
      (m) => gewerkId === null || m.gewerk_id === gewerkId
    );
    // Offene zuerst, erledigte darunter: Angemahnt wird, was offen ist.
    return [...passend].sort((a, b) => {
      if (a.ist_abgeschlossen !== b.ist_abgeschlossen) {
        return a.ist_abgeschlossen ? 1 : -1;
      }
      return a.nummer.localeCompare(b.nummer);
    });
  }, [maengel, gewerkId]);

  const mitFoto = auswaehlbar.filter((m) => m.anzahl_fotos > 0);

  function umschalten(id: number) {
    setVorschau(null);
    setGewaehlt((alt) =>
      alt.includes(id) ? alt.filter((x) => x !== id) : [...alt, id]
    );
  }

  function alleOffenenMitFoto() {
    setVorschau(null);
    setGewaehlt(
      auswaehlbar.filter((m) => !m.ist_abgeschlossen && m.anzahl_fotos > 0)
        .map((m) => m.id)
    );
  }

  /* ───────── Anfrage zusammenstellen ───────── */

  const fehlendeFelder = useMemo(() => {
    const fehlt: string[] = [];
    if (gewaehlt.length === 0) fehlt.push("mindestens ein Mangel");
    if (!vorbelegung) fehlt.push("Vorbelegung");
    else {
      if (!vorbelegung.projektbezeichnung.trim()) fehlt.push("Projektbezeichnung");
      if (!vorbelegung.vergabeeinheit.trim()) fehlt.push("Vergabeeinheit");
      if (!vorbelegung.dokumentkuerzel.trim()) fehlt.push("Dokumentkürzel");
      if (!vorbelegung.empfaenger.firma.trim()) fehlt.push("Empfänger: Firma");
      if (!vorbelegung.fristsetzungsdatum) fehlt.push("Fristsetzungsdatum");
    }
    if (!sachbearbeiter.name.trim()) fehlt.push("Sachbearbeiter: Name");
    return fehlt;
  }, [gewaehlt, vorbelegung, sachbearbeiter]);

  function anfrage(): MaengelanzeigeAnfrage | null {
    if (!vorbelegung) return null;
    return {
      projekt_id: projekt.id,
      gewerk_id: gewerkId,
      mangel_ids: gewaehlt,
      empfaenger: vorbelegung.empfaenger,
      sachbearbeiter,
      begehungsdatum: vorbelegung.begehungsdatum,
      briefdatum: vorbelegung.briefdatum,
      fristsetzungsdatum: vorbelegung.fristsetzungsdatum,
      anlagedatum: anlagedatum || null,
      projektbezeichnung: vorbelegung.projektbezeichnung,
      vergabeeinheit: vorbelegung.vergabeeinheit,
      dokumentkuerzel: vorbelegung.dokumentkuerzel,
    };
  }

  function meldeFehler(err: unknown, standard: string) {
    if (err instanceof ApiError && typeof err.detail === "string") setFehler(err.detail);
    else setFehler(err instanceof Error ? err.message : standard);
  }

  function merkeSachbearbeiter() {
    try {
      window.localStorage.setItem(
        SPEICHER_SACHBEARBEITER,
        JSON.stringify(sachbearbeiter)
      );
    } catch {
      /* privater Modus — dann gilt die Angabe nur für diese Sitzung */
    }
  }

  async function zeigeVorschau() {
    const daten = anfrage();
    if (!daten) return;
    setFehler(null);
    setErfolg(null);
    setLaeuft("vorschau");
    try {
      setVorschau(await api.maengelanzeige.vorschau(daten));
    } catch (err) {
      setVorschau(null);
      meldeFehler(err, "Vorschau fehlgeschlagen.");
    } finally {
      setLaeuft("");
    }
  }

  async function erzeuge(art: "beide" | "anschreiben" | "anlage") {
    const daten = anfrage();
    if (!daten) return;
    setFehler(null);
    setErfolg(null);
    setLaeuft(art);
    try {
      const { blob, dateiname } =
        art === "beide"
          ? await api.maengelanzeige.dokumente(daten)
          : await api.maengelanzeige.dokument(daten, art);
      dateiSpeichern(blob, dateiname || "maengelanzeige.zip");
      merkeSachbearbeiter();
      setErfolg(
        art === "beide"
          ? "Anschreiben und Anlage liegen als ZIP in den Downloads."
          : `${art === "anschreiben" ? "Anschreiben" : "Anlage"} heruntergeladen.`
      );
    } catch (err) {
      meldeFehler(err, "Erzeugen fehlgeschlagen.");
    } finally {
      setLaeuft("");
    }
  }

  /* ───────── Darstellung ───────── */

  const bereit = fehlendeFelder.length === 0 && laeuft === "";

  function setzeVorbelegung<K extends keyof MaengelanzeigeVorbelegung>(
    feld: K,
    wert: MaengelanzeigeVorbelegung[K]
  ) {
    setVorschau(null);
    setVorbelegung((alt) => (alt ? { ...alt, [feld]: wert } : alt));
  }

  function setzeEmpfaenger(feld: keyof MaengelanzeigeVorbelegung["empfaenger"], wert: string) {
    setVorschau(null);
    setVorbelegung((alt) =>
      alt ? { ...alt, empfaenger: { ...alt.empfaenger, [feld]: wert } } : alt
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}
      {erfolg && <Meldung art="erfolg">{erfolg}</Meldung>}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* ───── Firma und Mängelauswahl ───── */}
        <Karte className="xl:col-span-2">
          <KarteKopf
            titel="Firma und Mängel"
            unterzeile="Die angekreuzten Mängel kommen in die Anlage — in dieser Reihenfolge"
            icon={Building2}
            aktion={
              <Plakette art={gewaehlt.length > 0 ? "ok" : "neutral"}>
                {gewaehlt.length} gewählt
              </Plakette>
            }
          />
          <KarteInhalt className="flex flex-col gap-3">
            <Field
              label="Zuständige Firma / Vergabeeinheit"
              hinweis="Bestimmt Anschrift, Vergabeeinheit und Dokumentkürzel."
            >
              <Select
                value={gewerkId ?? ""}
                onChange={(e) =>
                  setGewerkId(e.target.value ? Number(e.target.value) : null)
                }
              >
                <option value="">— alle Mängel des Projekts —</option>
                {gewerke.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.anzeige_name || g.firma_name}
                  </option>
                ))}
              </Select>
            </Field>

            {gewerke.length === 0 && (
              <Meldung art="hinweis">
                Für dieses Projekt ist noch keine Firma hinterlegt. Ohne Firma
                fehlen Anschrift und Vergabeeinheit im Anschreiben —{" "}
                <button
                  type="button"
                  onClick={() => onAnsicht("stamm-firmen")}
                  className="cursor-pointer underline"
                >
                  Firmen pflegen
                </button>
                .
              </Meldung>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <Button variante="sekundaer" onClick={alleOffenenMitFoto}>
                Alle offenen mit Foto
              </Button>
              <Button
                variante="still"
                onClick={() => {
                  setGewaehlt([]);
                  setVorschau(null);
                }}
              >
                Auswahl leeren
              </Button>
              <span className="ml-auto text-[11.5px] text-app-text-still">
                {mitFoto.length} von {auswaehlbar.length} haben ein Foto
              </span>
            </div>

            {auswaehlbar.length === 0 ? (
              <LeerHinweis>
                {laedt
                  ? "Mängel werden geladen…"
                  : "Für diese Auswahl gibt es keine Mängel. Erst erfassen, dann anzeigen."}
              </LeerHinweis>
            ) : (
              <div className="max-h-[420px] overflow-y-auto rounded-app-sm border border-app-linie">
                {auswaehlbar.map((m) => {
                  const aktiv = gewaehlt.includes(m.id);
                  const ohneFoto = m.anzahl_fotos === 0;
                  return (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => umschalten(m.id)}
                      className={`flex w-full cursor-pointer items-start gap-2.5 border-b border-app-linie px-3 py-2 text-left last:border-b-0 transition-colors ${
                        aktiv ? "bg-app-akzent-sanft" : "hover:bg-app-flaeche-hoch"
                      }`}
                    >
                      <span
                        className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-[3px] border ${
                          aktiv
                            ? "border-app-akzent bg-app-akzent text-app-akzent-text"
                            : "border-app-linie-stark"
                        }`}
                      >
                        {aktiv && <Check size={11} strokeWidth={3} />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12.5px] text-app-text">
                          <span className="font-mono text-[11.5px] text-app-text-still">
                            {m.nummer}
                          </span>{" "}
                          {m.kurzbezeichnung}
                        </span>
                        <span className="mt-0.5 block truncate text-[11.5px] text-app-text-still">
                          {m.hinweis_ort || m.raumnummer || "ohne Ortsangabe"}
                          {" · "}
                          {m.anzahl_fotos} Foto(s)
                          {m.ist_abgeschlossen && " · erledigt"}
                        </span>
                      </span>
                      {ohneFoto && (
                        <span className="shrink-0">
                          <Plakette art="warn">ohne Foto</Plakette>
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}

            <p className="text-[11.5px] text-app-text-leise">
              Die Bereichsüberschriften der Anlage entstehen aus dem Ort am
              Mangel („Ostfassade“). Mängel ohne Foto bleiben außen vor — die
              Anlage belegt sonst nichts.
            </p>
          </KarteInhalt>
        </Karte>

        {/* ───── Termine und Kennungen ───── */}
        <Karte>
          <KarteKopf titel="Termine und Kennung" icon={CalendarClock} />
          <KarteInhalt className="flex flex-col gap-3">
            {!vorbelegung ? (
              <LeerHinweis>Vorschläge werden geladen…</LeerHinweis>
            ) : (
              <>
                <Field label="Begehung am">
                  <Input
                    type="date"
                    value={vorbelegung.begehungsdatum}
                    onChange={(e) => setzeVorbelegung("begehungsdatum", e.target.value)}
                  />
                </Field>
                <Field label="Briefdatum">
                  <Input
                    type="date"
                    value={vorbelegung.briefdatum}
                    onChange={(e) => setzeVorbelegung("briefdatum", e.target.value)}
                  />
                </Field>
                <Field
                  label="Frist bis"
                  hinweis="Vorschlag: die früheste am Mangel gesetzte Frist."
                >
                  <Input
                    type="date"
                    value={vorbelegung.fristsetzungsdatum}
                    onChange={(e) =>
                      setzeVorbelegung("fristsetzungsdatum", e.target.value)
                    }
                  />
                </Field>
                <Field
                  label="Stand der Anlage"
                  hinweis="Leer lassen: dann gilt das Begehungsdatum."
                >
                  <Input
                    type="date"
                    value={anlagedatum}
                    onChange={(e) => {
                      setAnlagedatum(e.target.value);
                      setVorschau(null);
                    }}
                  />
                </Field>
                <Field label="Projektbezeichnung (Betreff, Zeile 1)">
                  <Input
                    value={vorbelegung.projektbezeichnung}
                    onChange={(e) =>
                      setzeVorbelegung("projektbezeichnung", e.target.value)
                    }
                  />
                </Field>
                <Field label="Vergabeeinheit (Betreff, Zeile 2)">
                  <Input
                    value={vorbelegung.vergabeeinheit}
                    onChange={(e) => setzeVorbelegung("vergabeeinheit", e.target.value)}
                  />
                </Field>
                <div className="rounded-app-sm border border-app-linie bg-app-flaeche-still px-2.5 py-2 text-[11.5px] text-app-text-still">
                  Zeile 3 des Betreffs ist festgelegt:{" "}
                  <span className="text-app-text">{vorbelegung.betreff_dritte_zeile}</span>
                </div>
                <Field
                  label="Dokumentkürzel"
                  hinweis="Steht in der Fußzeile und im Dateinamen beider Dateien."
                >
                  <Input
                    value={vorbelegung.dokumentkuerzel}
                    onChange={(e) => setzeVorbelegung("dokumentkuerzel", e.target.value)}
                  />
                </Field>
              </>
            )}
          </KarteInhalt>
        </Karte>
      </div>

      {/* ───── Adressblock und Sachbearbeiter ───── */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Karte>
          <KarteKopf
            titel="Empfänger"
            unterzeile="Adressblock des Anschreibens"
            icon={FileText}
            aktion={
              <Button
                variante="still"
                icon={RefreshCw}
                onClick={() => ladeVorbelegung(gewerkId)}
              >
                Aus Stammdaten
              </Button>
            }
          />
          <KarteInhalt className="flex flex-col gap-3">
            {vorbelegung && (
              <>
                <Field label="Firma (Pflicht)">
                  <Input
                    value={vorbelegung.empfaenger.firma}
                    onChange={(e) => setzeEmpfaenger("firma", e.target.value)}
                  />
                </Field>
                <Field
                  label="Ansprechpartner"
                  hinweis="Wie im Adressfeld: „Herrn Hey“ — die Anrede entsteht daraus."
                >
                  <Input
                    value={vorbelegung.empfaenger.ansprechpartner}
                    onChange={(e) => setzeEmpfaenger("ansprechpartner", e.target.value)}
                    placeholder="Herrn Hey"
                  />
                </Field>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <Field label="Straße und Hausnummer">
                    <Input
                      value={vorbelegung.empfaenger.strasse_hausnummer}
                      onChange={(e) =>
                        setzeEmpfaenger("strasse_hausnummer", e.target.value)
                      }
                    />
                  </Field>
                  <Field label="PLZ und Ort">
                    <Input
                      value={vorbelegung.empfaenger.plz_ort}
                      onChange={(e) => setzeEmpfaenger("plz_ort", e.target.value)}
                    />
                  </Field>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <Field label="Versandart">
                    <Input
                      value={vorbelegung.empfaenger.versandart}
                      onChange={(e) => setzeEmpfaenger("versandart", e.target.value)}
                    />
                  </Field>
                  <Field label="E-Mail des Empfängers">
                    <Input
                      value={vorbelegung.empfaenger.email ?? ""}
                      onChange={(e) => setzeEmpfaenger("email", e.target.value)}
                      inputMode="email"
                    />
                  </Field>
                </div>
              </>
            )}
          </KarteInhalt>
        </Karte>

        <Karte>
          <KarteKopf
            titel="Sachbearbeiter"
            unterzeile="Datumszeile und Unterschrift — wird für das nächste Mal gemerkt"
            icon={Building2}
          />
          <KarteInhalt className="flex flex-col gap-3">
            <Field label="Name (Pflicht)">
              <Input
                value={sachbearbeiter.name}
                onChange={(e) =>
                  setSachbearbeiter({ ...sachbearbeiter, name: e.target.value })
                }
                placeholder="Steffen Buchholz"
              />
            </Field>
            <Field label="Funktion">
              <Input
                value={sachbearbeiter.funktion}
                onChange={(e) =>
                  setSachbearbeiter({ ...sachbearbeiter, funktion: e.target.value })
                }
              />
            </Field>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Zeichen">
                <Input
                  value={sachbearbeiter.zeichen}
                  onChange={(e) =>
                    setSachbearbeiter({ ...sachbearbeiter, zeichen: e.target.value })
                  }
                  placeholder="Ze: sb"
                />
              </Field>
              <Field label="Auftragsnummer">
                <Input
                  value={sachbearbeiter.auftragsnummer}
                  onChange={(e) =>
                    setSachbearbeiter({
                      ...sachbearbeiter,
                      auftragsnummer: e.target.value,
                    })
                  }
                  placeholder="T - 10"
                />
              </Field>
            </div>
            <Field label="E-Mail (steht in der Datumszeile)">
              <Input
                value={sachbearbeiter.email ?? ""}
                onChange={(e) =>
                  setSachbearbeiter({ ...sachbearbeiter, email: e.target.value })
                }
                inputMode="email"
                placeholder="vorname.name@hpp.com"
              />
            </Field>
          </KarteInhalt>
        </Karte>
      </div>

      {/* ───── Vorschau und Erzeugen ───── */}
      <Karte hervorgehoben>
        <KarteKopf
          titel="Dokumente"
          unterzeile="Anschreiben und Anlage — immer zwei getrennte Dateien"
          icon={Package}
        />
        <KarteInhalt className="flex flex-col gap-3">
          {fehlendeFelder.length > 0 && (
            <Meldung art="hinweis">
              <span className="flex items-start gap-2">
                <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                <span>Es fehlt noch: {fehlendeFelder.join(", ")}.</span>
              </span>
            </Meldung>
          )}

          {vorschau && (
            <div className="flex flex-col gap-2.5 rounded-app-sm border border-app-linie bg-app-flaeche-still px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-app-text-still">
                <span className="flex items-center gap-1.5">
                  <FileText size={13} />
                  <span className="font-mono text-[11.5px] break-all text-app-text">
                    {vorschau.dateiname_anschreiben}
                  </span>
                </span>
                <span className="flex items-center gap-1.5">
                  <Images size={13} />
                  <span className="font-mono text-[11.5px] break-all text-app-text">
                    {vorschau.dateiname_anlage}
                  </span>
                </span>
              </div>
              <div className="text-[12px] text-app-text-still">
                {vorschau.bereiche.length} Bereich(e) · {vorschau.anzahl_fotos} Foto(s)
                {" · Frist "}
                {vorschau.fristsetzungsdatum}
              </div>
              <div className="flex flex-col gap-1.5">
                {vorschau.bereiche.map((b, i) => (
                  <div key={`${b.bereich}-${i}`} className="text-[12px]">
                    <span className="font-semibold text-app-text">{b.bereich}</span>
                    <span className="text-app-text-still">
                      {" — "}
                      {b.beschreibungen.join(" · ")}
                    </span>
                  </div>
                ))}
              </div>
              {vorschau.hinweise.length > 0 && (
                <ul className="flex flex-col gap-1 border-t border-app-linie pt-2 text-[11.5px] text-app-warn">
                  {vorschau.hinweise.map((h) => (
                    <li key={h}>{h}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variante="sekundaer"
              icon={Eye}
              onClick={zeigeVorschau}
              disabled={!bereit}
            >
              {laeuft === "vorschau" ? "Wird geprüft…" : "Vorschau"}
            </Button>
            <Button icon={Package} onClick={() => erzeuge("beide")} disabled={!bereit}>
              {laeuft === "beide" ? "Wird erzeugt…" : "Beide erzeugen (ZIP)"}
            </Button>
            <Button
              variante="still"
              icon={FileText}
              onClick={() => erzeuge("anschreiben")}
              disabled={!bereit}
            >
              nur Anschreiben
            </Button>
            <Button
              variante="still"
              icon={Images}
              onClick={() => erzeuge("anlage")}
              disabled={!bereit}
            >
              nur Anlage
            </Button>
            <Button
              variante="still"
              className="ml-auto"
              onClick={() => onAnsicht("maengel-uebersicht")}
            >
              Zur Mängelübersicht
            </Button>
          </div>
        </KarteInhalt>
      </Karte>
    </div>
  );
}
