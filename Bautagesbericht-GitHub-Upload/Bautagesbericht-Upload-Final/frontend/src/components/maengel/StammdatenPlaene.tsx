"use client";

/**
 * Projektpläne verwalten — die Grundlage für "Plan auswählen" im Mangel.
 *
 * Hochgeladen werden PDF oder Bild. Die Vorschau zeigt die erste Seite, damit
 * beim Auswählen sofort klar ist, welcher Plan gemeint ist; bei mehrseitigen
 * PDF steht die Seitenzahl daneben.
 */

import { FileDown, Loader2, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { api, konfliktAnzahl } from "@/lib/api";
import type { ProjektPlan } from "@/lib/types";
import {
  Bereichstitel,
  Button,
  Card,
  EmptyState,
  LinkButton,
  Meldung,
} from "@/components/ui";

export function StammdatenPlaene({
  projektId,
  projektName,
  plaene,
  onAendern,
}: {
  projektId: number;
  projektName: string;
  plaene: ProjektPlan[];
  onAendern: () => void;
}) {
  const dateiRef = useRef<HTMLInputElement>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  async function hochladen(event: React.ChangeEvent<HTMLInputElement>) {
    const dateien = Array.from(event.target.files || []);
    event.target.value = "";
    if (dateien.length === 0) return;

    setLaeuft(true);
    setFehler(null);
    try {
      // Nacheinander, nicht parallel: Pläne sind groß, und auf einer schwachen
      // Verbindung kommen sequenzielle Uploads zuverlässiger durch.
      for (const datei of dateien) {
        await api.plaene.upload(projektId, datei);
      }
      onAendern();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Upload fehlgeschlagen");
    } finally {
      setLaeuft(false);
    }
  }

  async function loeschen(plan: ProjektPlan) {
    setFehler(null);
    try {
      await api.plaene.delete(plan.id);
      onAendern();
      return;
    } catch (err) {
      const anzahl = konfliktAnzahl(err);
      if (anzahl === null) {
        setFehler(err instanceof Error ? err.message : "Löschen fehlgeschlagen");
        return;
      }
      const ok = window.confirm(
        `„${plan.dateiname}“ wird gelöscht.\n\n` +
          `Auf diesem Plan sitzen ${anzahl} Mangel-Markierung(en) — sie gehen ` +
          `verloren, die Mängel selbst bleiben erhalten.\n\nWirklich löschen?`
      );
      if (!ok) return;
      try {
        await api.plaene.delete(plan.id, true);
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
          <Button
            icon={laeuft ? undefined : Upload}
            disabled={laeuft}
            onClick={() => dateiRef.current?.click()}
          >
            {laeuft ? (
              <>
                <Loader2 size={15} className="animate-spin" /> Wird übertragen…
              </>
            ) : (
              "Plan hochladen"
            )}
          </Button>
        }
      >
        Pläne · {projektName}
      </Bereichstitel>

      <input
        ref={dateiRef}
        type="file"
        multiple
        accept=".pdf,image/*,.heic,.heif,.avif,.tif,.tiff"
        className="hidden"
        onChange={hochladen}
      />

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {plaene.length === 0 ? (
        <EmptyState>
          Noch keine Pläne. Grundrisse als PDF oder Bild hochladen — danach kann
          im Mangel die Stelle direkt im Plan angetippt werden.
        </EmptyState>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {plaene.map((plan) => (
            <Card key={plan.id} className="overflow-hidden">
              <div className="aspect-[4/3] w-full overflow-hidden bg-ui-surface-muted">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={api.plaene.vorschauUrl(plan.id, 1)}
                  alt={plan.dateiname}
                  className="size-full object-contain"
                  loading="lazy"
                />
              </div>
              <div className="flex items-center gap-2 border-t border-ui-line px-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] text-ui-text">
                    {plan.dateiname}
                  </span>
                  <span className="block font-mono text-[11px] text-ui-text-muted">
                    {plan.seiten} Seite(n)
                  </span>
                </span>
                <LinkButton
                  href={api.plaene.dateiUrl(plan.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  variante="still"
                  icon={FileDown}
                  title="Originaldatei öffnen"
                />
                <button
                  type="button"
                  onClick={() => loeschen(plan)}
                  aria-label={`${plan.dateiname} löschen`}
                  className="cursor-pointer p-1.5 text-ui-text-faint transition-colors hover:text-ui-danger"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
