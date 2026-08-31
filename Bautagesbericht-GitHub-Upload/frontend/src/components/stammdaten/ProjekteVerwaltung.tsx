"use client";

/**
 * Projekte pflegen — der Dreh- und Angelpunkt der ganzen App.
 *
 * Am Projekt hängen Bautagesberichte, Mängel, Firmen, Pläne und Baufotos.
 * Deshalb steht auf jeder Karte, was daran hängt, und das Löschen fragt zurück,
 * statt eine halbe Bauakte stillschweigend mitzunehmen.
 *
 * Die Adresse ist nicht Zierde: Aus ihr werden beim Anlegen die Koordinaten
 * bestimmt, mit denen der Bautagesbericht die Wetterdaten des Tages holt.
 *
 * Der Fotoordner ebenso wenig: Er sagt dem Abholskript im Büro, in welchen
 * Ordner auf dem Netzlaufwerk die vom Handy hochgeladenen Baufotos gehören.
 * Jedes Projekt liegt woanders, deshalb steht der Pfad hier am Projekt und
 * nicht in einer Textdatei auf jedem einzelnen Rechner.
 */

import {
  Check,
  FolderTree,
  MapPin,
  MessageSquare,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { loeschenMitRueckfrage } from "@/lib/loeschen";
import { formatDatumIso } from "@/lib/formate";
import type { Projekt } from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  LeerHinweis,
  Plakette,
} from "@/components/dashboard";
import { Button, Field, Input, Meldung } from "@/components/ui";

