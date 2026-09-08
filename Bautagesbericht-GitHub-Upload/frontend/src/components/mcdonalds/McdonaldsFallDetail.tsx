"use client";

/**
 * Eine Beauftragung: Angaben prüfen, Ablage verfolgen, Angebot erstellen.
 *
 * WARUM DIE ANGABEN HIER ÄNDERBAR SIND
 * ====================================
 * Die Mail-Analyse schlägt vor, sie entscheidet nicht (siehe
 * backend/app/services/mcdonalds_email_analyse). Und ohne Anthropic-Schlüssel
 * schlägt sie gar nichts vor. Diese Ansicht ist deshalb der Ort, an dem ein
 * Mensch draufsieht, bevor aus den Angaben ein Ordnername und ein Angebot
 * werden — mit sichtbarem Unterschied zwischen "von der KI gelesen" und "von
 * Hand eingetragen".
 *
 * DER ORDNER IST EIN ZUSTAND, KEIN KNOPF
 * ======================================
 * Er entsteht im Hintergrund. Angezeigt wird, was daraus wurde, samt Pfad zum
 * Nachschauen. Der Knopf "Ordner anlegen" ist der zweite Versuch — nach einer
 * Korrektur oder nachdem der Basispfad eingetragen wurde.
 */

import {
  AlertTriangle,
  ArrowLeft,
  Building2,
  Calendar,
  CheckCircle2,
  Download,
  FileText,
  FolderOpen,
  Loader2,
  Mail,
  MapPin,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Table,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useRef, useState } from "react";

