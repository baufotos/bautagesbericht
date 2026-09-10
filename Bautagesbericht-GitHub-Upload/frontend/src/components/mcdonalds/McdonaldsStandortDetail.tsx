"use client";

/**
 * Ein Standort: Angaben prüfen, Ordner verfolgen, Subplaner beauftragen.
 *
 * WARUM DIE ANGABEN ÄNDERBAR SIND
 * ===============================
 * Die Mail-Auswertung *schlägt vor*. Bei einer echten SLS-Anfrage trifft sie
 * zuverlässig, weil die Mail maschinenerzeugt ist — aber ein zweiter Standort
 * in derselben Stadt braucht einen anderen Ordnernamen, und ein Termin kann
 * sich ändern. Diese Ansicht ist der Ort, an dem ein Mensch draufsieht, bevor
 * aus den Angaben ein Ordnername und ein Vertragstermin wird.
 */

import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  Download,
  FolderOpen,
  Loader2,
  MapPin,
  Pencil,
  RefreshCw,
  Search,
  Send,
  Table,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useRef, useState } from "react";

import { api } from "@/lib/api";
import { dateiSpeichern } from "@/lib/dateien";
import type {
  McdBeauftragung,
  McdFaehigkeiten,
  McdStandort,
  OrdnerStatus,
  Subplaner,
} from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  LeerHinweis,
  ListenZeile,
  Plakette,
} from "@/components/dashboard";
import {
  Button,
  Field,
  Input,
  Meldung,
  ReadOnlyField,
  Select,
  formatDatum,
} from "@/components/ui";
import { BeauftragungErstellen } from "@/components/mcdonalds/BeauftragungErstellen";

const PHASEN = [1, 2, 3];

const STATUS_TEXT: Record<OrdnerStatus, string> = {
  ausstehend: "wird angelegt",
  vorbereitet: "vorbereitet",
  angelegt: "angelegt",
  fehler: "fehlerhaft",
};

const STATUS_ART: Record<OrdnerStatus, "ok" | "warn" | "gefahr" | "info"> = {
  ausstehend: "warn",
  vorbereitet: "info",
  angelegt: "ok",
  fehler: "gefahr",
};

