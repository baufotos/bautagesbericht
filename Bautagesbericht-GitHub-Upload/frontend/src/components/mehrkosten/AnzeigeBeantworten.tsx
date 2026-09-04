"use client";

/**
 * Anzeige einer Baufirma beantworten — hochladen, prüfen, Schreiben, Outlook.
 *
 * DER ABLAUF IST DER SCHREIBTISCH
 * ===============================
 * Auf dem Tisch liegt ein Schreiben einer Firma. Vier Schritte, in dieser
 * Reihenfolge, alle auf einer Seite untereinander:
 *
 *   1. Anzeige hochladen        PDF oder Word. Der Server liest sie aus.
 *   2. Angaben prüfen           Alles, was er gelesen hat — Feld für Feld
 *                               änderbar. Nichts geht ungesehen in den Brief.
 *   3. Stellungnahme schreiben  Das Infofeld. Wort für Wort so, wie es im
 *                               Schreiben stehen wird.
 *   4. Erzeugen und verschicken Word herunterladen, dann Outlook-Entwurf.
 *
 * NICHT NUR MEHRKOSTENANZEIGEN
 * ============================
 * Erkannt und beantwortet werden auch Behinderungsanzeigen, Behinderungs- und
 * Mehrkostenanzeigen, Bedenkenanmeldungen, Nachtragsangebote sowie
 * Stundenlohn- und Störungsanzeigen. Die erkannte Art steht im Betreff des
 * Briefs *und* im Betreff der E-Mail — deshalb ist sie ein eigenes,
 * änderbares Feld und keine verborgene Annahme.
 *
 * WARUM DIE VORSCHAU EIN EIGENER SCHRITT IST
 * ==========================================
 * Ein solches Schreiben wehrt Vergütungsansprüche ab. Was darin steht, zählt
 * später. Die Vorschau zeigt deshalb den vollständigen Brieftext, den
 * Adressblock, die Datumszeile und die fertige E-Mail — und sie kommt vom
 * Server, also aus denselben Funktionen, die auch das Dokument bauen. Eine
 * zweite Fassung des Textes im Browser wäre eine zweite Wahrheit.
 *
 * WARUM ZWEI KNÖPFE FÜR OUTLOOK
 * =============================
 * Der Entwurf als ``.eml`` ist der gute Weg: Empfänger, Betreff, Text und das
 * Schreiben im Anhang sind drin, es fehlt nur „Senden“. Das klassische
 * Outlook öffnet ihn als Entwurf. Das neue Outlook und die Browserfassung
 * können ``.eml`` nicht öffnen — dafür steht daneben der Notausgang über
 * ``mailto:``, bei dem man das Dokument selbst anhängt. Denselben Doppelweg
 * geht schon der Fotoversand (``FotosatzMailDialog``).
 */

import {
  AlertTriangle,
  Check,
  Eye,
  FileSignature,
  FileText,
  Mail,
  Paperclip,
  ListPlus,
  RefreshCw,
  Sparkles,
  Undo2,
  Upload,
  Wand2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { dateiSpeichern, mailtoAdresse } from "@/lib/dateien";
import type {
  AnzeigeAngaben,
  AnzeigeAntwortAnfrage,
  AnzeigeAntwortVorschau,
  AnzeigeBaustein,
  AnzeigeBausteinGruppe,
  AnzeigeEmpfaenger,
  AnzeigeHaltung,
  AnzeigeSachbearbeiter,
  AnzeigeVorbelegung,
  GelesenesSchreiben,
  Projekt,
} from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  LeerHinweis,
  Plakette,
} from "@/components/dashboard";
import {
  Button,
  Checkbox,
  Field,
  Input,
  LinkButton,
  Meldung,
  Select,
  Textarea,
  heuteIso,
} from "@/components/ui";

/** Der Sachbearbeiter ändert sich nicht bei jedem Schreiben — also merken. */
const SPEICHER_SACHBEARBEITER = "hpp-anzeige-sachbearbeiter";

const LEERER_EMPFAENGER: AnzeigeEmpfaenger = {
  firma: "",
  anrede: "",
  ansprechpartner: "",
  strasse: "",
  plz: "",
  ort: "",
  email: "",
};

const LEERER_SACHBEARBEITER: AnzeigeSachbearbeiter = {
  name: "",
  funktion: "-Baumanagement-",
  zeichen: "",
  durchwahl: "",
  email: "",
};

const LEERE_ANZEIGE: AnzeigeAngaben = {
  art: "Mehrkostenanzeige",
  nummer: "",
  kennung: "",
  datum: null,
  kurzbezeichnung: "",
  bauzeit: "",
};

/** Ohne Server-Antwort: die Arten, die das Büro am häufigsten bekommt. */
const ARTEN_NOTFALL = [
  "Mehrkostenanzeige",
  "Behinderungsanzeige",
  "Behinderungs- und Mehrkostenanzeige",
  "Bedenkenanmeldung",
  "Nachtragsangebot",
];

function sachbearbeiterLesen(): AnzeigeSachbearbeiter {
  if (typeof window === "undefined") return LEERER_SACHBEARBEITER;
  try {
    const roh = window.localStorage.getItem(SPEICHER_SACHBEARBEITER);
    if (!roh) return LEERER_SACHBEARBEITER;
    return { ...LEERER_SACHBEARBEITER, ...(JSON.parse(roh) as object) };
  } catch {
    return LEERER_SACHBEARBEITER;
  }
}

function meldung(fehler: unknown, ersatz: string): string {
  if (fehler instanceof ApiError || fehler instanceof Error) return fehler.message;
  return ersatz;
}