import { api } from "@/lib/api";
import { dateiSpeichern } from "@/lib/dateien";
import type {
  Fachplaner,
  McdonaldsAngebot,
  McdonaldsFaehigkeiten,
  McdonaldsFall,
  OrdnerStatus,
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
import { AngebotErstellen } from "@/components/mcdonalds/AngebotErstellen";

const PHASEN = [6, 7, 8, 9, 1, 2, 3, 4, 5];

const STATUS_TEXT: Record<OrdnerStatus, string> = {
  ausstehend: "wird angelegt",
  angelegt: "angelegt",
  fehler: "offen",
};

const STATUS_ART: Record<OrdnerStatus, "ok" | "warn" | "gefahr"> = {
  ausstehend: "warn",
  angelegt: "ok",
  fehler: "gefahr",
};

export function McdonaldsFallDetail({
  fall,
  fachplaner,
  faehigkeiten,
  onZurueck,
  onAktualisiert,
  onGeloescht,
  onFachplanerAendern,
}: {
  fall: McdonaldsFall;
  fachplaner: Fachplaner[];
  faehigkeiten: McdonaldsFaehigkeiten | null;
  onZurueck: () => void;
  onAktualisiert: () => void;
  onGeloescht: () => void;
  onFachplanerAendern: () => void;
}) {
  const [bearbeiten, setBearbeiten] = useState(false);
  const [angebotOffen, setAngebotOffen] = useState(false);
  const [laeuft, setLaeuft] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);

  async function ordnerAnlegen() {
    setLaeuft("ordner");
    setFehler(null);
    setMeldung(null);
    try {
      const neu = await api.mcdonalds.ordnerAnlegen(fall.id);
      setMeldung(
        neu.ordner_status === "angelegt"
          ? `Ordner „${neu.ordner_name}“ ist angelegt.`
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
        `Diese Beauftragung löschen?\n\n` +
          `Zugehörige Angebote werden mit entfernt. Der bereits angelegte ` +
          `Ordner im Netzlaufwerk bleibt bestehen.`
      )
    ) {
      return;
    }
    setLaeuft("loeschen");
    try {
      await api.mcdonalds.fallLoeschen(fall.id);
      onGeloescht();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Löschen fehlgeschlagen.");
      setLaeuft("");
    }
  }

  const titel =
    fall.standort_name || fall.ordner_name || fall.standort_ort || "Ohne Standort";

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
          {!angebotOffen && (
            <Button icon={Plus} onClick={() => setAngebotOffen(true)}>
              Angebot erstellen
            </Button>
          )}
        </div>
      </div>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}
      {meldung && <Meldung art="erfolg">{meldung}</Meldung>}
      {fall.hinweise.map((hinweis, i) => (
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
              fall.analysiert_am
                ? `Aus der Mail gelesen am ${formatDatum(fall.analysiert_am)} — bitte gegenlesen`
                : fall.quelle === "telefon"
                ? "Von Hand erfasst (telefonische Beauftragung)"
                : "Nicht automatisch ausgewertet — Angaben von Hand prüfen"
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
                fall={fall}
                onFertig={() => {
                  setBearbeiten(false);
                  onAktualisiert();
                }}
                onAbbrechen={() => setBearbeiten(false)}
              />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <ReadOnlyField label="Auftraggeber" wert={fall.auftraggeber} />
                <ReadOnlyField
                  label="Leistungsphase"
                  wert={fall.leistungsphase ? `LPH ${fall.leistungsphase}` : ""}
                />
                <ReadOnlyField
                  label="Anschrift"
                  wert={fall.standort_adresse}
                  hervorgehoben={!fall.standort_adresse}
                />
                <ReadOnlyField label="Ort (für den Ortscode)" wert={fall.standort_ort} />
                <ReadOnlyField label="UN/LOCODE" wert={fall.unlocode ?? ""} />
                <ReadOnlyField
                  label="Erfasst am"
                  wert={formatDatum(fall.erstellt_am)}
                />
              </div>
            )}
          </KarteInhalt>
        </Karte>

        {/* ── Ablage ── */}
        <Karte>
          <KarteKopf
            titel="Projektordner"
            icon={FolderOpen}
            unterzeile="Netzlaufwerk und SharePoint — im Hintergrund angelegt."
            aktion={
              <Plakette art={STATUS_ART[fall.ordner_status]}>
                {STATUS_TEXT[fall.ordner_status]}
              </Plakette>
            }
          />
          <KarteInhalt className="flex flex-col gap-3">
            <ReadOnlyField
              label="Ordnername"
              wert={
                fall.ordner_name ? (
                  <span className="font-mono">{fall.ordner_name}</span>
                ) : (
                  ""
                )
              }
            />
            <PfadZeile
              label="Netzlaufwerk H:"
              pfad={fall.ordner_pfad_h}
              fehlt="Noch nicht angelegt."
            />
            <PfadZeile
              label="SharePoint"
              pfad={fall.ordner_pfad_sharepoint}
              fehlt="Anbindung noch nicht in Betrieb — bitte von Hand anlegen."
            />

            {fall.fehlermeldung && (
              <Meldung
                art={fall.ordner_status === "fehler" ? "fehler" : "hinweis"}
              >
                {fall.fehlermeldung}
              </Meldung>
            )}

            <div className="flex flex-wrap gap-2 border-t border-app-linie pt-3">
              <Button
                variante="sekundaer"
                icon={laeuft === "ordner" ? Loader2 : RefreshCw}
                onClick={ordnerAnlegen}
                disabled={laeuft !== ""}
              >
                {fall.ordner_status === "angelegt"
                  ? "Erneut anlegen"
                  : "Ordner anlegen"}
              </Button>
            </div>
          </KarteInhalt>
        </Karte>
      </div>

      {/* ── Weitere Eckdaten ── */}
      {Object.keys(fall.eckdaten).length > 0 && (
        <Karte>
          <KarteKopf titel="Weitere Eckdaten" icon={Calendar} />
          <KarteInhalt className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(fall.eckdaten).map(([bezeichnung, wert]) => (
              <ReadOnlyField key={bezeichnung} label={bezeichnung} wert={wert} />
            ))}
          </KarteInhalt>
        </Karte>
      )}

      {/* ── Angebot erstellen ── */}
      {angebotOffen && (
        <AngebotErstellen
          fall={fall}
          fachplaner={fachplaner}
          faehigkeiten={faehigkeiten}
          onFertig={() => {
            setAngebotOffen(false);
            onAktualisiert();
          }}
          onAbbrechen={() => setAngebotOffen(false)}
          onFachplanerAendern={onFachplanerAendern}
        />
      )}

      {/* ── Angebote ── */}
      <Karte>
        <KarteKopf
          titel="Angebote"
          icon={FileText}
          unterzeile="Dokument erzeugen und als Outlook-Entwurf verschicken."
        />
        <KarteInhalt className="px-0 sm:px-0">
          {fall.angebote.length === 0 ? (
            <div className="px-4 sm:px-5">
              <LeerHinweis>
                Noch kein Angebot. „Angebot erstellen“ öffnet das Formular.
              </LeerHinweis>
            </div>
          ) : (
            <div className="border-t border-app-linie">
              {fall.angebote.map((angebot) => (
                <AngebotZeile
                  key={angebot.id}
                  angebot={angebot}
                  smtp={faehigkeiten?.smtp ?? false}
                  onAendern={onAktualisiert}
                  onFehler={setFehler}
                  onMeldung={setMeldung}
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

function PfadZeile({
  label,
  pfad,
  fehlt,
}: {
  label: string;
  pfad: string | null;
  fehlt: string;
}) {
  return (
    <ReadOnlyField
      label={label}
      wert={
        pfad ? (
          <span className="inline-flex items-start gap-1.5">
            <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-app-ok" />
            <span className="min-w-0 font-mono text-[12px] break-all">{pfad}</span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-app-text-still">
            <AlertTriangle size={13} className="shrink-0" />
            {fehlt}
          </span>
        )
      }
    />
  );
}

/** Die Angaben eines Falls korrigieren. */
function AngabenFormular({
  fall,
  onFertig,
  onAbbrechen,
}: {
  fall: McdonaldsFall;
  onFertig: () => void;
  onAbbrechen: () => void;
}) {
  const [standortName, setStandortName] = useState(fall.standort_name);
  const [adresse, setAdresse] = useState(fall.standort_adresse);
  const [ort, setOrt] = useState(fall.standort_ort);
  const [auftraggeber, setAuftraggeber] = useState(fall.auftraggeber);
  const [phase, setPhase] = useState(
    fall.leistungsphase ? String(fall.leistungsphase) : ""
  );
  const [code, setCode] = useState(fall.unlocode ?? "");
  const [speichert, setSpeichert] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [treffer, setTreffer] = useState<string | null>(null);

  async function codeSuchen() {
    const gesucht = ort.trim() || adresse.trim();
    if (!gesucht) return;
    setFehler(null);
    setTreffer(null);
    try {
      const ergebnis = await api.mcdonalds.unlocodeSuche(gesucht);
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
      await api.mcdonalds.aendern(fall.id, {
        standort_name: standortName.trim(),
        standort_adresse: adresse.trim(),
        standort_ort: ort.trim(),
        auftraggeber: auftraggeber.trim(),
        leistungsphase: phase ? Number(phase) : null,
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
        <Field label="Standort">
          <Input
            value={standortName}
            onChange={(e) => setStandortName(e.target.value)}
            placeholder="z. B. Aachen Europaplatz"
          />
        </Field>
        <Field label="Auftraggeber">
          <Input
            value={auftraggeber}
            onChange={(e) => setAuftraggeber(e.target.value)}
          />
        </Field>
        <Field label="Anschrift">
          <Input value={adresse} onChange={(e) => setAdresse(e.target.value)} />
        </Field>
        <Field label="Ort" hinweis="Grundlage der Ortscode-Suche.">
          <Input value={ort} onChange={(e) => setOrt(e.target.value)} />
        </Field>
        <Field label="Leistungsphase">
          <Select value={phase} onChange={(e) => setPhase(e.target.value)}>
            <option value="">nicht angegeben</option>
            {PHASEN.map((p) => (
              <option key={p} value={p}>
                LPH {p}
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
              placeholder="AAH"
              className="w-24 font-mono"
            />
            <Button variante="sekundaer" icon={Search} onClick={codeSuchen}>
              Suchen
            </Button>
          </div>
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

/** Eine Zeile der Angebotsliste samt ihren beiden Aktionen. */
function AngebotZeile({
  angebot,
  smtp,
  onAendern,
  onFehler,
  onMeldung,
}: {
  angebot: McdonaldsAngebot;
  smtp: boolean;
  onAendern: () => void;
  onFehler: (text: string | null) => void;
  onMeldung: (text: string | null) => void;
}) {
  const [laeuft, setLaeuft] = useState("");

  async function dokument() {
    setLaeuft("dokument");
    onFehler(null);
    onMeldung(null);
    try {
      const { blob, dateiname } = await api.mcdonalds.dokumentErzeugen(angebot.id);
      dateiSpeichern(blob, dateiname || "angebot.docx");
      onMeldung("Das Angebotsdokument wurde erzeugt und heruntergeladen.");
      onAendern();
    } catch (err) {
      onFehler(err instanceof Error ? err.message : "Erzeugen fehlgeschlagen.");
    } finally {
      setLaeuft("");
    }
  }

  async function entwurf() {
    setLaeuft("entwurf");
    onFehler(null);
    onMeldung(null);
    try {
      const { blob, dateiname } = await api.mcdonalds.entwurf(angebot.id);
      dateiSpeichern(blob, dateiname || "angebot.eml");
      onMeldung(
        "Der Outlook-Entwurf wurde heruntergeladen. Doppelklick öffnet ihn " +
          "mit Empfänger, Text und Angebot im Anhang — abgeschickt wird er " +
          "von Outlook."
      );
      onAendern();
    } catch (err) {
      onFehler(err instanceof Error ? err.message : "Entwurf fehlgeschlagen.");
    } finally {
      setLaeuft("");
    }
  }

  async function senden() {
    setLaeuft("senden");
    onFehler(null);
    onMeldung(null);
    try {
      const ergebnis = await api.mcdonalds.senden(angebot.id);
      onMeldung(ergebnis.nachricht);
      onAendern();
    } catch (err) {
      onFehler(err instanceof Error ? err.message : "Versand fehlgeschlagen.");
    } finally {
      setLaeuft("");
    }
  }

  return (
    <ListenZeile
      vorne={<Building2 size={14} className="shrink-0 text-app-text-leise" />}
      titel={angebot.fachplaner_name || "ohne Fachplaner"}
      unterzeile={
        <>
          {angebot.leistungsphase ? `LPH ${angebot.leistungsphase} · ` : ""}
          {angebot.fachplaner_email}
          {angebot.mail_versendet_am
            ? ` · ${
                angebot.mail_weg === "entwurf" ? "Entwurf erstellt" : "versendet"
              } ${formatDatum(angebot.mail_versendet_am)}`
            : ""}
        </>
      }
      rechts={
        <span className="flex items-center gap-1.5">
          <Button
            variante="still"
            icon={laeuft === "dokument" ? Loader2 : Download}
            onClick={dokument}
            disabled={laeuft !== ""}
          >
            Dokument
          </Button>
          <Button
            variante="sekundaer"
            icon={laeuft === "entwurf" ? Loader2 : Mail}
            onClick={entwurf}
            disabled={laeuft !== ""}
          >
            Outlook-Entwurf
          </Button>
          {smtp && (
            <Button
              variante="still"
              icon={laeuft === "senden" ? Loader2 : Mail}
              onClick={senden}
              disabled={laeuft !== ""}
            >
              Direkt senden
            </Button>
          )}
        </span>
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
  faehigkeiten: McdonaldsFaehigkeiten | null;
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
          Ersetzt den bisherigen Bestand. Nur <span className="font-mono">.xlsx</span>{" "}
          — eine alte <span className="font-mono">.xls</span> vorher in Excel neu
          speichern.
        </span>
      </KarteInhalt>
    </Karte>
  );
}