export function ProjekteVerwaltung({
  projekte,
  onAendern,
}: {
  projekte: Projekt[];
  onAendern: () => void;
}) {
  const [formularOffen, setFormularOffen] = useState(false);
  const [name, setName] = useState("");
  const [adresse, setAdresse] = useState("");
  const [webhook, setWebhook] = useState("");
  const [zielpfad, setZielpfad] = useState("");
  const [speichert, setSpeichert] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  // Welche Karte gerade ihren Fotoordner bearbeitet. Der Pfad wird selten
  // beim Anlegen schon feststehen, deshalb ist er auch nachträglich änderbar.
  const [bearbeitet, setBearbeitet] = useState<number | null>(null);
  const [pfadEntwurf, setPfadEntwurf] = useState("");

  function zuruecksetzen() {
    setName("");
    setAdresse("");
    setWebhook("");
    setZielpfad("");
    setFormularOffen(false);
  }

  async function pfadSpeichern(projekt: Projekt) {
    setSpeichert(true);
    setFehler(null);
    try {
      await api.projekte.update(projekt.id, { foto_zielpfad: pfadEntwurf.trim() });
      setBearbeitet(null);
      onAendern();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Speichern fehlgeschlagen.");
    } finally {
      setSpeichert(false);
    }
  }

  async function anlegen() {
    if (!name.trim()) return;
    setSpeichert(true);
    setFehler(null);
    try {
      await api.projekte.create({
        name: name.trim(),
        adresse: adresse.trim(),
        teams_webhook_url: webhook.trim(),
        foto_zielpfad: zielpfad.trim(),
      });
      zuruecksetzen();
      onAendern();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Speichern fehlgeschlagen.");
    } finally {
      setSpeichert(false);
    }
  }

  async function loeschen(projekt: Projekt) {
    setFehler(null);
    const problem = await loeschenMitRueckfrage(
      (force) => api.projekte.delete(projekt.id, force),
      `Projekt „${projekt.name}“`,
      "Berichte, Mängel, Firmen, Pläne und Baufotos dieses Projekts werden mit entfernt."
    );
    if (problem) setFehler(problem);
    onAendern();
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-0 flex-1 text-[12.5px] text-app-text-still">
          Ein Projekt einmal anlegen — danach ist es oben in der Kopfzeile
          wählbar und gilt für Baufotos, Mängel und Bautagesberichte.
        </p>
        {!formularOffen && (
          <Button icon={Plus} onClick={() => setFormularOffen(true)}>
            Projekt anlegen
          </Button>
        )}
      </div>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {projekte.length === 0 && !formularOffen && (
        <LeerHinweis>
          Noch kein Projekt angelegt. Name und Adresse genügen — die Adresse
          wird für den automatischen Wetterdaten-Abruf gebraucht.
        </LeerHinweis>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {projekte.map((projekt) => (
          <Karte key={projekt.id}>
            <KarteKopf
              titel={projekt.name}
              unterzeile={
                projekt.erstellt_am
                  ? `angelegt ${formatDatumIso(projekt.erstellt_am.slice(0, 10))}`
                  : undefined
              }
              icon={MapPin}
              aktion={
                projekt.lat && projekt.lon ? (
                  <Plakette art="ok">Wetter aktiv</Plakette>
                ) : (
                  <Plakette art="warn">ohne Standort</Plakette>
                )
              }
            />
            <KarteInhalt className="flex flex-col gap-2">
              <div className="text-[12.5px] text-app-text">
                {projekt.adresse || (
                  <span className="text-app-text-leise">keine Adresse hinterlegt</span>
                )}
              </div>
              {projekt.lat && projekt.lon && (
                <div className="font-mono text-[11px] text-app-text-leise">
                  {projekt.lat.toFixed(4)}, {projekt.lon.toFixed(4)}
                </div>
              )}
              {projekt.teams_webhook_url && (
                <div className="inline-flex items-center gap-1.5 text-[12px] text-app-text-still">
                  <MessageSquare size={13} /> Teams-Kanal hinterlegt
                </div>
              )}

              {bearbeitet === projekt.id ? (
                <div className="flex flex-col gap-2 rounded-md bg-app-flaeche-still p-2">
                  <label className="text-[11.5px] text-app-text-still">
                    Fotoordner im Netzlaufwerk
                  </label>
                  <Input
                    value={pfadEntwurf}
                    onChange={(e) => setPfadEntwurf(e.target.value)}
                    placeholder={`L:\\Bauleitung-Hamburg\\${projekt.name}\\01 FOTOS`}
                    onKeyDown={(e) => e.key === "Enter" && pfadSpeichern(projekt)}
                    autoFocus
                  />
                  <div className="flex gap-2">
                    <Button
                      icon={Check}
                      onClick={() => pfadSpeichern(projekt)}
                      disabled={speichert}
                    >
                      Speichern
                    </Button>
                    <Button variante="still" icon={X} onClick={() => setBearbeitet(null)}>
                      Abbrechen
                    </Button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setPfadEntwurf(projekt.foto_zielpfad || "");
                    setBearbeitet(projekt.id);
                  }}
                  className="group flex cursor-pointer items-start gap-1.5 text-left text-[12px] text-app-text-still transition-colors hover:text-app-text"
                  title="Fotoordner im Netzlaufwerk festlegen"
                >
                  <FolderTree size={13} className="mt-0.5 shrink-0" />
                  <span className="min-w-0 flex-1 break-all font-mono text-[11px]">
                    {projekt.foto_zielpfad || (
                      <span className="font-sans text-app-text-leise">
                        Fotoordner nicht festgelegt
                      </span>
                    )}
                  </span>
                  <Pencil
                    size={12}
                    className="mt-0.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-70"
                  />
                </button>
              )}

              <div className="flex justify-end border-t border-app-linie pt-2">
                <button
                  type="button"
                  onClick={() => loeschen(projekt)}
                  aria-label={`Projekt ${projekt.name} löschen`}
                  className="cursor-pointer p-1.5 text-app-text-leise transition-colors hover:text-app-gefahr"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </KarteInhalt>
          </Karte>
        ))}
      </div>

      {formularOffen && (
        <Karte>
          <KarteKopf titel="Neues Projekt" icon={Plus} />
          <KarteInhalt className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Projektname / -nummer (Pflicht)">
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="z. B. 2451 Neubau Verwaltungsgebäude Süd"
                  onKeyDown={(e) => e.key === "Enter" && anlegen()}
                  autoFocus
                />
              </Field>
              <Field
                label="Adresse des Bauvorhabens"
                hinweis="Wird für den automatischen Wetterdaten-Abruf in Koordinaten umgerechnet."
              >
                <Input
                  value={adresse}
                  onChange={(e) => setAdresse(e.target.value)}
                  placeholder="z. B. Kaistraße 5, 40221 Düsseldorf"
                  onKeyDown={(e) => e.key === "Enter" && anlegen()}
                />
              </Field>
            </div>
            <Field
              label="Teams-Kanal-Webhook (optional)"
              hinweis="Meldungen zu Mängeln und Baufotos gehen hierhin, wenn bei der Firma kein eigener Kanal hinterlegt ist."
            >
              <Input
                type="url"
                value={webhook}
                onChange={(e) => setWebhook(e.target.value)}
                placeholder="optional"
              />
            </Field>
            <Field
              label="Fotoordner im Netzlaufwerk (optional)"
              hinweis="Dorthin legt das Abholskript im Büro die vom Handy hochgeladenen Baufotos. Lässt sich später jederzeit auf der Projektkarte ändern."
            >
              <Input
                value={zielpfad}
                onChange={(e) => setZielpfad(e.target.value)}
                placeholder={`L:\\Bauleitung-Hamburg\\${name || "Projektname"}\\01 FOTOS`}
              />
            </Field>
            <div className="flex gap-2">
              <Button onClick={anlegen} disabled={speichert || !name.trim()} icon={Plus}>
                Projekt speichern
              </Button>
              <Button variante="still" icon={X} onClick={zuruecksetzen}>
                Abbrechen
              </Button>
            </div>
          </KarteInhalt>
        </Karte>
      )}
    </div>
  );
}
