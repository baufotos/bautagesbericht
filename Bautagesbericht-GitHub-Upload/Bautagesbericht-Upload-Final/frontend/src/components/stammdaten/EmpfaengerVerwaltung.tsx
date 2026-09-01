"use client";

/**
 * Empfänger der Bautagesberichte pflegen.
 *
 * Wichtig zum Verständnis: Fertige Berichte stehen **immer** in der Übersicht
 * zum Download. Die hier hinterlegte E-Mail-Adresse ist Kontaktinformation, der
 * Teams-Kanal die einzige aktive Benachrichtigung — auf dem kostenlosen
 * Hosting-Plan ist ausgehendes SMTP gesperrt. Das steht auch im Formular, damit
 * niemand auf eine Mail wartet, die nicht kommt.
 */

import { Mail, MessageSquare, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { loeschenMitRueckfrage } from "@/lib/loeschen";
import type { Empfaenger } from "@/lib/types";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  LeerHinweis,
  Plakette,
} from "@/components/dashboard";
import { Button, Field, Input, Meldung } from "@/components/ui";

export function EmpfaengerVerwaltung({
  empfaenger,
  onAendern,
}: {
  empfaenger: Empfaenger[];
  onAendern: () => void;
}) {
  const [formularOffen, setFormularOffen] = useState(false);
  const [label, setLabel] = useState("");
  const [email, setEmail] = useState("");
  const [webhook, setWebhook] = useState("");
  const [speichert, setSpeichert] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  function zuruecksetzen() {
    setLabel("");
    setEmail("");
    setWebhook("");
    setFormularOffen(false);
  }

  async function anlegen() {
    if (!label.trim() || !email.trim()) return;
    setSpeichert(true);
    setFehler(null);
    try {
      await api.empfaenger.create({
        label: label.trim(),
        email: email.trim(),
        teams_webhook_url: webhook.trim(),
      });
      zuruecksetzen();
      onAendern();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Speichern fehlgeschlagen.");
    } finally {
      setSpeichert(false);
    }
  }

  async function loeschen(eintrag: Empfaenger) {
    setFehler(null);
    const problem = await loeschenMitRueckfrage(
      (force) => api.empfaenger.delete(eintrag.id, force),
      `Empfänger „${eintrag.label}“`,
      "Die zugehörigen Einreichungen werden mit entfernt, inklusive der erzeugten Word-Dokumente."
    );
    if (problem) setFehler(problem);
    onAendern();
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-0 flex-1 text-[12.5px] text-app-text-still">
          Für wen werden Bautagesberichte eingereicht? Fertige Berichte stehen
          immer in der Übersicht — ein hinterlegter Teams-Kanal meldet sie
          zusätzlich aktiv.
        </p>
        {!formularOffen && (
          <Button icon={Plus} onClick={() => setFormularOffen(true)}>
            Empfänger anlegen
          </Button>
        )}
      </div>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {empfaenger.length === 0 && !formularOffen && (
        <LeerHinweis>
          Noch keine Empfänger angelegt. Ohne Empfänger lässt sich kein
          Bautagesbericht einreichen.
        </LeerHinweis>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {empfaenger.map((eintrag) => (
          <Karte key={eintrag.id}>
            <KarteKopf
              titel={eintrag.label}
              icon={Mail}
              aktion={
                eintrag.teams_webhook_url ? (
                  <Plakette art="ok">Teams</Plakette>
                ) : (
                  <Plakette art="neutral">nur Übersicht</Plakette>
                )
              }
            />
            <KarteInhalt className="flex flex-col gap-2">
              <div className="truncate text-[12.5px] text-app-text">{eintrag.email}</div>
              {eintrag.teams_webhook_url && (
                <div className="inline-flex items-center gap-1.5 text-[12px] text-app-text-still">
                  <MessageSquare size={13} /> Teams-Kanal hinterlegt
                </div>
              )}
              <div className="flex justify-end border-t border-app-linie pt-2">
                <button
                  type="button"
                  onClick={() => loeschen(eintrag)}
                  aria-label={`Empfänger ${eintrag.label} löschen`}
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
          <KarteKopf titel="Neuer Empfänger" icon={Plus} />
          <KarteInhalt className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Bezeichnung (Pflicht)">
                <Input
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="Name oder Rolle"
                  onKeyDown={(e) => e.key === "Enter" && anlegen()}
                  autoFocus
                />
              </Field>
              <Field
                label="E-Mail (Pflicht)"
                hinweis="Kontaktinformation — es wird von hier aus keine Mail versendet."
              >
                <Input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && anlegen()}
                />
              </Field>
            </div>
            <Field
              label="Teams-Kanal-Webhook (optional)"
              hinweis="Kanal → „…“ → Workflows → „Send webhook alerts to a channel“ → Link kopieren."
            >
              <Input
                type="url"
                value={webhook}
                onChange={(e) => setWebhook(e.target.value)}
                placeholder="optional"
              />
            </Field>
            <div className="flex gap-2">
              <Button
                onClick={anlegen}
                disabled={speichert || !label.trim() || !email.trim()}
                icon={Plus}
              >
                Empfänger speichern
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
