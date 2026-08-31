"use client";

/**
 * Einen Fotosatz per E-Mail verschicken.
 *
 * ZWEI WEGE, WEIL DAS BÜRO GEMISCHT ARBEITET
 * ==========================================
 * • **Direkt senden** erscheint nur, wenn am Server ein Postausgangsserver
 *   hinterlegt ist. Sonst wäre der Knopf eine Falle: Der Kollege klickt und
 *   erfährt erst danach, dass nichts geht.
 * • **Outlook-Entwurf** funktioniert immer. Die App baut die vollständige Mail
 *   samt ZIP-Anhang als ``.eml``; das klassische Outlook öffnet sie als fertigen
 *   Entwurf, in dem nur noch "Senden" fehlt. Absender bleibt frei, damit Outlook
 *   das Konto des Kollegen nimmt.
 * • Darunter der Notausgang für das neue Outlook und die Browserfassung, die
 *   ``.eml`` nicht öffnen: Mailfenster per ``mailto:`` öffnen, ZIP daneben
 *   herunterladen, selbst anhängen.
 *
 * Die Empfängerliste kommt aus den Stammdaten (Empfänger **und** Firmen mit
 * Adresse) plus einem Freitextfeld — Bauherren und Sachverständige stehen
 * selten in den Stammdaten, und für einen einzelnen Versand soll man sie nicht
 * erst anlegen müssen.
 */