export function McdonaldsStandortDetail({
  standort,
  subplaner,
  faehigkeiten,
  onZurueck,
  onAktualisiert,
  onGeloescht,
}: {
  standort: McdStandort;
  subplaner: Subplaner[];
  faehigkeiten: McdFaehigkeiten | null;
  onZurueck: () => void;
  onAktualisiert: () => void;
  onGeloescht: () => void;
}) {
  const [bearbeiten, setBearbeiten] = useState(false);
  const [beauftragenOffen, setBeauftragenOffen] = useState(false);
  const [laeuft, setLaeuft] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);

  async function ordnerAnlegen() {
    setLaeuft("ordner");
    setFehler(null);
    setMeldung(null);
    try {
      const neu = await api.mcdonalds.ordnerAnlegen(standort.id);
      setMeldung(
        neu.ordner_status === "angelegt"
          ? `Ordner „${neu.ordner_name}“ ist angelegt — ${neu.ordner_anzahl} Unterordner.`
          : neu.fehlermeldung || "Der Ordner konnte nicht angelegt werden."
      );
      onAktualisiert();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Anlegen fehlgeschlagen.");
    } finally {
      setLaeuft("");
    }
  }

  async function loeschen() {
    if (
      !window.confirm(
        "Diesen Standort löschen?\n\n" +
          "Die erzeugten Einzelabrufe werden mit entfernt. Ein bereits " +
          "angelegter Ordner im Projektlaufwerk bleibt bestehen."
      )
    ) {
      return;
    }
    setLaeuft("loeschen");
    try {
      await api.mcdonalds.standortLoeschen(standort.id);
      onGeloescht();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Löschen fehlgeschlagen.");
      setLaeuft("");
    }
  }

  const titel =
    standort.ordner_name || standort.standort_name || standort.ort || "Ohne Ort";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variante="still" icon={ArrowLeft} onClick={onZurueck}>
          Zur Übersicht
        </Button>
        <div className="ml-auto flex items-center gap-2">
          <Button
            variante="still"
            icon={laeuft === "loeschen" ? Loader2 : Trash2}
            onClick={loeschen}
            disabled={laeuft !== ""}
          >
            Löschen
          </Button>
          {!beauftragenOffen && (
            <Button icon={Send} onClick={() => setBeauftragenOffen(true)}>
              Subplaner beauftragen
            </Button>
          )}
        </div>
      </div>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}
      {meldung && <Meldung art="erfolg">{meldung}</Meldung>}
      {standort.hinweise.map((hinweis, i) => (
        <Meldung key={i} art="hinweis">
          {hinweis}
        </Meldung>
      ))}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {/* ── Angaben ── */}
        <Karte>
          <KarteKopf
            titel={titel}
            icon={MapPin}
            unterzeile={
              standort.sls_erkannt
                ? "Aus der SLS-Anfrage gelesen — Betreff und Text, ohne KI"
                : standort.analysiert_am
                ? `KI-Auswertung vom ${formatDatum(standort.analysiert_am)} — bitte gegenlesen`
                : "Von Hand erfasst"
            }
            aktion={
              !bearbeiten ? (
                <Button
                  variante="still"
                  icon={Pencil}
                  onClick={() => setBearbeiten(true)}
                >
                  Ändern
                </Button>
              ) : undefined
            }
          />
          <KarteInhalt>
            {bearbeiten ? (
              <AngabenFormular
                standort={standort}
                onFertig={() => {
                  setBearbeiten(false);
                  onAktualisiert();
                }}
                onAbbrechen={() => setBearbeiten(false)}
              />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <ReadOnlyField
                  label="Phase"
                  wert={standort.phase ? `Phase ${standort.phase}` : ""}
                />
                <ReadOnlyField label="UN/LOCODE" wert={standort.unlocode ?? ""} />
                <ReadOnlyField
                  label="Ort"
                  wert={standort.ort}
                  hervorgehoben={!standort.ort}
                />
                <ReadOnlyField
                  label="Anschrift"
                  wert={[standort.strasse, `${standort.plz} ${standort.ort}`.trim()]
                    .filter(Boolean)
                    .join(", ")}
                />
                <ReadOnlyField
                  label="Leistungsbeginn"
                  wert={formatDatum(standort.leistungsbeginn)}
                />
                <ReadOnlyField
                  label="Abgabetermin"
                  wert={formatDatum(standort.abgabetermin)}
                />
                <ReadOnlyField
                  label="SLS-Vorgang"
                  wert={standort.sls_vorgang}
                />
                <ReadOnlyField
                  label="Erfasst am"
                  wert={formatDatum(standort.erstellt_am)}
                />
              </div>
            )}
          </KarteInhalt>
        </Karte>

        {/* ── Ablage ── */}
        <Karte>
          <KarteKopf
            titel="Standortordner"
            icon={FolderOpen}
            unterzeile={
              faehigkeiten
                ? `Musterstruktur mit ${faehigkeiten.unterordner} Unterordnern`
                : "Musterstruktur des Büros"
            }
            aktion={
              <Plakette art={STATUS_ART[standort.ordner_status]}>
                {STATUS_TEXT[standort.ordner_status]}
              </Plakette>
            }
          />
          <KarteInhalt className="flex flex-col gap-3">
            <ReadOnlyField
              label="Ordnername"
              wert={
                standort.ordner_name ? (
                  <span className="font-mono">{standort.ordner_name}</span>
                ) : (
                  ""
                )
              }
            />
            <ReadOnlyField
              label="Projektlaufwerk"
              wert={
                standort.ordner_pfad ? (
                  <span className="inline-flex items-start gap-1.5">
                    <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-app-ok" />
                    <span className="min-w-0 font-mono text-[12px] break-all">
                      {standort.ordner_pfad}
                      {standort.ordner_anzahl > 0 && (
                        <span className="text-app-text-still">
                          {" "}
                          ({standort.ordner_anzahl} Unterordner)
                        </span>
                      )}
                    </span>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 text-app-text-still">
                    <Clock size={13} className="shrink-0" />
                    Noch nicht angelegt
                  </span>
                )
              }
            />

            {standort.fehlermeldung && (
              <Meldung
                art={standort.ordner_status === "fehler" ? "fehler" : "hinweis"}
              >
                {standort.fehlermeldung}
              </Meldung>
            )}

            <div className="flex flex-wrap gap-2 border-t border-app-linie pt-3">
              <Button
                variante="sekundaer"
                icon={laeuft === "ordner" ? Loader2 : RefreshCw}
                onClick={ordnerAnlegen}
                disabled={laeuft !== ""}
              >
                {standort.ordner_status === "angelegt"
                  ? "Struktur ergänzen"
                  : "Ordner anlegen"}
              </Button>
            </div>
          </KarteInhalt>
        </Karte>
      </div>

      {/* ── Beauftragen ── */}
      {beauftragenOffen && (
        <BeauftragungErstellen
          standort={standort}
          subplaner={subplaner}
          faehigkeiten={faehigkeiten}
          onFertig={() => {
            setBeauftragenOffen(false);
            onAktualisiert();
          }}
          onAbbrechen={() => setBeauftragenOffen(false)}
        />
      )}

      {/* ── Erzeugte Einzelabrufe ── */}
      <Karte>
        <KarteKopf
          titel="Einzelabrufe"
          icon={Send}
          unterzeile="Erzeugte Beauftragungen — Entwurf jederzeit erneut abrufbar."
        />
        <KarteInhalt className="px-0 sm:px-0">
          {standort.beauftragungen.length === 0 ? (
            <div className="px-4 sm:px-5">
              <LeerHinweis>
                Noch kein Einzelabruf. „Subplaner beauftragen“ führt durch
                Phase, Termine und Vorschau.
              </LeerHinweis>
            </div>
          ) : (
            <div className="border-t border-app-linie">
              {standort.beauftragungen.map((eintrag) => (
                <BeauftragungZeile
                  key={eintrag.id}
                  eintrag={eintrag}
                  onFehler={setFehler}
                />
              ))}
            </div>
          )}
        </KarteInhalt>
      </Karte>

      {/* ── Referenztabelle ── */}
      <UnlocodeKarte
        faehigkeiten={faehigkeiten}
        onGeladen={onAktualisiert}
        onFehler={setFehler}
        onMeldung={setMeldung}
      />
    </div>
  );
}

