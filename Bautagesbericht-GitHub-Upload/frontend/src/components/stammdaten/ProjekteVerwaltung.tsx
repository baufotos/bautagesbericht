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
 * Weil eine Baustellenadresse selten sauber ist ("DESYUM, Notkestraße 85"),
 * ist das Nachschlagen mehrstufig und darf misslingen — deshalb ist der
 * Standort hier nicht nur Anzeige, sondern über StandortFeld auch
 * nachträglich such-, wähl- und eintippbar. Vorher stand bei einer völlig
 * richtigen Adresse „ohne Standort“, und es gab keinen Weg, das zu ändern.
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

import { StandortFeld } from "./StandortFeld";

import { api } from "@/lib/api";
import { loeschenMitRueckfrage } from "@/lib/loeschen";
import { formatDatumIso } from "@/lib/formate";
import type { Projekt } from "@/lib/types";
import { Karte, KarteInhalt, KarteKopf, LeerHinweis } from "@/components/dashboard";
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
  // Welche Karte gerade ihre Adresse bearbeitet.
  const [adresseBearbeitet, setAdresseBearbeitet] = useState<number | null>(null);
  const [adresseEntwurf, setAdresseEntwurf] = useState("");
  // Standort, den der Nutzer im Anlegen-Formular schon ausgewählt hat. Ist er
  // gesetzt, schlägt der Server die Adresse nicht mehr nach.
  const [neuLat, setNeuLat] = useState<number | null>(null);
  const [neuLon, setNeuLon] = useState<number | null>(null);

  function zuruecksetzen() {
    setName("");
    setAdresse("");
    setWebhook("");
    setZielpfad("");
    setNeuLat(null);
    setNeuLon(null);
    setFormularOffen(false);
  }

  async function adresseSpeichern(projekt: Projekt) {
    // Der Server schlägt bei geänderter Adresse selbst nach; steht dieselbe
    // Adresse noch einmal drin, wird das Nachschlagen ausdrücklich verlangt
    // — genau der Fall „war richtig, wurde trotzdem nicht gefunden“.
    await projektAendern(projekt, {
      adresse: adresseEntwurf.trim(),
      standort_neu_suchen: true,
    });
    setAdresseBearbeitet(null);
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

  /** Ein Feld der Projektkarte ändern und die Liste neu laden. */
  async function projektAendern(
    projekt: Projekt,
    daten: Parameters<typeof api.projekte.update>[1]
  ) {
    setSpeichert(true);
    setFehler(null);
    try {
      await api.projekte.update(projekt.id, daten);
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
        lat: neuLat,
        lon: neuLon,
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
            />
            <KarteInhalt className="flex flex-col gap-2">
              {/* Adresse: anklickbar wie der Fotoordner. Sie ist die Grundlage
                  des Standorts, also muss sie korrigierbar sein, ohne das
                  Projekt neu anzulegen. */}
              {adresseBearbeitet === projekt.id ? (
                <div className="flex flex-col gap-2 rounded-md bg-app-flaeche-still p-2">
                  <label className="text-[11.5px] text-app-text-still">
                    Adresse des Bauvorhabens
                  </label>
                  <Input
                    value={adresseEntwurf}
                    onChange={(e) => setAdresseEntwurf(e.target.value)}
                    placeholder="z. B. Notkestraße 85, 22607 Hamburg"
                    onKeyDown={(e) => e.key === "Enter" && adresseSpeichern(projekt)}
                    autoFocus
                  />
                  <p className="text-[11.5px] text-app-text-leise">
                    Mit Postleitzahl und Ort — daran findet der Kartendienst die
                    Stelle. Zusätze wie „Baufeld 3“ davor stören nicht.
                  </p>
                  <div className="flex gap-2">
                    <Button
                      icon={Check}
                      onClick={() => adresseSpeichern(projekt)}
                      disabled={speichert}
                    >
                      Speichern und Standort suchen
                    </Button>
                    <Button
                      variante="still"
                      icon={X}
                      onClick={() => setAdresseBearbeitet(null)}
                    >
                      Abbrechen
                    </Button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setAdresseEntwurf(projekt.adresse || "");
                    setAdresseBearbeitet(projekt.id);
                  }}
                  className="group flex cursor-pointer items-start gap-1.5 text-left text-[12.5px] text-app-text transition-colors hover:text-app-akzent"
                  title="Adresse ändern"
                >
                  <span className="min-w-0 flex-1">
                    {projekt.adresse || (
                      <span className="text-app-text-leise">
                        keine Adresse hinterlegt
                      </span>
                    )}
                  </span>
                  <Pencil
                    size={12}
                    className="mt-0.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-70"
                  />
                </button>
              )}

              <StandortFeld
                adresse={projekt.adresse}
                lat={projekt.lat}
                lon={projekt.lon}
                guete={projekt.standort_guete}
                label={projekt.standort_label}
                onWaehlen={(lat, lon) =>
                  projektAendern(
                    projekt,
                    lat === null || lon === null
                      ? { standort_entfernen: true }
                      : { lat, lon }
                  )
                }
              />

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
                hinweis="Mit Postleitzahl und Ort. Wird beim Speichern in Koordinaten umgerechnet — die braucht der Bautagesbericht für die Wetterdaten."
              >
                <Input
                  value={adresse}
                  onChange={(e) => {
                    setAdresse(e.target.value);
                    // Eine bereits getroffene Wahl passt nicht mehr zur neuen
                    // Adresse — sonst entstünde das Projekt mit dem Standort
                    // der alten.
                    setNeuLat(null);
                    setNeuLon(null);
                  }}
                  placeholder="z. B. Kaistraße 5, 40221 Düsseldorf"
                  onKeyDown={(e) => e.key === "Enter" && anlegen()}
                />
              </Field>
            </div>
            {/* Vor dem Speichern nachsehen, ob die Adresse gefunden wird.
                Erspart den Weg „anlegen, ohne Standort sehen, nachbessern“. */}
            <StandortFeld
              adresse={adresse}
              lat={neuLat}
              lon={neuLon}
              guete={neuLat === null ? "" : "manuell"}
              onWaehlen={(lat, lon) => {
                setNeuLat(lat);
                setNeuLon(lon);
              }}
            />
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