export function AnzeigeBeantworten({
  projekt,
  onAnsicht,
}: {
  projekt: Projekt | null;
  onAnsicht: (ansicht: "stamm-firmen" | "stamm-listen") => void;
}) {
  /* ───────── Zustand ───────── */

  const [vorbelegung, setVorbelegung] = useState<AnzeigeVorbelegung | null>(null);
  const [gelesene, setGelesene] = useState<GelesenesSchreiben[]>([]);
  const [aktiv, setAktiv] = useState(0);
  const [uploadFehler, setUploadFehler] = useState<string[]>([]);

  const [gewerkId, setGewerkId] = useState<number | null>(null);
  const [bearbeiterId, setBearbeiterId] = useState<number | null>(null);

  const [empfaenger, setEmpfaenger] = useState(LEERER_EMPFAENGER);
  const [sachbearbeiter, setSachbearbeiter] = useState(LEERER_SACHBEARBEITER);
  const [anzeige, setAnzeige] = useState(LEERE_ANZEIGE);
  const [projektzeile, setProjektzeile] = useState("");
  const [vergabeeinheit, setVergabeeinheit] = useState("");
  const [betreff, setBetreff] = useState("");
  const [briefdatum, setBriefdatum] = useState(heuteIso());
  const [stellungnahme, setStellungnahme] = useState("");
  // Die Stichpunkte, aus denen formuliert wurde — fuer die Ruecknahme.
  // Ohne sie waere ein Klick auf "Text formulieren" unumkehrbar, und wer
  // zehn Zeilen Stichworte getippt hat, will sie nicht verlieren.
  const [rohfassung, setRohfassung] = useState<string | null>(null);
  const [offeneFragen, setOffeneFragen] = useState<string[]>([]);
  const [gruppen, setGruppen] = useState<AnzeigeBausteinGruppe[]>([]);
  const [luecke, setLuecke] = useState("___");
  const [bausteineOffen, setBausteineOffen] = useState(false);
  const [einleitung, setEinleitung] = useState("");
  const [haltung, setHaltung] = useState<AnzeigeHaltung>("kenntnisnahme");
  const [schlusssatz, setSchlusssatz] = useState("");
  const [bauzeitAblehnen, setBauzeitAblehnen] = useState(false);
  const [anlagen, setAnlagen] = useState("");
  const [verteiler, setVerteiler] = useState("");
  const [dateikuerzel, setDateikuerzel] = useState("");

  const [vorschau, setVorschau] = useState<AnzeigeAntwortVorschau | null>(null);
  const [mailBetreff, setMailBetreff] = useState("");
  const [mailText, setMailText] = useState("");
  const [mailKopie, setMailKopie] = useState("");
  const [mailAnhang, setMailAnhang] = useState(true);

  const [laeuft, setLaeuft] = useState<
    "" | "upload" | "formulieren" | "glaetten" | "vorschau" | "docx"
    | "pdf" | "eml"
  >("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [erfolg, setErfolg] = useState<string | null>(null);

  const dateiwahl = useRef<HTMLInputElement>(null);
  const infofeld = useRef<HTMLTextAreaElement>(null);

  /* ───────── Vorbelegung aus den Stammdaten ───────── */

  const ladeVorbelegung = useCallback(async () => {
    try {
      const daten = await api.anzeigen.vorbelegung(
        projekt?.id ?? null,
        gewerkId,
        bearbeiterId
      );
      setVorbelegung(daten);
      if (daten.projektzeile) setProjektzeile((alt) => alt || daten.projektzeile);
      if (daten.dateikuerzel) setDateikuerzel((alt) => alt || daten.dateikuerzel);
      if (daten.vergabeeinheit) setVergabeeinheit(daten.vergabeeinheit);
      if (daten.empfaenger) {
        // Stammdaten füllen nur, was leer ist: Das ausgelesene Schreiben ist
        // näher an der Wirklichkeit als eine Adresse, die vor zwei Jahren
        // eingetragen wurde.
        setEmpfaenger((alt) => ({
          ...alt,
          firma: alt.firma || daten.empfaenger!.firma,
          ansprechpartner:
            alt.ansprechpartner || daten.empfaenger!.ansprechpartner,
          strasse: alt.strasse || daten.empfaenger!.strasse,
          plz: alt.plz || daten.empfaenger!.plz,
          ort: alt.ort || daten.empfaenger!.ort,
          email: alt.email || daten.empfaenger!.email,
        }));
      }
      if (daten.sachbearbeiter) {
        setSachbearbeiter((alt) => ({ ...alt, ...daten.sachbearbeiter! }));
      }
    } catch (err) {
      setFehler(meldung(err, "Vorbelegung nicht ladbar."));
    }
  }, [projekt?.id, gewerkId, bearbeiterId]);

  useEffect(() => {
    void ladeVorbelegung();
  }, [ladeVorbelegung]);

  // Die Bausteine haengen an der Haltung: Wer ablehnt, soll "Dies ist eine
  // Zusatzleistung" gar nicht angeboten bekommen.
  useEffect(() => {
    let verworfen = false;
    api.anzeigen
      .bausteine(haltung)
      .then((daten) => {
        if (verworfen) return;
        setGruppen(daten.gruppen);
        setLuecke(daten.luecke);
      })
      .catch(() => {
        // Kein Grund zu stoeren — das Infofeld funktioniert auch ohne Liste.
        if (!verworfen) setGruppen([]);
      });
    return () => {
      verworfen = true;
    };
  }, [haltung]);

  useEffect(() => {
    const gemerkt = sachbearbeiterLesen();
    if (gemerkt.name) setSachbearbeiter(gemerkt);
  }, []);

  useEffect(() => {
    if (!sachbearbeiter.name) return;
    try {
      window.localStorage.setItem(
        SPEICHER_SACHBEARBEITER,
        JSON.stringify(sachbearbeiter)
      );
    } catch {
      /* Privates Fenster oder voller Speicher — kein Grund zu stören. */
    }
  }, [sachbearbeiter]);

  /* ───────── Ausgelesenes Schreiben ins Formular ───────── */

  const uebernehmen = useCallback((s: GelesenesSchreiben) => {
    setEmpfaenger({
      firma: s.absender.firma,
      anrede: "",
      ansprechpartner: s.ansprechpartner,
      strasse: s.absender.strasse,
      plz: s.absender.plz,
      ort: s.absender.ort,
      email: s.ansprechpartner_email || s.absender_email,
    });
    setAnzeige({
      art: s.art || "Mehrkostenanzeige",
      nummer: s.nummer,
      kennung: s.kennung,
      datum: s.datum,
      kurzbezeichnung: s.kurzbezeichnung,
      bauzeit: s.bauzeit,
    });
    setBetreff("");
    setBauzeitAblehnen(Boolean(s.bauzeit));
    if (s.empfaenger.firma && s.empfaenger.firma !== s.absender.firma) {
      // Wen die Firma angeschrieben hat, ist der Bauherr — der gehört in den
      // Verteiler, nicht ins Adressfeld.
      setVerteiler((alt) => alt || s.empfaenger.firma);
    }
    if (s.punkte.length > 0) {
      // Das Gerüst für die Stellungnahme: Zu jedem Punkt der Firma eine
      // Zeile, die noch zu füllen ist. So beantwortet das Büro sie in den
      // Referenzschreiben auch — Punkt für Punkt.
      setStellungnahme((alt) =>
        alt ||
        s.punkte.map((p) => `${p.nummer}) ${p.titel} — `).join("\n")
      );
    }
    setVorschau(null);
    setRohfassung(null);
    setOffeneFragen([]);
  }, []);

  /* ───────── Hochladen ───────── */

  async function hochladen(dateien: FileList | null) {
    if (!dateien || dateien.length === 0) return;
    setLaeuft("upload");
    setFehler(null);
    setErfolg(null);
    try {
      const ergebnis = await api.anzeigen.auslesen(Array.from(dateien));
      setGelesene(ergebnis.schreiben);
      setUploadFehler(ergebnis.fehlgeschlagen);
      setAktiv(0);
      if (ergebnis.schreiben.length > 0) {
        uebernehmen(ergebnis.schreiben[0]);
        setErfolg(
          ergebnis.schreiben.length === 1
            ? "Schreiben ausgelesen. Bitte die Angaben unten prüfen."
            : `${ergebnis.schreiben.length} Schreiben ausgelesen. ` +
              `Bearbeitet wird das oben ausgewählte.`
        );
      }
    } catch (err) {
      setFehler(meldung(err, "Die Datei konnte nicht gelesen werden."));
    } finally {
      setLaeuft("");
      if (dateiwahl.current) dateiwahl.current.value = "";
    }
  }

  /* ───────── Anfrage zusammenstellen ───────── */

  const anfrage = useMemo<AnzeigeAntwortAnfrage>(
    () => ({
      empfaenger,
      sachbearbeiter,
      anzeige,
      projektzeile,
      vergabeeinheit,
      betreff,
      briefdatum: briefdatum || null,
      stellungnahme,
      einleitung,
      haltung,
      schlusssatz,
      bauzeit_ablehnen: bauzeitAblehnen,
      anlagen,
      verteiler,
      dateikuerzel,
    }),
    [
      empfaenger,
      sachbearbeiter,
      anzeige,
      projektzeile,
      vergabeeinheit,
      betreff,
      briefdatum,
      stellungnahme,
      einleitung,
      haltung,
      schlusssatz,
      bauzeitAblehnen,
      anlagen,
      verteiler,
      dateikuerzel,
    ]
  );

  /* ───────── Bausteine und Glätten (ohne Schlüssel) ───────── */

  /**
   * Einen Baustein an der Schreibmarke einsetzen.
   *
   * An der Schreibmarke und nicht am Ende: Wer zu Punkt 2 einen Satz braucht,
   * will ihn bei Punkt 2 haben. Steht die Marke nirgends (das Feld war nie
   * angeklickt), wird angehängt.
   */
  function setzeBaustein(baustein: AnzeigeBaustein) {
    const feld = infofeld.current;
    const satz = baustein.text;
    const alt = stellungnahme;

    let neuerText: string;
    let marke: number;
    if (feld && feld.selectionStart !== null) {
      const vor = alt.slice(0, feld.selectionStart);
      const nach = alt.slice(feld.selectionEnd ?? feld.selectionStart);
      const trenner = vor && !vor.endsWith("\n") ? "\n" : "";
      neuerText = `${vor}${trenner}${satz}${nach}`;
      marke = vor.length + trenner.length + satz.length;
    } else {
      const trenner = alt && !alt.endsWith("\n") ? "\n" : "";
      neuerText = `${alt}${trenner}${satz}`;
      marke = neuerText.length;
    }

    setStellungnahme(neuerText);
    setVorschau(null);
    // Die erste Lücke ansteuern — dort muss der Mensch weiterschreiben.
    const stelle = neuerText.indexOf(luecke, marke - satz.length);
    window.setTimeout(() => {
      if (!feld) return;
      feld.focus();
      if (stelle >= 0) feld.setSelectionRange(stelle, stelle + luecke.length);
      else feld.setSelectionRange(marke, marke);
    }, 0);
  }

  async function glaetteText() {
    setLaeuft("glaetten");
    setFehler(null);
    setErfolg(null);
    const vorher = stellungnahme;
    try {
      const ergebnis = await api.anzeigen.glaetten(stellungnahme);
      setRohfassung(vorher);
      setStellungnahme(ergebnis.text);
      setOffeneFragen(ergebnis.hinweise);
      setVorschau(null);
      setErfolg(
        "Geglättet: Aufzählung, Abkürzungen und Satzzeichen. Der Inhalt ist " +
          "unverändert."
      );
    } catch (err) {
      setFehler(meldung(err, "Glätten war nicht möglich."));
    } finally {
      setLaeuft("");
    }
  }

  /* ───────── Stichpunkte ausformulieren ───────── */

  async function formuliereText() {
    setLaeuft("formulieren");
    setFehler(null);
    setErfolg(null);
    const vorher = stellungnahme;
    try {
      const ergebnis = await api.anzeigen.formulieren({
        stichpunkte: stellungnahme,
        anzeige,
        // Die Punkte und der Volltext der Anzeige sind die Tatsachengrundlage.
        // Ohne sie muesste das Modell raten, worauf sich die Stichpunkte
        // beziehen — und genau das soll es nicht.
        punkte: gelesenesAktiv
          ? gelesenesAktiv.punkte.map((p) => `${p.nummer}. ${p.titel}`)
          : [],
        lv_positionen: gelesenesAktiv?.lv_positionen ?? [],
        rechtsgrundlage: gelesenesAktiv?.rechtsgrundlage ?? "",
        anzeigetext: gelesenesAktiv?.volltext ?? "",
        haltung,
        projektzeile,
        vergabeeinheit,
      });
      setRohfassung(vorher);
      setStellungnahme(ergebnis.stellungnahme);
      setOffeneFragen(ergebnis.offene_fragen);
      setVorschau(null);
      setErfolg(
        ergebnis.offene_fragen.length > 0
          ? "Text formuliert. Bitte gegenlesen — zu den Punkten unten fehlten " +
            "Angaben, sie stehen nicht im Text."
          : "Text formuliert. Bitte gegenlesen und ändern, was nicht passt."
      );
    } catch (err) {
      setFehler(meldung(err, "Formulieren war nicht möglich."));
    } finally {
      setLaeuft("");
    }
  }

  function nimmZurueck() {
    if (rohfassung === null) return;
    setStellungnahme(rohfassung);
    setRohfassung(null);
    setOffeneFragen([]);
    setVorschau(null);
  }

  async function zeigeVorschau() {
    setLaeuft("vorschau");
    setFehler(null);
    setErfolg(null);
    try {
      const gesehen = await api.anzeigen.vorschau(anfrage);
      setVorschau(gesehen);
      setMailBetreff(gesehen.mail_betreff);
      setMailText(gesehen.mail_text);
    } catch (err) {
      setVorschau(null);
      setFehler(meldung(err, "Vorschau nicht möglich."));
    } finally {
      setLaeuft("");
    }
  }

  async function holeDokument(format: "docx" | "pdf") {
    setLaeuft(format);
    setFehler(null);
    setErfolg(null);
    try {
      const { blob, dateiname } = await api.anzeigen.dokument(anfrage, format);
      dateiSpeichern(blob, dateiname || `anzeige.${format}`);
      setErfolg(
        `${dateiname} gespeichert. Bitte gegenlesen — danach der ` +
          `Outlook-Entwurf darunter.`
      );
    } catch (err) {
      setFehler(meldung(err, "Das Schreiben konnte nicht erzeugt werden."));
    } finally {
      setLaeuft("");
    }
  }

  async function holeEntwurf() {
    setLaeuft("eml");
    setFehler(null);
    setErfolg(null);
    try {
      const { blob, dateiname } = await api.anzeigen.mailEntwurf({
        antwort: anfrage,
        kopie: mailKopie
          .split(/[;,]/)
          .map((a) => a.trim())
          .filter(Boolean),
        betreff: mailBetreff,
        text: mailText,
        dokument_anhaengen: mailAnhang,
      });
      dateiSpeichern(blob, dateiname || "anzeige.eml");
      setErfolg(
        "Entwurf gespeichert. Die .eml-Datei öffnen — Outlook zeigt sie als " +
          "fertige Mail. Nur noch das Schreiben gegenlesen und senden."
      );
    } catch (err) {
      setFehler(meldung(err, "Der Outlook-Entwurf konnte nicht erzeugt werden."));
    } finally {
      setLaeuft("");
    }
  }

  /* ───────── Ableitungen ───────── */

  const arten = vorbelegung?.arten?.length ? vorbelegung.arten : ARTEN_NOTFALL;
  const haltungen = vorbelegung?.haltungen ?? {
    ablehnung: "Ablehnung",
    teilweise: "Teilweise Anerkennung",
    pruefung: "In Prüfung",
    anerkennung: "Anerkennung",
    kenntnisnahme: "Nur Kenntnisnahme",
  };
  const gelesenesAktiv = gelesene[aktiv];
  const mailAn = empfaenger.email.trim();

  return (
    <div className="space-y-4">
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}
      {erfolg && <Meldung art="erfolg">{erfolg}</Meldung>}

      {/* ─────────── 1. Hochladen ─────────── */}

      <Karte>
        <KarteKopf
          titel="1 · Anzeige hochladen"
          unterzeile="PDF oder Word. Mehrere Dateien auf einmal sind möglich."
        />
        <KarteInhalt className="space-y-3">
          <input
            ref={dateiwahl}
            type="file"
            multiple
            accept=".pdf,.docx,.docm,.dotx,.txt"
            onChange={(e) => void hochladen(e.target.files)}
            className="hidden"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              icon={Upload}
              onClick={() => dateiwahl.current?.click()}
              disabled={laeuft !== ""}
            >
              {laeuft === "upload" ? "Wird gelesen…" : "Dateien wählen"}
            </Button>
            <span className="text-[12.5px] text-ui-text-muted">
              Mehrkosten- und Behinderungsanzeigen, Nachträge, Bedenken —
              die Art erkennt die App selbst.
            </span>
          </div>

          {uploadFehler.length > 0 && (
            <Meldung art="hinweis">
              <span className="flex items-start gap-2">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <span>
                  Nicht gelesen:
                  <ul className="mt-1 list-disc pl-4">
                    {uploadFehler.map((z) => (
                      <li key={z}>{z}</li>
                    ))}
                  </ul>
                </span>
              </span>
            </Meldung>
          )}

          {gelesene.length > 1 && (
            <div className="flex flex-wrap gap-2">
              {gelesene.map((s, nr) => (
                <button
                  key={s.quelle + nr}
                  type="button"
                  onClick={() => {
                    setAktiv(nr);
                    uebernehmen(s);
                  }}
                  className={`cursor-pointer rounded-full border px-3 py-1.5 text-[12.5px] ${
                    nr === aktiv
                      ? "border-ui-accent bg-ui-accent-soft text-ui-accent"
                      : "border-ui-line text-ui-text-muted hover:border-ui-line-strong"
                  }`}
                >
                  {s.kennung || s.art || s.quelle}
                </button>
              ))}
            </div>
          )}

          {gelesenesAktiv && (
            <AusgelesenesFeld
              schreiben={gelesenesAktiv}
              onErneutUebernehmen={() => uebernehmen(gelesenesAktiv)}
            />
          )}
        </KarteInhalt>
      </Karte>

      {/* ─────────── 2. Angaben ─────────── */}

      <Karte>
        <KarteKopf
          titel="2 · Angaben prüfen"
          unterzeile="Alles änderbar. Was hier steht, steht später im Schreiben."
        />
        <KarteInhalt className="space-y-5">
          {/* Stammdaten als Abkürzung */}
          {(vorbelegung?.gewerke.length || vorbelegung?.bearbeiter.length) ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {vorbelegung && vorbelegung.gewerke.length > 0 && (
                <Field
                  label="Firma aus den Stammdaten"
                  hinweis="Füllt nur leere Felder — das Schreiben hat Vorrang."
                >
                  <Select
                    value={gewerkId ?? ""}
                    onChange={(e) =>
                      setGewerkId(e.target.value ? Number(e.target.value) : null)
                    }
                  >
                    <option value="">— keine —</option>
                    {vorbelegung.gewerke.map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.firma_name}
                        {g.vergabeeinheit_code ? ` · ${g.vergabeeinheit_code}` : ""}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {vorbelegung && vorbelegung.bearbeiter.length > 0 && (
                <Field
                  label="Unterzeichner aus den Stammdaten"
                  hinweis="Kürzel, Durchwahl und Mailadresse kommen mit."
                >
                  <Select
                    value={bearbeiterId ?? ""}
                    onChange={(e) =>
                      setBearbeiterId(
                        e.target.value ? Number(e.target.value) : null
                      )
                    }
                  >
                    <option value="">— keiner —</option>
                    {vorbelegung.bearbeiter.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                        {b.kuerzel ? ` (${b.kuerzel})` : ""}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
            </div>
          ) : null}

          <Abschnitt titel="Die Anzeige">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="Art der Anzeige">
                <Select
                  value={anzeige.art}
                  onChange={(e) =>
                    setAnzeige({ ...anzeige, art: e.target.value })
                  }
                >
                  {[...new Set([anzeige.art, ...arten])]
                    .filter(Boolean)
                    .map((a) => (
                      <option key={a} value={a}>
                        {a}
                      </option>
                    ))}
                </Select>
              </Field>
              <Field label="Nummer" hinweis="Wie im Schreiben: 01, nicht 1.">
                <Input
                  value={anzeige.nummer}
                  onChange={(e) =>
                    setAnzeige({ ...anzeige, nummer: e.target.value })
                  }
                  placeholder="03"
                />
              </Field>
              <Field label="Kennung" hinweis="Für den Dateinamen: MKA 03, BEH 01.">
                <Input
                  value={anzeige.kennung}
                  onChange={(e) =>
                    setAnzeige({ ...anzeige, kennung: e.target.value })
                  }
                  placeholder="MKA 03"
                />
              </Field>
              <Field label="Datum des Schreibens">
                <Input
                  type="date"
                  value={anzeige.datum ?? ""}
                  onChange={(e) =>
                    setAnzeige({ ...anzeige, datum: e.target.value || null })
                  }
                />
              </Field>
            </div>
            <Field
              label="Sachverhalt"
              hinweis="Steht hinter dem Gedankenstrich im Betreff."
            >
              <Input
                value={anzeige.kurzbezeichnung}
                onChange={(e) =>
                  setAnzeige({ ...anzeige, kurzbezeichnung: e.target.value })
                }
                placeholder="Zusätzlicher Rückbauaufwand aufgrund abweichender Bodenaufbauten"
              />
            </Field>
          </Abschnitt>

          <Abschnitt titel="Adressfeld — die Firma, die geschrieben hat">
            <Field
              label="Firma"
              hinweis={
                gelesenesAktiv &&
                gelesenesAktiv.empfaenger.firma &&
                gelesenesAktiv.empfaenger.firma !== empfaenger.firma
                  ? `Im Schreiben angeschrieben war „${gelesenesAktiv.empfaenger.firma}“ — das ist der Bauherr und gehört in den Verteiler.`
                  : undefined
              }
            >
              <Input
                value={empfaenger.firma}
                onChange={(e) =>
                  setEmpfaenger({ ...empfaenger, firma: e.target.value })
                }
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field
                label="Anrede"
                hinweis="Leer = „Sehr geehrte Damen und Herren“."
              >
                <Select
                  value={empfaenger.anrede}
                  onChange={(e) =>
                    setEmpfaenger({
                      ...empfaenger,
                      anrede: e.target.value as AnzeigeEmpfaenger["anrede"],
                    })
                  }
                >
                  <option value="">— neutral —</option>
                  <option value="Herr">Herr</option>
                  <option value="Frau">Frau</option>
                </Select>
              </Field>
              <Field label="Ansprechpartner" className="sm:col-span-2">
                <Input
                  value={empfaenger.ansprechpartner}
                  onChange={(e) =>
                    setEmpfaenger({
                      ...empfaenger,
                      ansprechpartner: e.target.value,
                    })
                  }
                />
              </Field>
            </div>
            <div className="grid gap-3 sm:grid-cols-4">
              <Field label="Straße und Nr." className="sm:col-span-2">
                <Input
                  value={empfaenger.strasse}
                  onChange={(e) =>
                    setEmpfaenger({ ...empfaenger, strasse: e.target.value })
                  }
                />
              </Field>
              <Field label="PLZ">
                <Input
                  value={empfaenger.plz}
                  onChange={(e) =>
                    setEmpfaenger({ ...empfaenger, plz: e.target.value })
                  }
                />
              </Field>
              <Field label="Ort">
                <Input
                  value={empfaenger.ort}
                  onChange={(e) =>
                    setEmpfaenger({ ...empfaenger, ort: e.target.value })
                  }
                />
              </Field>
            </div>
            <Field
              label="E-Mail der Firma"
              hinweis="Steht im Adressfeld unter „per E-Mail:“ und ist der Empfänger des Outlook-Entwurfs."
            >
              <Input
                type="email"
                value={empfaenger.email}
                onChange={(e) =>
                  setEmpfaenger({ ...empfaenger, email: e.target.value })
                }
              />
            </Field>
          </Abschnitt>

          <Abschnitt titel="Projekt und Betreff">
            <Field
              label="Projektzeile (fett, erste Zeile)"
              hinweis="Im Büro „Nummer_Name“ — der Name davon wird der Mailbetreff."
            >
              <Input
                value={projektzeile}
                onChange={(e) => setProjektzeile(e.target.value)}
                placeholder="G.100-DESYUM_Neubau Besucherzentrum DESY"
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Vergabeeinheit (zweite Zeile)" className="sm:col-span-2">
                <Input
                  value={vergabeeinheit}
                  onChange={(e) => setVergabeeinheit(e.target.value)}
                  placeholder="VE300.01- Erweiterter Rohbau"
                />
              </Field>
              <Field
                label="Kürzel für den Dateinamen"
                hinweis="Wird zu „260903 Kürzel-VE-Kennung.docx“."
              >
                <Input
                  value={dateikuerzel}
                  onChange={(e) => setDateikuerzel(e.target.value)}
                  placeholder="G.100-DESYUM"
                />
              </Field>
            </div>
            <Field
              label="Betreff (dritte Zeile)"
              hinweis="Leer lassen: dann aus Art, Nummer, Datum und Sachverhalt gebildet."
            >
              <Input
                value={betreff}
                onChange={(e) => setBetreff(e.target.value)}
                placeholder="wird aus der Anzeige gebildet"
              />
            </Field>
          </Abschnitt>

          <Abschnitt titel="Unterzeichner und Datum">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="Name">
                <Input
                  value={sachbearbeiter.name}
                  onChange={(e) =>
                    setSachbearbeiter({ ...sachbearbeiter, name: e.target.value })
                  }
                />
              </Field>
              <Field label="Funktion">
                <Input
                  value={sachbearbeiter.funktion}
                  onChange={(e) =>
                    setSachbearbeiter({
                      ...sachbearbeiter,
                      funktion: e.target.value,
                    })
                  }
                  placeholder="-Baumanagement-"
                />
              </Field>
              <Field label="Kürzel (Ze:)">
                <Input
                  value={sachbearbeiter.zeichen}
                  onChange={(e) =>
                    setSachbearbeiter({
                      ...sachbearbeiter,
                      zeichen: e.target.value,
                    })
                  }
                  placeholder="gg"
                />
              </Field>
              <Field label="Durchwahl (T -)">
                <Input
                  value={sachbearbeiter.durchwahl}
                  onChange={(e) =>
                    setSachbearbeiter({
                      ...sachbearbeiter,
                      durchwahl: e.target.value,
                    })
                  }
                  placeholder="25"
                />
              </Field>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="E-Mail (HPP)">
                <Input
                  type="email"
                  value={sachbearbeiter.email}
                  onChange={(e) =>
                    setSachbearbeiter({ ...sachbearbeiter, email: e.target.value })
                  }
                  placeholder="vorname.name@hpp.com"
                />
              </Field>
              <Field label="Datum des Schreibens">
                <Input
                  type="date"
                  value={briefdatum}
                  onChange={(e) => setBriefdatum(e.target.value)}
                />
              </Field>
            </div>
          </Abschnitt>
        </KarteInhalt>
      </Karte>

      {/* ─────────── 3. Stellungnahme ─────────── */}

      <Karte>
        <KarteKopf
          titel="3 · Stellungnahme"
          unterzeile="Der Text kommt Wort für Wort in den Brief — nichts wird umformuliert."
        />
        <KarteInhalt className="space-y-4">
          {/* ── Stichpunkte ausformulieren ──
              Der Knopf schreibt in dasselbe Feld: Erst stehen dort die
              Stichworte, danach der Brieftext. Beides ist derselbe Weg ins
              Dokument, und dazwischen liest ein Mensch. */}
          <div className="flex flex-wrap items-center gap-2">
            {gruppen.length > 0 && (
              <Button
                variante="sekundaer"
                icon={ListPlus}
                onClick={() => setBausteineOffen((offen) => !offen)}
              >
                {bausteineOffen ? "Bausteine schließen" : "Textbausteine"}
              </Button>
            )}
            <Button
              variante="sekundaer"
              icon={laeuft === "glaetten" ? RefreshCw : Sparkles}
              onClick={() => void glaetteText()}
              disabled={laeuft !== "" || !stellungnahme.trim()}
            >
              {laeuft === "glaetten" ? "Wird geglättet…" : "Stichworte glätten"}
            </Button>
            {rohfassung !== null && (
              <Button variante="still" icon={Undo2} onClick={nimmZurueck}>
                Zurück zur vorigen Fassung
              </Button>
            )}
            {vorbelegung?.formulieren_verfuegbar ? (
              <>
                <Button
                  variante="sekundaer"
                  icon={laeuft === "formulieren" ? RefreshCw : Wand2}
                  onClick={() => void formuliereText()}
                  disabled={laeuft !== "" || !stellungnahme.trim()}
                >
                  {laeuft === "formulieren"
                    ? "Wird formuliert…"
                    : "Stichpunkte ausformulieren"}
                </Button>
                <span className="text-[12.5px] text-ui-text-muted">
                  Hinschreiben, was hinein soll — Stichworte genügen. Daraus
                  wird der Brieftext im Stil des Büros.
                </span>
              </>
            ) : (
              <span className="text-[12.5px] text-ui-text-muted">
                Bausteine und Glätten brauchen keinen Schlüssel. Freies
                Ausformulieren aus Notizen schon —{" "}
                {vorbelegung?.formulieren_hinweis ||
                  "der Schlüssel fehlt derzeit."}
              </span>
            )}
          </div>

          {offeneFragen.length > 0 && (
            <Meldung art="hinweis">
              <span className="flex items-start gap-2">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <span>
                  Bitte noch von Hand nachsehen:
                  <ul className="mt-1 list-disc pl-4">
                    {offeneFragen.map((f) => (
                      <li key={f}>{f}</li>
                    ))}
                  </ul>
                </span>
              </span>
            </Meldung>
          )}

          {bausteineOffen && gruppen.length > 0 && (
            <div className="space-y-3 rounded-ui border border-ui-line bg-ui-surface-muted p-3.5">
              <p className="text-[12.5px] text-ui-text-muted">
                Die Standardsätze des Büros — angeklickt landen sie an der
                Schreibmarke im Infofeld. Steht „{luecke}“ darin, springt der
                Zeiger gleich dorthin.
              </p>
              {gruppen.map((gruppe) => (
                <div key={gruppe.kennung}>
                  <p className="font-mono text-[10px] tracking-[0.08em] uppercase text-ui-text-faint">
                    {gruppe.titel}
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {gruppe.bausteine.map((baustein) => (
                      <button
                        key={baustein.kennung}
                        type="button"
                        title={baustein.text}
                        onClick={() => setzeBaustein(baustein)}
                        className="cursor-pointer rounded-full border border-ui-line bg-ui-surface px-2.5 py-1 text-[12px] text-ui-text hover:border-ui-line-strong"
                      >
                        {baustein.titel}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          <Field
            label={
              rohfassung === null
                ? "Infofeld: was HPP zu der Anzeige sagt"
                : "Infofeld: der formulierte Brieftext — bitte gegenlesen"
            }
            hinweis={
              "Leerzeile = neuer Absatz. „1) …“ bleibt eine eigene Zeile. " +
              "Eine Zeile „Auszug LV:“ rückt alles Folgende ein, bis zur nächsten Leerzeile."
            }
          >
            <Textarea
              ref={infofeld}
              value={stellungnahme}
              onChange={(e) => setStellungnahme(e.target.value)}
              rows={12}
              className="min-h-[240px] font-mono text-[13px]"
              placeholder={
                "Wir sehen hier keinen Mehrvergütungsanspruch. In der Ausschreibung " +
                "bzw. in Ihrem Auftrags-LV ist Ihr Vertragssoll dargelegt.\n\n" +
                "1) Doppelböden — Der Rückbau ist mit Pos. 03.0110 ausgeschrieben.\n" +
                "2) Mehrlagige Beläge — Die Bestandsschnitte lagen der Ausschreibung bei.\n\n" +
                "Auszug LV:\n" +
                "Bodenbeläge einschließlich Kleber und Unterlage sind vollständig\n" +
                "zurückzubauen. Mehrlagige Aufbauten sind einzukalkulieren."
              }
            />
          </Field>

          {/* Was man im Infofeld noch unterbringen kann, ohne nach oben zu
              springen. Als <details>, damit die Liste nicht dauernd Platz
              wegnimmt — gebraucht wird sie beim ersten Mal, danach weiss man es. */}
          <details className="rounded-ui border border-ui-line bg-ui-surface-muted px-3.5 py-2.5">
            <summary className="cursor-pointer text-[12.5px] text-ui-text">
              Angaben direkt im Infofeld — Anlage, Verteiler, Betreff und mehr
            </summary>
            <div className="mt-2 space-y-2 text-[12.5px] text-ui-text-muted">
              <p>
                Eine Zeile, die mit einer dieser Beschriftungen und einem
                Doppelpunkt beginnt, wird nicht Brieftext, sondern landet an
                ihrem Platz im Schreiben. Die Vorschau sagt danach, was
                übernommen wurde.
              </p>
              <pre className="overflow-x-auto rounded-ui-sm bg-ui-surface p-2.5 font-mono text-[11.5px] leading-relaxed text-ui-text">{`Anlage: Auszug LV Pos. 03.0110      → letzte Seite (mehrfach möglich)
Verteiler: SBH, Hr. Melms           → letzte Seite (mehrfach möglich)
Betreff: Ihre MKA Nr. 03            → fette Betreffzeile
Projekt: BOB_Boulevard Berlin       → fette Projektzeile
VE: VE100- Abbrucharbeiten          → zweite fette Zeile
Haltung: ablehnen                   → Schlusssatz
Datum: 03.09.2026                   → Datumszeile und Dateiname
Firma / Anrede / Ansprechpartner    → Adressfeld
Straße / PLZ Ort                    → Adressfeld
Mail: name@firma.de                 → Adressfeld, Empfänger der Mail
Unterzeichner / Funktion            → Unterschriftsblock
Zeichen: kb   Durchwahl: 22         → Datumszeile
E-Mail HPP: w29@hpp.com             → Datumszeile
Kürzel: BOB                         → Dateiname
Bauzeit ablehnen                    → weist die Bauzeitverlängerung zurück`}</pre>
              <p>
                Ein gewöhnlicher Satz bleibt Brieftext, auch wenn er dieselben
                Wörter enthält: „Die Anlage 3 haben wir geprüft." steht im
                Brief, weil der Doppelpunkt fehlt.
              </p>
            </div>
          </details>

          {gelesenesAktiv && gelesenesAktiv.punkte.length > 0 && (
            <div className="rounded-ui bg-ui-surface-muted px-3.5 py-3">
              <p className="text-[12px] font-medium text-ui-text-muted">
                Die Punkte der Firma — Vorlage für die Antwort:
              </p>
              <ol className="mt-1.5 space-y-1 text-[13px] text-ui-text">
                {gelesenesAktiv.punkte.map((p) => (
                  <li key={p.nummer}>
                    <span className="text-ui-text-muted">{p.nummer})</span>{" "}
                    {p.titel}
                  </li>
                ))}
              </ol>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              label="Haltung"
              hinweis="Bestimmt den Schlusssatz des Briefs."
            >
              <Select
                value={haltung}
                onChange={(e) => setHaltung(e.target.value as AnzeigeHaltung)}
              >
                {Object.entries(haltungen).map(([schluessel, text]) => (
                  <option key={schluessel} value={schluessel}>
                    {text}
                  </option>
                ))}
              </Select>
            </Field>
            <Field
              label="Eigener Schlusssatz"
              hinweis="Leer = Standardsatz zur gewählten Haltung."
            >
              <Input
                value={schlusssatz}
                onChange={(e) => setSchlusssatz(e.target.value)}
                placeholder="Wir bitten um Kenntnisnahme."
              />
            </Field>
          </div>

          <Field
            label="Eigene Einleitung"
            hinweis="Leer = „wir haben Ihre … erhalten und nehmen hierzu wie folgt Stellung:“"
          >
            <Input
              value={einleitung}
              onChange={(e) => setEinleitung(e.target.value)}
              placeholder="wird aus der Anzeige gebildet"
            />
          </Field>

          {anzeige.bauzeit && (
            <div className="space-y-1.5">
              <Checkbox
                checked={bauzeitAblehnen}
                onChange={setBauzeitAblehnen}
                label="Bauzeitverlängerung ausdrücklich zurückweisen"
              />
              <p className="pl-7 text-[12px] text-ui-text-muted">
                Die Firma schreibt: „{anzeige.bauzeit}“
              </p>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Anlagen" hinweis="Eine Zeile je Anlage. Kommt auf die letzte Seite.">
              <Textarea
                value={anlagen}
                onChange={(e) => setAnlagen(e.target.value)}
                rows={3}
                placeholder={"Auszug LV Pos. 03.0110\nBestandsschnitt Ebene 0"}
              />
            </Field>
            <Field label="Verteiler" hinweis="Eine Zeile je Empfänger — Bauherr, HPP, Projektadressen.">
              <Textarea
                value={verteiler}
                onChange={(e) => setVerteiler(e.target.value)}
                rows={3}
                placeholder={"Bauherr, Frau Eschelbach\nHPP, Herr da Costa\nsowie Projektadressen"}
              />
            </Field>
          </div>
        </KarteInhalt>
      </Karte>

      {/* ─────────── 4. Vorschau, Dokument, Outlook ─────────── */}

      <Karte>
        <KarteKopf
          titel="4 · Prüfen und verschicken"
          unterzeile="Erst gegenlesen, dann erzeugen — das Schreiben wehrt Ansprüche ab."
          aktion={
            <Button
              variante="sekundaer"
              icon={laeuft === "vorschau" ? RefreshCw : Eye}
              onClick={() => void zeigeVorschau()}
              disabled={laeuft !== ""}
            >
              {laeuft === "vorschau" ? "Wird geprüft…" : "Vorschau"}
            </Button>
          }
        />
        <KarteInhalt className="space-y-4">
          {!vorschau ? (
            <LeerHinweis>
              Auf „Vorschau“ drücken. Dann steht hier der vollständige
              Brieftext, so wie er im Word-Dokument landet — samt Adressfeld,
              Datumszeile und fertiger E-Mail.
            </LeerHinweis>
          ) : (
            <>
              {vorschau.hinweise.length > 0 && (
                <Meldung art="hinweis">
                  <ul className="list-disc pl-4">
                    {vorschau.hinweise.map((h) => (
                      <li key={h}>{h}</li>
                    ))}
                  </ul>
                </Meldung>
              )}

              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-ui-sm bg-ui-surface-muted px-2.5 py-1 font-mono text-[12px] text-ui-text">
                  {vorschau.dateiname}
                </span>
                <Plakette art="neutral">
                  {vorschau.adressblock.length} Zeilen Adressfeld
                </Plakette>
                <Plakette art="neutral">
                  {vorschau.absaetze.length} Absätze
                </Plakette>
                {vorschau.verteilerseite.length > 0 && (
                  <Plakette art="neutral">Verteilerseite</Plakette>
                )}
              </div>

              <Briefvorschau vorschau={vorschau} />

              <div className="flex flex-wrap gap-2">
                <Button
                  icon={FileText}
                  onClick={() => void holeDokument("docx")}
                  disabled={laeuft !== ""}
                >
                  {laeuft === "docx" ? "Wird erzeugt…" : "Word herunterladen"}
                </Button>
                {vorbelegung?.word_vorhanden && (
                  <Button
                    variante="sekundaer"
                    icon={FileSignature}
                    onClick={() => void holeDokument("pdf")}
                    disabled={laeuft !== ""}
                  >
                    {laeuft === "pdf" ? "Wird erzeugt…" : "Als PDF"}
                  </Button>
                )}
              </div>

              {/* ── Outlook ── */}
              <div className="space-y-3 rounded-ui border border-ui-line bg-ui-surface-muted p-3.5">
                <p className="text-[12.5px] text-ui-text-muted">
                  Der Entwurf enthält Empfänger, Betreff, Text und das
                  Schreiben im Anhang. Outlook öffnet ihn als fertige Mail —
                  nur noch das Dokument kontrollieren und senden.
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="An" hinweis="Kommt aus dem Feld „E-Mail der Firma“.">
                    <Input value={mailAn} readOnly />
                  </Field>
                  <Field label="Kopie" hinweis="Mehrere mit Komma trennen.">
                    <Input
                      value={mailKopie}
                      onChange={(e) => setMailKopie(e.target.value)}
                      placeholder="bauherr@example.de, kollege@hpp.com"
                    />
                  </Field>
                </div>
                <Field label="Betreff der E-Mail">
                  <Input
                    value={mailBetreff}
                    onChange={(e) => setMailBetreff(e.target.value)}
                  />
                </Field>
                <Field label="Text der E-Mail">
                  <Textarea
                    value={mailText}
                    onChange={(e) => setMailText(e.target.value)}
                    rows={5}
                  />
                </Field>
                <Checkbox
                  checked={mailAnhang}
                  onChange={setMailAnhang}
                  label="Das Schreiben als Anhang mitgeben"
                />
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    icon={Mail}
                    onClick={() => void holeEntwurf()}
                    disabled={laeuft !== "" || !mailAn}
                  >
                    {laeuft === "eml" ? "Wird erzeugt…" : "Outlook-Entwurf"}
                  </Button>
                  <LinkButton
                    href={mailtoAdresse(
                      mailAn ? [mailAn] : [],
                      mailBetreff,
                      mailText
                    )}
                    icon={Paperclip}
                  >
                    Mailfenster öffnen
                  </LinkButton>
                </div>
                <p className="text-[12px] text-ui-text-muted">
                  Öffnet das neue Outlook oder Outlook im Browser die
                  Entwurfsdatei nicht, den zweiten Knopf nehmen und das
                  Word-Dokument selbst anhängen.
                </p>
              </div>
            </>
          )}
        </KarteInhalt>
      </Karte>

      {!projekt && (
        <LeerHinweis>
          Ohne gewähltes Projekt geht es auch — dann kommen Projektzeile und
          Firma allein aus dem hochgeladenen Schreiben. Wer die Anschriften
          dauerhaft hinterlegen will, pflegt sie unter{" "}
          <button
            type="button"
            onClick={() => onAnsicht("stamm-firmen")}
            className="cursor-pointer underline"
          >
            Stammdaten → Firmen
          </button>
          .
        </LeerHinweis>
      )}
    </div>
  );
}

/* ───────────────────────────── Bausteine ───────────────────────────── */

function Abschnitt({
  titel,
  children,
}: {
  titel: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-3">
      <p className="font-mono text-[10.5px] tracking-[0.1em] uppercase text-ui-text-faint">
        {titel}
      </p>
      {children}
    </div>
  );
}

/** Was der Server aus dem Schreiben gelesen hat — zum Gegenlesen. */
function AusgelesenesFeld({
  schreiben,
  onErneutUebernehmen,
}: {
  schreiben: GelesenesSchreiben;
  onErneutUebernehmen: () => void;
}) {
  const zeilen: [string, string][] = [
    ["Art", schreiben.art || "—"],
    ["Nummer / Kennung", [schreiben.nummer, schreiben.kennung].filter(Boolean).join(" · ") || "—"],
    ["Datum", schreiben.datum ?? "—"],
    ["Betreff", schreiben.betreff || "—"],
    [
      "Anschrift der Firma",
      [
        schreiben.absender.firma,
        schreiben.absender.strasse,
        `${schreiben.absender.plz} ${schreiben.absender.ort}`.trim(),
      ]
        .filter(Boolean)
        .join(", ") || "—",
    ],
    ["Ansprechpartner", schreiben.ansprechpartner || "—"],
    ["E-Mail", schreiben.ansprechpartner_email || schreiben.absender_email || "—"],
    ["Leistungsort", schreiben.leistungsort || "—"],
    ["Gewerk", schreiben.gewerk || "—"],
    ["Rechtsgrundlage", schreiben.rechtsgrundlage || "—"],
    ["LV-Positionen", schreiben.lv_positionen.join(", ") || "—"],
    ["Bauzeit", schreiben.bauzeit || "—"],
    ["Forderung", schreiben.forderung || "—"],
    ["Unterzeichner", [schreiben.unterzeichner, schreiben.unterzeichner_funktion].filter(Boolean).join(", ") || "—"],
    ["Angeschrieben war", schreiben.empfaenger.firma || "—"],
  ];

  return (
    <div className="space-y-2 rounded-ui border border-ui-line bg-ui-surface-muted p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12.5px] font-medium text-ui-text">
          Gelesen aus „{schreiben.quelle}“ ({schreiben.seiten}{" "}
          {schreiben.seiten === 1 ? "Seite" : "Seiten"})
        </p>
        <Button variante="still" icon={RefreshCw} onClick={onErneutUebernehmen}>
          Erneut ins Formular
        </Button>
      </div>

      {schreiben.hinweise.length > 0 && (
        <Meldung art="hinweis">
          <ul className="list-disc pl-4">
            {schreiben.hinweise.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        </Meldung>
      )}

      <dl className="grid gap-x-4 gap-y-1.5 sm:grid-cols-2">
        {zeilen.map(([kopf, wert]) => (
          <div key={kopf} className="min-w-0">
            <dt className="font-mono text-[10px] tracking-[0.08em] uppercase text-ui-text-faint">
              {kopf}
            </dt>
            <dd className="truncate text-[13px] text-ui-text" title={wert}>
              {wert}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** Der Brief, wie er im Dokument aussieht — dieselben Texte vom Server. */
function Briefvorschau({ vorschau }: { vorschau: AnzeigeAntwortVorschau }) {
  return (
    <div className="space-y-4 rounded-ui border border-ui-line bg-ui-surface p-4 text-[13px] leading-relaxed text-ui-text">
      <div className="whitespace-pre-line text-ui-text-muted">
        {vorschau.adressblock.join("\n")}
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-[11px] text-ui-text-faint">
        {vorschau.datumszeile.filter(Boolean).map((z) => (
          <span key={z}>{z}</span>
        ))}
      </div>
      <div className="font-semibold">
        <p>{vorschau.projektzeile}</p>
        {vorschau.vergabeeinheit && <p>{vorschau.vergabeeinheit}</p>}
        <p>{vorschau.betreff}</p>
      </div>
      <p>{vorschau.anrede}</p>
      <div>
        {vorschau.absaetze.map((absatz, nr) => {
          // Ein Zitat, das auf ein Zitat oder auf seine Einleitung folgt,
          // bleibt ohne Abstand — genau wie im Word-Dokument.
          const eng = absatz.zitat && nr > 0;
          return (
            <p
              key={nr}
              className={`${eng ? "" : "mt-2.5 first:mt-0"} ${
                absatz.zitat ? "pl-6 text-ui-text-muted" : ""
              }`}
            >
              {absatz.text}
            </p>
          );
        })}
      </div>
      <div className="space-y-0.5 text-ui-text-muted">
        <p>Mit freundlichen Grüßen</p>
        <p>HPP Architekten GmbH</p>
      </div>
      {vorschau.verteilerseite.length > 0 && (
        <div className="border-t border-ui-line pt-3">
          <p className="mb-1 font-mono text-[10px] tracking-[0.08em] uppercase text-ui-text-faint">
            Letzte Seite
          </p>
          <div className="whitespace-pre-line text-ui-text-muted">
            {vorschau.verteilerseite.join("\n")}
          </div>
        </div>
      )}
      <div className="border-t border-ui-line pt-3">
        <p className="mb-1 font-mono text-[10px] tracking-[0.08em] uppercase text-ui-text-faint">
          E-Mail
        </p>
        <p className="text-ui-text-muted">
          <Check size={12} className="mr-1 inline" />
          {vorschau.mail_an || "kein Empfänger"} · {vorschau.mail_betreff}
        </p>
        <div className="mt-1 whitespace-pre-line text-ui-text-muted">
          {vorschau.mail_text}
        </div>
      </div>
    </div>
  );
}