/** Die Angaben eines Standorts korrigieren. */
function AngabenFormular({
  standort,
  onFertig,
  onAbbrechen,
}: {
  standort: McdStandort;
  onFertig: () => void;
  onAbbrechen: () => void;
}) {
  const [ort, setOrt] = useState(standort.ort);
  const [plz, setPlz] = useState(standort.plz);
  const [strasse, setStrasse] = useState(standort.strasse);
  const [name, setName] = useState(standort.standort_name);
  const [phase, setPhase] = useState(
    standort.phase ? String(standort.phase) : ""
  );
  const [beginn, setBeginn] = useState(standort.leistungsbeginn ?? "");
  const [abgabe, setAbgabe] = useState(standort.abgabetermin ?? "");
  const [code, setCode] = useState(standort.unlocode ?? "");
  const [speichert, setSpeichert] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [treffer, setTreffer] = useState<string | null>(null);

  async function codeSuchen() {
    if (!ort.trim()) return;
    setFehler(null);
    setTreffer(null);
    try {
      const ergebnis = await api.mcdonalds.unlocodeSuche(ort.trim());
      setCode(ergebnis.code);
      setTreffer(
        `${ergebnis.code} — ${ergebnis.ort}` +
          (ergebnis.bundesland ? ` (${ergebnis.bundesland})` : "") +
          (ergebnis.art === "unscharf"
            ? " · unscharfer Treffer, bitte prüfen"
            : "")
      );
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Suche fehlgeschlagen.");
    }
  }

  async function speichern() {
    setSpeichert(true);
    setFehler(null);
    try {
      await api.mcdonalds.aendern(standort.id, {
        ort: ort.trim(),
        plz: plz.trim(),
        strasse: strasse.trim(),
        standort_name: name.trim() || ort.trim(),
        phase: phase ? Number(phase) : null,
        leistungsbeginn: beginn || null,
        abgabetermin: abgabe || null,
        ...(code.trim().length === 3 ? { unlocode: code.trim() } : {}),
      });
      onFertig();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Speichern fehlgeschlagen.");
    } finally {
      setSpeichert(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}
      {treffer && <Meldung art="hinweis">{treffer}</Meldung>}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Ort" hinweis="Grundlage der Ortscode-Suche.">
          <Input value={ort} onChange={(e) => setOrt(e.target.value)} />
        </Field>
        <Field
          label="Ordnername (Teil nach dem Code)"
          hinweis="Leer = wie der Ort. Bei zwei Standorten in einer Stadt hier unterscheiden."
        >
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={ort}
          />
        </Field>
        <Field label="Postleitzahl">
          <Input value={plz} onChange={(e) => setPlz(e.target.value)} />
        </Field>
        <Field label="Straße">
          <Input value={strasse} onChange={(e) => setStrasse(e.target.value)} />
        </Field>
        <Field label="Phase">
          <Select value={phase} onChange={(e) => setPhase(e.target.value)}>
            <option value="">nicht angegeben</option>
            {PHASEN.map((p) => (
              <option key={p} value={p}>
                Phase {p}
              </option>
            ))}
          </Select>
        </Field>
        <Field
          label="UN/LOCODE"
          hinweis="Drei Buchstaben. „Suchen“ schlägt ihn zum Ort nach."
        >
          <div className="flex gap-2">
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase().slice(0, 3))}
              placeholder="NIV"
              className="w-24 font-mono"
            />
            <Button variante="sekundaer" icon={Search} onClick={codeSuchen}>
              Suchen
            </Button>
          </div>
        </Field>
        <Field label="Leistungsbeginn">
          <Input
            type="date"
            value={beginn}
            onChange={(e) => setBeginn(e.target.value)}
          />
        </Field>
        <Field label="Abgabetermin">
          <Input
            type="date"
            value={abgabe}
            onChange={(e) => setAbgabe(e.target.value)}
          />
        </Field>
      </div>

      <div className="flex gap-2">
        <Button onClick={speichern} disabled={speichert}>
          {speichert ? "Wird gespeichert…" : "Angaben speichern"}
        </Button>
        <Button variante="still" icon={X} onClick={onAbbrechen}>
          Abbrechen
        </Button>
      </div>
    </div>
  );
}

