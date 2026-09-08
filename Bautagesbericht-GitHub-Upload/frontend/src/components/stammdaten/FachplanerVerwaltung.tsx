"use client";

/**
 * Fachplaner-Unternehmen pflegen — die Auswahlliste der Beauftragung.
 *
 * Aufbau wie ``EmpfaengerVerwaltung``: Liste als Karten, Formular darunter,
 * Löschen mit Rückfrage. Ein Unterschied ist wichtig und steht auch im
 * Formular: Die hier hinterlegte E-Mail-Adresse ist keine Kontaktinformation,
 * sondern der **Empfänger des Outlook-Entwurfs** (siehe
 * components/mcdonalds/AngebotErstellen). Ein Tippfehler fällt sonst erst
 * auf, wenn die Mail zurückkommt.
 *
 * Wer Angebote hat, bleibt stehen: Der Server lehnt das Löschen mit 409 ab,
 * damit nachvollziehbar bleibt, an wen sie gingen.
 */

import { Building2, Mail, MapPin, Plus, Trash2, User, X } from "lucide-react";
import { useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { Fachplaner } from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  LeerHinweis,
} from "@/components/dashboard";
import { Button, Field, Input, Meldung } from "@/components/ui";

export function FachplanerVerwaltung({
  fachplaner,
  onAendern,
}: {
  fachplaner: Fachplaner[];
  onAendern: () => void;
}) {
  const [formularOffen, setFormularOffen] = useState(false);
  const [name, setName] = useState("");
  const [ansprechpartner, setAnsprechpartner] = useState("");
  const [email, setEmail] = useState("");
  const [adresse, setAdresse] = useState("");
  const [speichert, setSpeichert] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  const bereit = name.trim() !== "" && email.trim() !== "";

  function zuruecksetzen() {
    setName("");
    setAnsprechpartner("");
    setEmail("");
    setAdresse("");
    setFormularOffen(false);
  }

  async function anlegen() {
    if (!bereit) return;
    setSpeichert(true);
    setFehler(null);
    try {
      await api.fachplaner.create({
        name: name.trim(),
        ansprechpartner: ansprechpartner.trim(),
        email: email.trim(),
        adresse: adresse.trim(),
      });
      zuruecksetzen();
      onAendern();
    } catch (err) {
      setFehler(
        err instanceof Error ? err.message : "Speichern fehlgeschlagen."
      );
    } finally {
      setSpeichert(false);
    }
  }

  async function loeschen(eintrag: Fachplaner) {
    setFehler(null);
    if (
      !window.confirm(
        `„${eintrag.name}“ aus den Stammdaten entfernen?\n\n` +
          "Bereits erstellte Angebote bleiben erhalten."
      )
    ) {
      return;
    }
    try {
      await api.fachplaner.delete(eintrag.id);
      onAendern();
    } catch (err) {
      // Der Server lehnt mit 409 ab, wenn Angebote daran hängen — seine
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
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-0 flex-1 text-[12.5px] text-app-text-still">
          Planungsbüros, die im McDonald&apos;s-Ablauf beauftragt werden. Die
          hinterlegte Adresse ist der Empfänger des Outlook-Entwurfs — sie
          gehört geprüft, bevor das erste Angebot herausgeht.
        </p>
        {!formularOffen && (
          <Button icon={Plus} onClick={() => setFormularOffen(true)}>
            Fachplaner anlegen
          </Button>
        )}
      </div>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {fachplaner.length === 0 && !formularOffen && (
        <LeerHinweis>
          Noch keine Fachplaner angelegt. Ohne mindestens einen Eintrag lässt
          sich kein Angebot erstellen.
        </LeerHinweis>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {fachplaner.map((eintrag) => (
          <Karte key={eintrag.id}>
            <KarteKopf titel={eintrag.name} icon={Building2} />
            <KarteInhalt className="flex flex-col gap-2">
              <div className="inline-flex items-center gap-1.5 text-[12.5px] text-app-text">
                <Mail size={13} className="shrink-0 text-app-text-leise" />
                <span className="truncate">{eintrag.email}</span>
              </div>
              {eintrag.ansprechpartner && (
                <div className="inline-flex items-center gap-1.5 text-[12px] text-app-text-still">
                  <User size={13} className="shrink-0" />
                  <span className="truncate">{eintrag.ansprechpartner}</span>
                </div>
              )}
              {eintrag.adresse && (
                <div className="inline-flex items-center gap-1.5 text-[12px] text-app-text-still">
                  <MapPin size={13} className="shrink-0" />
                  <span className="truncate">{eintrag.adresse}</span>
                </div>
              )}
              <div className="flex justify-end border-t border-app-linie pt-2">
                <button
                  type="button"
                  onClick={() => loeschen(eintrag)}
                  aria-label={`Fachplaner ${eintrag.name} löschen`}
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
          <KarteKopf titel="Neuer Fachplaner" icon={Plus} />
          <KarteInhalt className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Unternehmen (Pflicht)">
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="z. B. Ingenieurbüro Müller GmbH"
                  onKeyDown={(e) => e.key === "Enter" && anlegen()}
                  autoFocus
                />
              </Field>
              <Field
                label="E-Mail (Pflicht)"
                hinweis="Empfänger des Outlook-Entwurfs."
              >
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && anlegen()}
                />
              </Field>
              <Field
                label="Ansprechpartner (optional)"
                hinweis="Wird als Anrede in den Mailtext übernommen."
              >
                <Input
                  value={ansprechpartner}
                  onChange={(e) => setAnsprechpartner(e.target.value)}
                  placeholder="z. B. Frau Stark"
                  onKeyDown={(e) => e.key === "Enter" && anlegen()}
                />
              </Field>
              <Field label="Anschrift (optional)">
                <Input
                  value={adresse}
                  onChange={(e) => setAdresse(e.target.value)}
                  placeholder="Straße, PLZ Ort"
                  onKeyDown={(e) => e.key === "Enter" && anlegen()}
                />
              </Field>
            </div>
            <div className="flex gap-2">
              <Button onClick={anlegen} disabled={speichert || !bereit} icon={Plus}>
                Fachplaner speichern
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