import {
  AlertTriangle,
  Building2,
  Check,
  FileArchive,
  Mail,
  Send,
  UserRound,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { dateiSpeichern, mailtoAdresse } from "@/lib/dateien";
import { formatBytes } from "@/lib/formate";
import type {
  Empfaenger,
  FotosatzListItem,
  FotosatzMailFaehigkeiten,
  FotosatzMailVorschlag,
  Gewerk,
} from "@/lib/types";
import { Button, Field, Input, Meldung, Textarea } from "@/components/ui";

/** Ein Vorschlag in der Empfängerliste. */
type Vorschlag = { email: string; label: string; art: "empfaenger" | "gewerk" };

/** Adressen aus einem Freitextfeld: Komma, Semikolon oder Zeilenumbruch. */
function adressenAus(text: string): string[] {
  return text
    .split(/[,;\n]/)
    .map((teil) => teil.trim())
    .filter(Boolean);
}

export function FotosatzMailDialog({
  satz,
  empfaenger,
  gewerke,
  onSchliessen,
  onVersendet,
}: {
  satz: FotosatzListItem;
  empfaenger: Empfaenger[];
  gewerke: Gewerk[];
  onSchliessen: () => void;
  /** Nach erfolgreichem Versand: Liste neu laden, damit der Vermerk erscheint. */
  onVersendet: () => void;
}) {
  const [faehig, setFaehig] = useState<FotosatzMailFaehigkeiten | null>(null);
  const [vorschlag, setVorschlag] = useState<FotosatzMailVorschlag | null>(null);
  const [gewaehlt, setGewaehlt] = useState<string[]>([]);
  const [weitere, setWeitere] = useState("");
  const [kopie, setKopie] = useState("");
  const [betreff, setBetreff] = useState("");
  const [text, setText] = useState("");
  const [laeuft, setLaeuft] = useState<"" | "senden" | "entwurf">("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [erfolg, setErfolg] = useState<string | null>(null);

  const vorschlaege: Vorschlag[] = useMemo(() => {
    const liste: Vorschlag[] = empfaenger
      .filter((e) => e.email)
      .map((e) => ({ email: e.email, label: e.label, art: "empfaenger" }));
    for (const gewerk of gewerke) {
      const adresse = (gewerk.email || "").trim();
      if (!adresse || liste.some((v) => v.email === adresse)) continue;
      liste.push({
        email: adresse,
        label: gewerk.firma_name || gewerk.vergabeeinheit_bezeichnung || adresse,
        art: "gewerk",
      });
    }
    return liste;
  }, [empfaenger, gewerke]);

  // Betreff und Text vom Server holen: derselbe Wortlaut wie bei einem
  // direkten API-Aufruf, und die Größe des Anhangs steht damit auch fest.
  useEffect(() => {
    let abgebrochen = false;
    (async () => {
      try {
        const [f, v] = await Promise.all([
          api.baufotos.mailFaehigkeiten(),
          api.baufotos.mailVorschlag(satz.id),
        ]);
        if (abgebrochen) return;
        setFaehig(f);
        setVorschlag(v);
        setBetreff(v.betreff);
        setText(v.nachricht);
      } catch (err) {
        if (!abgebrochen) {
          setFehler(err instanceof Error ? err.message : "Vorschlag nicht ladbar.");
        }
      }
    })();
    return () => {
      abgebrochen = true;
    };
  }, [satz.id]);

  const alleEmpfaenger = [...gewaehlt, ...adressenAus(weitere)];
  const kopieListe = adressenAus(kopie);
  const bereit = alleEmpfaenger.length > 0 && (vorschlag?.passt ?? false);

  function umschalten(adresse: string) {
    setGewaehlt((alt) =>
      alt.includes(adresse) ? alt.filter((a) => a !== adresse) : [...alt, adresse]
    );
  }

  function anfrage() {
    return {
      empfaenger: alleEmpfaenger,
      kopie: kopieListe,
      betreff: betreff.trim(),
      nachricht: text,
    };
  }

  function meldeFehler(err: unknown, standard: string) {
    if (err instanceof ApiError && typeof err.detail === "string") {
      setFehler(err.detail);
    } else {
      setFehler(err instanceof Error ? err.message : standard);
    }
  }

  async function direktSenden() {
    setFehler(null);
    setErfolg(null);
    setLaeuft("senden");
    try {
      const ergebnis = await api.baufotos.mailSenden(satz.id, anfrage());
      setErfolg(ergebnis.nachricht);
      onVersendet();
    } catch (err) {
      meldeFehler(err, "Versand fehlgeschlagen.");
    } finally {
      setLaeuft("");
    }
  }

  async function entwurfLaden() {
    setFehler(null);
    setErfolg(null);
    setLaeuft("entwurf");
    try {
      const { blob, dateiname } = await api.baufotos.mailEntwurf(satz.id, anfrage());
      dateiSpeichern(blob, dateiname || "baufotos.eml");
      setErfolg(
        "Entwurf erzeugt. Die Datei liegt in den Downloads — doppelklicken, " +
          "Outlook öffnet sie als fertige Mail mit Anhang."
      );
      onVersendet();
    } catch (err) {
      meldeFehler(err, "Entwurf konnte nicht erzeugt werden.");
    } finally {
      setLaeuft("");
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label={`Fotosatz ${satz.kategorie} per E-Mail verschicken`}
    >
      <div className="flex max-h-full w-full flex-col overflow-hidden rounded-t-app border border-app-linie bg-app-flaeche sm:max-w-[560px] sm:rounded-app">
        {/* Kopf */}
        <div className="flex items-center gap-2 border-b border-app-linie px-4 py-3">
          <Mail size={16} className="shrink-0 text-app-akzent" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13.5px] font-semibold text-app-text">
              Fotos per E-Mail
            </div>
            <div className="truncate text-[11.5px] text-app-text-still">
              {satz.kategorie} · {satz.anzahl_fotos} Foto(s)
            </div>
          </div>
          <button
            type="button"
            onClick={onSchliessen}
            aria-label="Schließen"
            className="cursor-pointer rounded-app-sm p-1.5 text-app-text-still transition-colors hover:bg-app-flaeche-still hover:text-app-text"
          >
            <X size={16} />
          </button>
        </div>

        {/* Inhalt */}
        <div className="flex flex-col gap-3 overflow-y-auto px-4 py-3">
          {fehler && <Meldung art="fehler">{fehler}</Meldung>}
          {erfolg && <Meldung art="erfolg">{erfolg}</Meldung>}

          {/* Anhang */}
          <div className="flex items-start gap-2.5 rounded-app-sm border border-app-linie bg-app-flaeche-still px-2.5 py-2">
            <FileArchive size={15} className="mt-0.5 shrink-0 text-app-text-still" />
            <div className="min-w-0 flex-1">
              <div className="font-mono text-[11.5px] break-all text-app-text">
                {vorschlag?.zip_dateiname ?? satz.zip_dateiname}
              </div>
              <div className="text-[11.5px] text-app-text-still">
                {formatBytes(vorschlag?.groesse_bytes ?? satz.groesse_bytes)} im Anhang
                {faehig && ` · Grenze ${faehig.max_anhang_mb} MB`}
              </div>
            </div>
          </div>

          {vorschlag && !vorschlag.passt && (
            <Meldung art="hinweis">
              <span className="flex items-start gap-2">
                <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                <span>{vorschlag.hinweis}</span>
              </span>
            </Meldung>
          )}

          {/* Empfänger aus den Stammdaten */}
          {vorschlaege.length > 0 && (
            <Field label="Empfänger aus den Stammdaten">
              <div className="flex max-h-[168px] flex-col gap-0.5 overflow-y-auto rounded-app-sm border border-app-linie p-1">
                {vorschlaege.map((v) => {
                  const aktiv = gewaehlt.includes(v.email);
                  const Symbol = v.art === "gewerk" ? Building2 : UserRound;
                  return (
                    <button
                      key={v.email}
                      type="button"
                      onClick={() => umschalten(v.email)}
                      className={`flex cursor-pointer items-center gap-2 rounded-app-sm px-2 py-1.5 text-left transition-colors ${
                        aktiv
                          ? "bg-app-akzent-sanft text-app-text"
                          : "hover:bg-app-flaeche-still"
                      }`}
                    >
                      <span
                        className={`flex size-4 shrink-0 items-center justify-center rounded-[3px] border ${
                          aktiv
                            ? "border-app-akzent bg-app-akzent text-app-akzent-text"
                            : "border-app-linie"
                        }`}
                      >
                        {aktiv && <Check size={11} strokeWidth={3} />}
                      </span>
                      <Symbol size={13} className="shrink-0 text-app-text-leise" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[12.5px] text-app-text">
                          {v.label}
                        </span>
                        <span className="block truncate text-[11px] text-app-text-still">
                          {v.email}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </Field>
          )}

          <Field
            label="Weitere Adressen"
            hinweis="Mehrere mit Komma trennen — Bauherr, Sachverständiger, Behörde."
          >
            <Input
              value={weitere}
              onChange={(e) => setWeitere(e.target.value)}
              placeholder="name@firma.de, zweite@firma.de"
              inputMode="email"
            />
          </Field>

          <Field label="Kopie an">
            <Input
              value={kopie}
              onChange={(e) => setKopie(e.target.value)}
              placeholder="ablage@hpp.com"
              inputMode="email"
            />
          </Field>

          <Field label="Betreff">
            <Input value={betreff} onChange={(e) => setBetreff(e.target.value)} />
          </Field>

          <Field label="Nachricht">
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={10}
              className="min-h-[180px] font-mono text-[11.5px]"
            />
          </Field>

          {/* Notausgang, wenn sich die .eml nicht öffnet */}
          <div className="rounded-app-sm border border-app-linie bg-app-flaeche-still px-2.5 py-2 text-[11.5px] text-app-text-still">
            Öffnet das neue Outlook oder Outlook im Browser die Entwurfsdatei
            nicht?{" "}
            <a
              href={mailtoAdresse(alleEmpfaenger, betreff, text)}
              className="text-app-akzent underline"
            >
              Mailfenster öffnen
            </a>{" "}
            und die{" "}
            <a
              href={api.baufotos.zipUrl(satz.id)}
              className="text-app-akzent underline"
            >
              ZIP-Datei
            </a>{" "}
            selbst anhängen.
          </div>
        </div>

        {/* Fußzeile */}
        <div className="flex flex-wrap items-center gap-2 border-t border-app-linie px-4 py-3">
          {faehig?.smtp && (
            <Button
              icon={Send}
              onClick={direktSenden}
              disabled={!bereit || laeuft !== ""}
            >
              {laeuft === "senden" ? "Wird gesendet…" : "Direkt senden"}
            </Button>
          )}
          <Button
            variante={faehig?.smtp ? "sekundaer" : "primaer"}
            icon={Mail}
            onClick={entwurfLaden}
            disabled={!bereit || laeuft !== ""}
          >
            {laeuft === "entwurf" ? "Wird erzeugt…" : "Outlook-Entwurf"}
          </Button>
          <div className="ml-auto flex items-center gap-2">
            {alleEmpfaenger.length === 0 && (
              <span className="text-[11.5px] text-app-text-still">
                Empfänger wählen
              </span>
            )}
            <Button variante="still" onClick={onSchliessen}>
              Schließen
            </Button>
          </div>
        </div>

        {faehig && !faehig.smtp && (
          <div className="border-t border-app-linie bg-app-flaeche-still px-4 py-2 text-[11px] text-app-text-still">
            Direktversand ist nicht eingerichtet (kein Postausgangsserver). Der
            Entwurfsweg braucht keinen — siehe desktop/README.md.
          </div>
        )}
        {faehig?.smtp && (
          <div className="border-t border-app-linie bg-app-flaeche-still px-4 py-2 text-[11px] text-app-text-still">
            Direktversand geht ab {faehig.absender || "dem hinterlegten Konto"}.
          </div>
        )}
      </div>
    </div>
  );
}
