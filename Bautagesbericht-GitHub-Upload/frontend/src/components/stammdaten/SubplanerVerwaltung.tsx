"use client";

/**
 * Subplaner pflegen — gegliedert nach Phase, wie im Büro gedacht.
 *
 *     Phase 1
 *       Kocks Consult          Ansprechpartner, mehrere E-Mail-Adressen
 *       RKA Architekten …      Ansprechpartner, mehrere E-Mail-Adressen
 *     Phase 2
 *       …
 *
 * WARUM MEHRERE ADRESSEN JE FIRMA
 * ===============================
 * Weil der Einzelabruf beim Sachbearbeiter *und* im Sekretariat ankommen
 * soll. Eine Adresse pro Firma hieße, den Rest von Hand nachzutragen — genau
 * das, was diese Stammdaten ersparen sollen.
 *
 * DIE ZWEI FIRMEN DER PHASE 1 SIND SCHON DA
 * =========================================
 * Kocks und RKA werden beim ersten Start angelegt, mit Anrede, Angebotsdatum,
 * Vertragsordner und Textfassung aus den Musterschreiben des Büros. Was fehlt,
 * sind die E-Mail-Adressen — die standen in den Vorlagen nicht drin und werden
 * nicht geraten. Solange sie fehlen, sagt die Karte das, und es lässt sich
 * kein Entwurf erzeugen.
 */

import {
  AlertTriangle,
  Building2,
  Calendar,
  FolderTree,
  Mail,
  Pencil,
  Plus,
  Trash2,
  User,
  X,
} from "lucide-react";
import { useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { McdFaehigkeiten, Subplaner, SubplanerEingabe } from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  LeerHinweis,
  Plakette,
} from "@/components/dashboard";
import {
  Button,
  Field,
  Input,
  Meldung,
  Select,
  formatDatum,
} from "@/components/ui";

const PHASEN = [1, 2, 3];

