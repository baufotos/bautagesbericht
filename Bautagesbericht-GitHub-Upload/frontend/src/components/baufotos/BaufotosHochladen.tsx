"use client";

/**
 * Baufotos hochladen — der Ablauf des bisherigen Windows-Werkzeugs, zentral.
 *
 * Der Nutzer gibt Kategorie und Datum an, wählt oder fotografiert, und bekommt
 * am Ende genau die ZIP-Datei, die er bisher per Outlook geschickt hat.
 *
 * ZWEI ENTSCHEIDUNGEN, DIE MAN IM CODE SEHEN SOLLTE
 * =================================================
 * 1. **Namensvorschau.** Noch vor dem Hochladen steht da, wie das Archiv und
 *    das erste Foto heißen werden. Diese Namen landen später in den
 *    Projektordnern des Büros — ein Tippfehler in der Kategorie fällt so vorher
 *    auf und nicht erst im Archiv. Die Vorschau rechnet mit derselben Regel wie
 *    das Backend; die Wahrheit bleibt aber dort (siehe services/baufotos.py).
 * 2. **Erst anlegen, dann einzeln senden.** Der Fotosatz entsteht mit einem
 *    winzigen JSON-Aufruf, die Fotos gehen danach einzeln raus. Bricht die
 *    Verbindung auf der Baustelle ab, ist höchstens ein Foto verloren — nicht
 *    der ganze Vorgang.
 */

import {
  Camera,
  CheckCircle2,
  FileArchive,
  Loader2,
  Mail,
  Send,
  Upload,
} from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { komprimiereBild } from "@/lib/bildkompression";
import { heuteIso } from "@/lib/formate";
import type { Empfaenger, Fotosatz, Gewerk, Projekt } from "@/lib/types";
import { Karte, KarteInhalt, KarteKopf, Plakette } from "@/components/dashboard";
import { Button, Field, Input, LinkButton, Meldung, Textarea } from "@/components/ui";
import { FotoAuswahl } from "@/components/maengel/FotoAufnahme";
import { FotosatzMailDialog } from "@/components/baufotos/FotosatzMailDialog";

/**
 * Wie viele Fotos ein Bautag auf einmal fassen darf.
 *
 * Ein Rundgang über eine Baustelle bringt 50 bis 80 Aufnahmen mit; wird hier
 * abgeschnitten, fehlt der halbe Tag im Projektordner. Der Wert entspricht
 * ``MAX_FOTOS_PRO_UPLOAD`` in services/baufotos.py — die Fotos gehen zwar
 * einzeln raus (siehe ``hochladen``), aber beide Grenzen sollen dieselbe
 * Aussage treffen, damit sie nicht auseinanderlaufen.
 */
const MAX_BAUFOTOS = 80;

/**
 * Dieselbe Bereinigung wie im Backend (``sanitize`` in services/baufotos.py):
 * Leerzeichen werden zu "_", Sonderzeichen fallen weg, Umlaute bleiben.
 * Hier NUR für die Vorschau — verbindlich ist der Server.
 */
function bereinige(wert: string): string {
  return (wert || "")
    .trim()
    .replace(/\s+/g, "_")
    .replace(/[^\wÀ-ſ-]/g, "");
}

/** "2026-08-19" → "260819" */
function datumStempel(iso: string): string {
  const [jahr, monat, tag] = (iso || "").slice(0, 10).split("-");
  if (!jahr || !monat || !tag) return "";
  return `${jahr.slice(2)}${monat}${tag}`;
}

interface Fortschritt {
  aktuell: number;
  gesamt: number;
}