function BeauftragungZeile({
  eintrag,
  onFehler,
}: {
  eintrag: McdBeauftragung;
  onFehler: (text: string | null) => void;
}) {
  const [laeuft, setLaeuft] = useState(false);

  async function entwurf() {
    setLaeuft(true);
    onFehler(null);
    try {
      const { blob, dateiname } = await api.mcdonalds.entwurf(eintrag.id);
      dateiSpeichern(blob, dateiname || "beauftragung.eml");
    } catch (err) {
      onFehler(err instanceof Error ? err.message : "Entwurf fehlgeschlagen.");
    } finally {
      setLaeuft(false);
    }
  }

  return (
    <ListenZeile
      vorne={<Send size={14} className="shrink-0 text-app-text-leise" />}
      titel={eintrag.betreff || eintrag.subplaner_name}
      unterzeile={
        <>
          {eintrag.empfaenger.join(", ") || "ohne Empfänger"}
          {eintrag.eml_pfad
            ? " · im Vertragsordner abgelegt"
            : " · Ablage steht noch aus"}
        </>
      }
      rechts={
        <Button
          variante="sekundaer"
          icon={laeuft ? Loader2 : Download}
          onClick={entwurf}
          disabled={laeuft}
        >
          Entwurf
        </Button>
      }
    />
  );
}

/**
 * Die UN/LOCODE-Referenztabelle hochladen.
 *
 * Steht hier und nicht in den Stammdaten: Man merkt, dass sie fehlt, wenn ein
 * Ordner „XXX_…“ heißt — und dann ist man in dieser Ansicht.
 */
function UnlocodeKarte({
  faehigkeiten,
  onGeladen,
  onFehler,
  onMeldung,
}: {
  faehigkeiten: McdFaehigkeiten | null;
  onGeladen: () => void;
  onFehler: (text: string | null) => void;
  onMeldung: (text: string | null) => void;
}) {
  const [laeuft, setLaeuft] = useState(false);
  const dateiwahl = useRef<HTMLInputElement>(null);
  const anzahl = faehigkeiten?.unlocode_eintraege ?? 0;

  async function hochladen(dateien: FileList | null) {
    const datei = dateien?.[0];
    if (!datei) return;
    setLaeuft(true);
    onFehler(null);
    onMeldung(null);
    try {
      const ergebnis = await api.mcdonalds.unlocodeTabelle(datei);
      onMeldung(
        `${ergebnis.eingelesen} Orte aus Blatt „${ergebnis.blatt}“ übernommen.` +
          (ergebnis.uebersprungen
            ? ` ${ergebnis.uebersprungen} Zeile(n) übersprungen.`
            : "")
      );
      onGeladen();
    } catch (err) {
      onFehler(err instanceof Error ? err.message : "Upload fehlgeschlagen.");
    } finally {
      setLaeuft(false);
      if (dateiwahl.current) dateiwahl.current.value = "";
    }
  }

  return (
    <Karte>
      <KarteKopf
        titel="UN/LOCODE-Tabelle"
        icon={Table}
        unterzeile="Anlage 5.1 des Projekthandbuchs — Grundlage des Ortscodes im Ordnernamen."
        aktion={
          <Plakette art={anzahl > 0 ? "ok" : "warn"}>
            {anzahl > 0 ? `${anzahl} Orte` : "nicht geladen"}
          </Plakette>
        }
      />
      <KarteInhalt className="flex flex-wrap items-center gap-2">
        <input
          ref={dateiwahl}
          type="file"
          accept=".xlsx"
          onChange={(e) => void hochladen(e.target.files)}
          className="hidden"
        />
        <Button
          variante="sekundaer"
          icon={laeuft ? Loader2 : Upload}
          onClick={() => dateiwahl.current?.click()}
          disabled={laeuft}
        >
          {laeuft ? "Wird gelesen…" : "Excel-Tabelle hochladen"}
        </Button>
        <span className="text-[12px] text-app-text-still">
          Ersetzt den bisherigen Bestand. Nur{" "}
          <span className="font-mono">.xlsx</span> — eine alte{" "}
          <span className="font-mono">.xls</span> vorher in Excel neu speichern.
        </span>
      </KarteInhalt>
    </Karte>
  );
}