export function SubplanerVerwaltung({
  subplaner,
  faehigkeiten,
  onAendern,
}: {
  subplaner: Subplaner[];
  faehigkeiten: McdFaehigkeiten | null;
  onAendern: () => void;
}) {
  const [neuInPhase, setNeuInPhase] = useState<number | null>(null);
  const [bearbeiten, setBearbeiten] = useState<number | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  const varianten = faehigkeiten?.textvarianten ?? [];

  async function loeschen(eintrag: Subplaner) {
    setFehler(null);
    if (
      !window.confirm(
        `„${eintrag.name}“ aus den Stammdaten entfernen?\n\n` +
          "Bereits erzeugte Einzelabrufe bleiben erhalten."
      )
    ) {
      return;
    }
    try {
      await api.subplaner.delete(eintrag.id);
      onAendern();
    } catch (err) {
      // Der Server lehnt mit 409 ab, wenn Einzelabrufe daran hängen — seine
      // Meldung nennt die Anzahl und ist besser als jeder eigene Text.
      const detail =
        err instanceof ApiError &&
        typeof err.detail === "object" &&
        err.detail !== null &&
        "nachricht" in err.detail
          ? String((err.detail as { nachricht: unknown }).nachricht)
          : err instanceof Error
          ? err.message
          : "Löschen fehlgeschlagen.";
      setFehler(detail);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[12.5px] leading-relaxed text-app-text-still">
        Die Unternehmen, die je Phase beauftragt werden. Sie sind über alle
        Standorte dieselben — deshalb stehen sie hier und nicht am Standort.
        Anrede, Angebotsdatum und Vertragsordner fließen wortgleich in den
        Einzelabruf ein.
      </p>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {PHASEN.map((phase) => {
        const dieserPhase = subplaner.filter((s) => s.phase === phase);
        return (
          <div key={phase} className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[11px] tracking-[0.12em] uppercase text-app-text-still">
                Phase {phase}
              </span>
              <span className="text-[12px] text-app-text-leise">
                {dieserPhase.length === 0
                  ? "keine Unternehmen"
                  : `${dieserPhase.length} Unternehmen`}
              </span>
              {neuInPhase !== phase && (
                <Button
                  variante="still"
                  icon={Plus}
                  onClick={() => {
                    setNeuInPhase(phase);
                    setBearbeiten(null);
                  }}
                >
                  Unternehmen
                </Button>
              )}
            </div>

            {dieserPhase.length === 0 && neuInPhase !== phase && (
              <LeerHinweis>
                Für Phase {phase} ist noch kein Unternehmen hinterlegt.
              </LeerHinweis>
            )}

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {dieserPhase.map((eintrag) =>
                bearbeiten === eintrag.id ? (
                  <div key={eintrag.id} className="sm:col-span-2 xl:col-span-3">
                    <SubplanerFormular
                      titel={`${eintrag.name} ändern`}
                      phase={eintrag.phase}
                      varianten={varianten}
                      start={eintrag}
                      onSpeichern={async (daten) => {
                        await api.subplaner.aendern(eintrag.id, daten);
                        setBearbeiten(null);
                        onAendern();
                      }}
                      onAbbrechen={() => setBearbeiten(null)}
                    />
                  </div>
                ) : (
                  <SubplanerKarte
                    key={eintrag.id}
                    eintrag={eintrag}
                    onBearbeiten={() => {
                      setBearbeiten(eintrag.id);
                      setNeuInPhase(null);
                    }}
                    onLoeschen={() => loeschen(eintrag)}
                  />
                )
              )}
            </div>

            {neuInPhase === phase && (
              <SubplanerFormular
                titel={`Neues Unternehmen in Phase ${phase}`}
                phase={phase}
                varianten={varianten}
                onSpeichern={async (daten) => {
                  await api.subplaner.create({ ...daten, phase } as SubplanerEingabe);
                  setNeuInPhase(null);
                  onAendern();
                }}
                onAbbrechen={() => setNeuInPhase(null)}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function SubplanerKarte({
  eintrag,
  onBearbeiten,
  onLoeschen,
}: {
  eintrag: Subplaner;
  onBearbeiten: () => void;
  onLoeschen: () => void;
}) {
  const ohneAdresse = eintrag.emails.length === 0;

  return (
    <Karte>
      <KarteKopf
        titel={eintrag.name}
        icon={Building2}
        unterzeile={eintrag.kuerzel || undefined}
        aktion={
          ohneAdresse ? (
            <Plakette art="warn">Adresse fehlt</Plakette>
          ) : (
            <Plakette art="ok">
              {eintrag.emails.length} Adresse
              {eintrag.emails.length === 1 ? "" : "n"}
            </Plakette>
          )
        }
      />
      <KarteInhalt className="flex flex-col gap-2">
        {ohneAdresse ? (
          <div className="inline-flex items-start gap-1.5 text-[12px] text-app-warn">
            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
            Ohne E-Mail-Adresse lässt sich kein Einzelabruf erzeugen.
          </div>
        ) : (
          eintrag.emails.map((adresse) => (
            <div
              key={adresse}
              className="inline-flex items-center gap-1.5 text-[12.5px] text-app-text"
            >
              <Mail size={13} className="shrink-0 text-app-text-leise" />
              <span className="truncate">{adresse}</span>
            </div>
          ))
        )}

        {eintrag.anrede && (
          <div className="inline-flex items-start gap-1.5 text-[12px] text-app-text-still">
            <User size={13} className="mt-0.5 shrink-0" />
            <span className="min-w-0">{eintrag.anrede}</span>
          </div>
        )}
        {eintrag.angebot_datum && (
          <div className="inline-flex items-center gap-1.5 text-[12px] text-app-text-still">
            <Calendar size={13} className="shrink-0" />
            Angebot vom {formatDatum(eintrag.angebot_datum)}
          </div>
        )}
        {eintrag.ordner && (
          <div className="inline-flex items-center gap-1.5 text-[12px] text-app-text-still">
            <FolderTree size={13} className="shrink-0" />
            <span className="truncate font-mono">{eintrag.ordner}</span>
          </div>
        )}

        <div className="flex justify-end gap-1 border-t border-app-linie pt-2">
          <button
            type="button"
            onClick={onBearbeiten}
            aria-label={`${eintrag.name} ändern`}
            className="cursor-pointer p-1.5 text-app-text-leise transition-colors hover:text-app-text"
          >
            <Pencil size={15} />
          </button>
          <button
            type="button"
            onClick={onLoeschen}
            aria-label={`${eintrag.name} löschen`}
            className="cursor-pointer p-1.5 text-app-text-leise transition-colors hover:text-app-gefahr"
          >
            <Trash2 size={15} />
          </button>
        </div>
      </KarteInhalt>
    </Karte>
  );
}

/**
 * Anlegen und Ändern in einem Formular.
 *
 * Die Adressen stehen in einem einzigen Feld, durch Komma oder Zeilenumbruch
 * getrennt. Eine dynamische Zeilenliste wäre hier mehr Bedienung für dasselbe
 * Ergebnis — man fügt Adressen ohnehin aus Outlook ein, und dort stehen sie
 * schon durch Semikolon getrennt.
 */
function SubplanerFormular({
  titel,
  phase,
  varianten,
  start,
  onSpeichern,
  onAbbrechen,
}: {
  titel: string;
  phase: number;
  varianten: { kennung: string; beschriftung: string }[];
  start?: Subplaner;
  onSpeichern: (daten: Partial<SubplanerEingabe>) => Promise<void>;
  onAbbrechen: () => void;
}) {
  const [name, setName] = useState(start?.name ?? "");
  const [kuerzel, setKuerzel] = useState(start?.kuerzel ?? "");
  const [ordner, setOrdner] = useState(start?.ordner ?? "");
  const [ansprechpartner, setAnsprechpartner] = useState(
    start?.ansprechpartner ?? ""
  );
  const [anrede, setAnrede] = useState(start?.anrede ?? "");
  const [adressen, setAdressen] = useState((start?.emails ?? []).join(", "));
  const [angebot, setAngebot] = useState(start?.angebot_datum ?? "");
  const [variante, setVariante] = useState(start?.textvariante ?? "rka");
  const [phaseWert, setPhaseWert] = useState(String(start?.phase ?? phase));
  const [speichert, setSpeichert] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  const bereit = name.trim() !== "";

  function adressliste(): string[] {
    return adressen
      .split(/[,;\n]/)
      .map((a) => a.trim())
      .filter(Boolean);
  }

  async function speichern() {
    if (!bereit) return;
    setSpeichert(true);
    setFehler(null);
    try {
      await onSpeichern({
        phase: Number(phaseWert),
        name: name.trim(),
        kuerzel: kuerzel.trim(),
        ordner: ordner.trim(),
        ansprechpartner: ansprechpartner.trim(),
        anrede: anrede.trim(),
        emails: adressliste(),
        angebot_datum: angebot || null,
        textvariante: variante,
      });
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Speichern fehlgeschlagen.");
    } finally {
      setSpeichert(false);
    }
  }

  return (
    <Karte>
      <KarteKopf titel={titel} icon={Building2} />
      <KarteInhalt className="flex flex-col gap-4">
        {fehler && <Meldung art="fehler">{fehler}</Meldung>}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Unternehmen (Pflicht)"
            hinweis="Wortgleich wie im Schreiben: „hiermit erteilen wir an …“."
          >
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z. B. Kocks Consult"
              autoFocus
            />
          </Field>
          <Field label="Kürzel" hinweis="Steht am Ende des Betreffs.">
            <Input
              value={kuerzel}
              onChange={(e) => setKuerzel(e.target.value.toUpperCase())}
              placeholder="KOCKS"
              className="font-mono"
            />
          </Field>
          <Field
            label="E-Mail-Adressen"
            hinweis="Mehrere durch Komma oder Semikolon trennen."
          >
            <Input
              value={adressen}
              onChange={(e) => setAdressen(e.target.value)}
              placeholder="name@firma.de, sekretariat@firma.de"
            />
          </Field>
          <Field label="Ansprechpartner">
            <Input
              value={ansprechpartner}
              onChange={(e) => setAnsprechpartner(e.target.value)}
              placeholder="Herr Hömmerich"
            />
          </Field>
          <Field
            label="Anredezeile"
            hinweis="Im Wortlaut — sie steht als erste Zeile im Schreiben."
          >
            <Input
              value={anrede}
              onChange={(e) => setAnrede(e.target.value)}
              placeholder="Sehr geehrter Herr Hömmerich,"
            />
          </Field>
          <Field
            label="Angebot vom"
            hinweis="„gemäß ihrem Angebot vom …“ — je Firma fest."
          >
            <Input
              type="date"
              value={angebot}
              onChange={(e) => setAngebot(e.target.value)}
            />
          </Field>
          <Field
            label="Vertragsordner"
            hinweis="Ordner unter 02_Subplaner — dorthin wird abgelegt."
          >
            <Input
              value={ordner}
              onChange={(e) => setOrdner(e.target.value)}
              placeholder="090_VAA_Kocks"
              className="font-mono"
            />
          </Field>
          <Field label="Phase">
            <Select
              value={phaseWert}
              onChange={(e) => setPhaseWert(e.target.value)}
            >
              {PHASEN.map((p) => (
                <option key={p} value={p}>
                  Phase {p}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Textfassung"
            hinweis="Welcher Wortlaut des Einzelabrufs benutzt wird."
            className="sm:col-span-2"
          >
            <Select
              value={variante}
              onChange={(e) => setVariante(e.target.value)}
            >
              {varianten.length === 0 && <option value="rka">Standard</option>}
              {varianten.map((v) => (
                <option key={v.kennung} value={v.kennung}>
                  {v.beschriftung}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="flex gap-2">
          <Button onClick={speichern} disabled={speichert || !bereit}>
            {speichert ? "Wird gespeichert…" : "Speichern"}
          </Button>
          <Button variante="still" icon={X} onClick={onAbbrechen}>
            Abbrechen
          </Button>
        </div>
      </KarteInhalt>
    </Karte>
  );
}