export function BaufotosHochladen({
  projekt,
  kategorien,
  empfaenger,
  gewerke,
  onFertig,
}: {
  projekt: Projekt;
  /** Bisher benutzte Kategorien dieses Projekts — Vorschlag, keine Vorschrift. */
  kategorien: string[];
  /** Adressvorschläge für den Mailversand direkt nach dem Hochladen. */
  empfaenger: Empfaenger[];
  gewerke: Gewerk[];
  onFertig: (fotosatzId: number) => void;
}) {
  const [kategorie, setKategorie] = useState("");
  const [datum, setDatum] = useState(heuteIso());
  const [notiz, setNotiz] = useState("");
  const [fotos, setFotos] = useState<File[]>([]);

  const [laeuft, setLaeuft] = useState(false);
  const [fortschritt, setFortschritt] = useState<Fortschritt | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [warnung, setWarnung] = useState<string | null>(null);
  const [fertig, setFertig] = useState<{ id: number; zip: string; anzahl: number } | null>(
    null
  );
  const [meldung, setMeldung] = useState<string | null>(null);
  // Für den Mail-Dialog wird der fertige Satz nachgeladen: Er braucht
  // Kategorie, Größe und Archivname, und die Wahrheit dazu steht im Server.
  const [mailFuer, setMailFuer] = useState<Fotosatz | null>(null);

  const stempel = datumStempel(datum);
  const kategorieRein = bereinige(kategorie);
  const zipName =
    stempel && kategorieRein
      ? `${stempel}_${bereinige(projekt.name)}_${kategorieRein}.zip`
      : "";
  const ersterFotoName =
    stempel && kategorieRein ? `${stempel}_${kategorieRein}_1.jpg` : "";

  const kannSpeichern =
    kategorie.trim().length > 0 && datum.length === 10 && fotos.length > 0 && !laeuft;

  async function hochladen() {
    if (!kannSpeichern) return;
    setLaeuft(true);
    setFehler(null);
    setWarnung(null);
    setMeldung(null);

    try {
      // Schritt 1: Fotosatz anlegen — ab hier ist der Vorgang gesichert.
      const satz = await api.baufotos.create({
        projekt_id: projekt.id,
        kategorie: kategorie.trim(),
        datum,
        notiz: notiz.trim(),
      });

      // Schritt 2: Fotos einzeln, mit einem zweiten Versuch je Foto.
      let uebertragen = 0;
      const gescheitert: string[] = [];
      for (let i = 0; i < fotos.length; i++) {
        setFortschritt({ aktuell: i + 1, gesamt: fotos.length });
        // Vor dem Senden verkleinern: Das ist der Unterschied zwischen
        // "geht durch" und "läuft in den Zeitüberschreitung".
        const klein = await komprimiereBild(fotos[i]);
        let erfolg = false;
        for (let versuch = 1; versuch <= 2 && !erfolg; versuch++) {
          try {
            await api.baufotos.uploadFotos(satz.id, [klein]);
            erfolg = true;
            uebertragen += 1;
          } catch (err) {
            if (versuch === 2) {
              gescheitert.push(
                `${fotos[i].name}${
                  err instanceof Error ? ` (${err.message})` : ""
                }`
              );
            }
          }
        }
      }

      setFortschritt(null);

      if (uebertragen === 0) {
        // Kein einziges Foto angekommen: Der leere Fotosatz wäre nur Ballast.
        await api.baufotos.delete(satz.id).catch(() => undefined);
        setFehler(
          "Kein Foto konnte übertragen werden. Der Fotosatz wurde nicht angelegt — " +
            "bitte mit besserem Empfang erneut versuchen."
        );
        return;
      }

      if (gescheitert.length > 0) {
        setWarnung(
          `${gescheitert.length} von ${fotos.length} Foto(s) sind nicht angekommen ` +
            `(${gescheitert[0]}). Sie lassen sich in den Fotosätzen nachtragen.`
        );
      }

      const aktuell = await api.baufotos.get(satz.id);
      setFertig({
        id: satz.id,
        zip: aktuell.zip_dateiname,
        anzahl: aktuell.anzahl_fotos,
      });
      setFotos([]);
    } catch (err) {
      setFehler(
        err instanceof Error ? err.message : "Hochladen fehlgeschlagen."
      );
    } finally {
      setLaeuft(false);
      setFortschritt(null);
    }
  }

  async function melden(fotosatzId: number) {
    setMeldung(null);
    try {
      const ergebnis = await api.baufotos.melden(fotosatzId);
      setMeldung(ergebnis.nachricht);
    } catch (err) {
      setMeldung(err instanceof Error ? err.message : "Melden fehlgeschlagen.");
    }
  }

  /* ───────── Nach dem Hochladen ───────── */

  if (fertig) {
    return (
      <div className="flex flex-col gap-3">
        {warnung && <Meldung art="hinweis">{warnung}</Meldung>}
        <Karte>
          <KarteKopf
            titel="Fotosatz fertig"
            unterzeile={`${fertig.anzahl} Foto(s) umbenannt und verkleinert`}
            icon={CheckCircle2}
            aktion={<Plakette art="ok">Bereit</Plakette>}
          />
          <KarteInhalt className="flex flex-col gap-3">
            <div className="rounded-app-sm border border-app-linie bg-app-flaeche-still px-3 py-2.5">
              <div className="text-[10.5px] uppercase tracking-[0.1em] text-app-text-still">
                Archivname
              </div>
              <div className="mt-0.5 font-mono text-[12.5px] break-all text-app-text">
                {fertig.zip}
              </div>
            </div>

            <p className="text-[12.5px] text-app-text-still">
              Die ZIP-Datei wird bei jedem Abruf frisch gebaut — auch später,
              wenn Fotos nachgetragen wurden.
            </p>

            <div className="flex flex-wrap gap-2">
              <LinkButton
                href={api.baufotos.zipUrl(fertig.id)}
                icon={FileArchive}
                variante="primaer"
              >
                ZIP herunterladen
              </LinkButton>
              <Button
                variante="sekundaer"
                icon={Mail}
                onClick={async () => {
                  setMeldung(null);
                  try {
                    setMailFuer(await api.baufotos.get(fertig.id));
                  } catch (err) {
                    setFehler(
                      err instanceof Error ? err.message : "Fotosatz nicht ladbar."
                    );
                  }
                }}
              >
                Per Mail senden
              </Button>
              <Button variante="still" icon={Send} onClick={() => melden(fertig.id)}>
                In Teams melden
              </Button>
              <Button variante="still" onClick={() => onFertig(fertig.id)}>
                Zu den Fotosätzen
              </Button>
              <Button
                variante="still"
                onClick={() => {
                  setFertig(null);
                  setWarnung(null);
                  setMeldung(null);
                }}
              >
                Weiteren Satz erfassen
              </Button>
            </div>

            {meldung && <Meldung art="hinweis">{meldung}</Meldung>}
            {fehler && <Meldung art="fehler">{fehler}</Meldung>}
          </KarteInhalt>
        </Karte>

        {mailFuer && (
          <FotosatzMailDialog
            satz={mailFuer}
            empfaenger={empfaenger}
            gewerke={gewerke}
            onSchliessen={() => setMailFuer(null)}
            onVersendet={() => undefined}
          />
        )}
      </div>
    );
  }

  /* ───────── Erfassung ───────── */

  return (
    <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
      <div className="xl:col-span-2">
        <Karte>
          <KarteKopf
            titel="Fotos dieses Bautags"
            unterzeile={projekt.name}
            icon={Camera}
          />
          <KarteInhalt className="flex flex-col gap-4">
            {fehler && <Meldung art="fehler">{fehler}</Meldung>}

            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Kategorie (Pflicht)"
                hinweis="Steht im Dateinamen, z. B. Rohbau, Fenster EG, Abnahme Dach."
              >
                <Input
                  value={kategorie}
                  onChange={(e) => setKategorie(e.target.value)}
                  placeholder="z. B. Rohbau"
                  list="baufoto-kategorien"
                  autoFocus
                />
                {/* Vorschläge aus bisher benutzten Kategorien — frei überschreibbar */}
                <datalist id="baufoto-kategorien">
                  {kategorien.map((k) => (
                    <option key={k} value={k} />
                  ))}
                </datalist>
              </Field>

              <Field label="Aufnahmedatum" hinweis="Nicht der Upload-Tag — es steht im Namen.">
                <Input
                  type="date"
                  value={datum}
                  onChange={(e) => setDatum(e.target.value)}
                />
              </Field>
            </div>

            <Field label="Notiz (optional)" hinweis="Nur für die App, nicht im Dateinamen.">
              <Textarea
                value={notiz}
                onChange={(e) => setNotiz(e.target.value)}
                placeholder="z. B. Achse C, nach dem Ausschalen"
                className="min-h-[64px]"
              />
            </Field>

            <FotoAuswahl
              dateien={fotos}
              onChange={setFotos}
              maxFotos={MAX_BAUFOTOS}
              hinweis="Noch keine Fotos. Alles, was auf die Baustelle gehört — sie werden beim Hochladen umbenannt und verkleinert."
            />

            <div className="flex flex-wrap items-center gap-2 border-t border-app-linie pt-3">
              <Button
                onClick={hochladen}
                disabled={!kannSpeichern}
                icon={laeuft ? undefined : Upload}
              >
                {laeuft ? (
                  <>
                    <Loader2 size={15} className="animate-spin" />
                    {fortschritt
                      ? `Foto ${fortschritt.aktuell} von ${fortschritt.gesamt}…`
                      : "Wird angelegt…"}
                  </>
                ) : (
                  `${fotos.length || ""} Foto(s) hochladen`
                )}
              </Button>
              {!kannSpeichern && !laeuft && (
                <span className="text-[12px] text-app-text-still">
                  Kategorie, Datum und mindestens ein Foto werden gebraucht.
                </span>
              )}
            </div>
          </KarteInhalt>
        </Karte>
      </div>

      {/* Namensvorschau — die wichtigste Rückversicherung vor dem Hochladen */}
      <div>
        <Karte>
          <KarteKopf titel="So werden die Dateien heißen" icon={FileArchive} />
          <KarteInhalt className="flex flex-col gap-3">
            {zipName ? (
              <>
                <div>
                  <div className="text-[10.5px] uppercase tracking-[0.1em] text-app-text-still">
                    Archiv
                  </div>
                  <div className="mt-0.5 font-mono text-[12px] break-all text-app-text">
                    {zipName}
                  </div>
                </div>
                <div>
                  <div className="text-[10.5px] uppercase tracking-[0.1em] text-app-text-still">
                    Fotos
                  </div>
                  <div className="mt-0.5 font-mono text-[12px] break-all text-app-text">
                    {ersterFotoName}
                  </div>
                  {fotos.length > 1 && (
                    <div className="font-mono text-[12px] text-app-text-still">
                      … bis {stempel}_{kategorieRein}_{fotos.length}.jpg
                    </div>
                  )}
                </div>
              </>
            ) : (
              <p className="text-[12.5px] text-app-text-still">
                Kategorie und Datum eingeben — dann steht hier, wie das Archiv
                und die Fotos heißen werden.
              </p>
            )}

            <div className="border-t border-app-linie pt-3 text-[12px] leading-relaxed text-app-text-still">
              Es gelten dieselben Regeln wie im bisherigen Windows-Werkzeug:
              Datum als JJMMTT, Leerzeichen werden zu Unterstrichen, Umlaute
              bleiben. Jedes Foto wird auf 1600 px verkleinert (JPEG-Qualität
              70) — genau wie bisher.
            </div>
          </KarteInhalt>
        </Karte>
      </div>
    </div>
  );
}
