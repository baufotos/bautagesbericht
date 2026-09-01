"use client";

/**
 * Firmen / Büros eines Projekts pflegen (Tabelle ``gewerke``).
 *
 * Die E-Mail-Adresse ist bewusst optional — genauso wie in der Bürosoftware,
 * in der ein Gewerk erst einmal ohne Adresse angelegt wird. Fehlt sie, sagt
 * die Liste das deutlich, denn davon hängt der Versand der Mängelrüge ab.
 */

import { AlertTriangle, Mail, MessageSquare, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";

import { api, konfliktAnzahl } from "@/lib/api";
import type { Gewerk } from "@/lib/types";
import {
  Bereichstitel,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Meldung,
} from "@/components/ui";

export function StammdatenGewerke({
  projektId,
  projektName,
  gewerke,
  onAendern,
}: {
  projektId: number;
  projektName: string;
  gewerke: Gewerk[];
  onAendern: () => void;
}) {
  const [formularOffen, setFormularOffen] = useState(false);
  const [firma, setFirma] = useState("");
  const [code, setCode] = useState("");
  const [bezeichnung, setBezeichnung] = useState("");
  const [email, setEmail] = useState("");
  // Postanschrift: Sie steht im Adressblock der Maengelanzeige. Einmal je
  // Firma eintragen, statt bei jedem Schreiben abzutippen.
  const [ansprechpartner, setAnsprechpartner] = useState("");
  const [strasse, setStrasse] = useState("");
  const [plz, setPlz] = useState("");
  const [ort, setOrt] = useState("");
  const [webhook, setWebhook] = useState("");
  const [speichert, setSpeichert] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [nachtragen, setNachtragen] = useState<number | null>(null);
  const [nachtragMail, setNachtragMail] = useState("");

  function zuruecksetzen() {
    setFirma("");
    setCode("");
    setBezeichnung("");
    setEmail("");
    setAnsprechpartner("");
    setStrasse("");
    setPlz("");
    setOrt("");
    setWebhook("");
    setFormularOffen(false);
  }

  async function anlegen() {
    if (!firma.trim()) return;
    setSpeichert(true);
    setFehler(null);
    try {
      await api.gewerke.create({
        projekt_id: projektId,
        firma_name: firma.trim(),
        vergabeeinheit_code: code.trim(),
        vergabeeinheit_bezeichnung: bezeichnung.trim(),
        email: email.trim(),
        ansprechpartner: ansprechpartner.trim(),
        strasse: strasse.trim(),
        plz: plz.trim(),
        ort: ort.trim(),
        teams_webhook_url: webhook.trim(),
      });
      zuruecksetzen();
      onAendern();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Speichern fehlgeschlagen");
    } finally {
      setSpeichert(false);
    }
  }

  async function mailNachtragen(gewerk: Gewerk) {
    setFehler(null);
    try {
      await api.gewerke.update(gewerk.id, { email: nachtragMail.trim() });
      setNachtragen(null);
      setNachtragMail("");
      onAendern();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Speichern fehlgeschlagen");
    }
  }

  async function loeschen(gewerk: Gewerk) {
    setFehler(null);
    try {
      await api.gewerke.delete(gewerk.id);
      onAendern();
      return;
    } catch (err) {
      const anzahl = konfliktAnzahl(err);
      if (anzahl === null) {
        setFehler(err instanceof Error ? err.message : "Löschen fehlgeschlagen");
        return;
      }
      const ok = window.confirm(
        `„${gewerk.anzeige_name}“ wird gelöscht.\n\n` +
          `Dazu gehören noch ${anzahl} Mangel/Mängel — diese bleiben erhalten, ` +
          `verlieren aber die Firmenzuordnung.\n\nWirklich löschen?`
      );
      if (!ok) return;
      try {
        await api.gewerke.delete(gewerk.id, true);
        onAendern();
      } catch (err2) {
        setFehler(err2 instanceof Error ? err2.message : "Löschen fehlgeschlagen");
      }
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <Bereichstitel
        aktion={
          !formularOffen ? (
            <Button icon={Plus} onClick={() => setFormularOffen(true)}>
              Firma anlegen
            </Button>
          ) : undefined
        }
      >
        Firmen / Büros · {projektName}
      </Bereichstitel>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {gewerke.length === 0 && !formularOffen && (
        <EmptyState>
          Noch keine Firmen für dieses Projekt. Eine Firma besteht aus Name und
          Vergabeeinheit, z. B. „Rolfes Bau GmbH“ mit „VE300-01 Erweiterter
          Rohbau“ — genau so erscheint sie später in der Mangel-Auswahl.
        </EmptyState>
      )}

      <div className="flex flex-col gap-1.5">
        {gewerke.map((gewerk) => (
          <Card key={gewerk.id} className="px-4 py-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[14.5px] font-semibold text-ui-text">
                  {gewerk.firma_name}
                </div>
                {(gewerk.vergabeeinheit_code || gewerk.vergabeeinheit_bezeichnung) && (
                  <div className="mt-0.5 font-mono text-[12px] text-ui-text-muted">
                    {[gewerk.vergabeeinheit_code, gewerk.vergabeeinheit_bezeichnung]
                      .filter(Boolean)
                      .join(" ")}
                  </div>
                )}
                <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px]">
                  {gewerk.email ? (
                    <span className="inline-flex items-center gap-1.5 text-ui-text-muted">
                      <Mail size={13} /> {gewerk.email}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 text-ui-danger">
                      <AlertTriangle size={13} /> keine E-Mail-Adresse — Versand
                      nur manuell
                    </span>
                  )}
                  {gewerk.teams_webhook_url && (
                    <span className="inline-flex items-center gap-1.5 text-ui-text-muted">
                      <MessageSquare size={13} /> Teams-Kanal hinterlegt
                    </span>
                  )}
                </div>

                {nachtragen === gewerk.id && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Input
                      type="email"
                      className="w-auto min-w-[240px]"
                      placeholder="E-Mail-Adresse der Firma"
                      value={nachtragMail}
                      onChange={(e) => setNachtragMail(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && mailNachtragen(gewerk)}
                    />
                    <Button onClick={() => mailNachtragen(gewerk)}>Übernehmen</Button>
                    <Button variante="still" onClick={() => setNachtragen(null)}>
                      Abbrechen
                    </Button>
                  </div>
                )}
              </div>

              <div className="flex shrink-0 items-center gap-1">
                {!gewerk.email && nachtragen !== gewerk.id && (
                  <Button
                    variante="sekundaer"
                    icon={Mail}
                    onClick={() => {
                      setNachtragen(gewerk.id);
                      setNachtragMail("");
                    }}
                  >
                    E-Mail nachtragen
                  </Button>
                )}
                <button
                  type="button"
                  onClick={() => loeschen(gewerk)}
                  aria-label={`${gewerk.firma_name} entfernen`}
                  className="cursor-pointer p-1.5 text-ui-text-faint transition-colors hover:text-ui-danger"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {formularOffen && (
        <Card className="flex flex-col gap-4 p-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Firma (Pflicht)">
              <Input
                value={firma}
                onChange={(e) => setFirma(e.target.value)}
                placeholder="z. B. Rolfes Bau GmbH"
                autoFocus
              />
            </Field>
            <Field label="Vergabeeinheit — Code">
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="z. B. VE300-01"
              />
            </Field>
            <Field label="Vergabeeinheit — Bezeichnung">
              <Input
                value={bezeichnung}
                onChange={(e) => setBezeichnung(e.target.value)}
                placeholder="z. B. Erweiterter Rohbau"
              />
            </Field>
            <Field
              label="E-Mail"
              hinweis="Voraussetzung für den Versand der Mängelrüge; kann später nachgetragen werden."
            >
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="optional"
              />
            </Field>
          </div>
          {/* Postanschrift — sie steht im Adressblock der Mängelanzeige und
              wird sonst nirgends gebraucht, deshalb ein eigener Block und
              durchgehend optional. */}
          <div className="rounded-ui border border-ui-line bg-ui-surface-muted px-3 py-2.5">
            <div className="mb-2 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ui-text-muted">
              Postanschrift für die Mängelanzeige
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Ansprechpartner" hinweis="Wie im Adressfeld: „Herrn Hey“.">
                <Input
                  value={ansprechpartner}
                  onChange={(e) => setAnsprechpartner(e.target.value)}
                  placeholder="optional"
                />
              </Field>
              <Field label="Straße und Hausnummer">
                <Input
                  value={strasse}
                  onChange={(e) => setStrasse(e.target.value)}
                  placeholder="optional"
                />
              </Field>
              <Field label="PLZ">
                <Input
                  value={plz}
                  onChange={(e) => setPlz(e.target.value)}
                  placeholder="optional"
                />
              </Field>
              <Field label="Ort">
                <Input
                  value={ort}
                  onChange={(e) => setOrt(e.target.value)}
                  placeholder="optional"
                />
              </Field>
            </div>
          </div>
          <Field
            label="Teams-Kanal-Webhook"
            hinweis="Optional: eigener Kanal dieser Firma. Ohne Eintrag greift der Kanal des Projekts."
          >
            <Input
              type="url"
              value={webhook}
              onChange={(e) => setWebhook(e.target.value)}
              placeholder="optional"
            />
          </Field>
          <div className="flex gap-2">
            <Button onClick={anlegen} disabled={speichert || !firma.trim()} icon={Plus}>
              Firma speichern
            </Button>
            <Button variante="still" icon={X} onClick={zuruecksetzen}>
              Abbrechen
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
