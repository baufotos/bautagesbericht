"use client";

/**
 * Plan anzeigen und die Stecknadel setzen.
 *
 * Der Plan kommt vom Backend als Bild einer Seite (auch bei PDF, siehe
 * app/services/plan_vorschau.py). Getippt wird auf dieses Bild; gespeichert
 * wird die Position in **Prozent** der Bildfläche. Deshalb sitzt die Nadel auf
 * dem Handy, auf dem Tablet und im Word-Export an derselben Stelle des Plans —
 * unabhängig von Bildschirmgröße und Zoomstufe.
 *
 * Zwei Schritte statt einem: Tippen setzt die Nadel nur vorläufig, erst
 * "Übernehmen" schreibt sie fest. Auf der Baustelle wird mit Handschuhen und
 * schmutzigem Display getippt — ein Fehlgriff soll keine vorhandene Markierung
 * überschreiben.
 */

import { ChevronLeft, ChevronRight, Crosshair, MapPin, Trash2, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { ProjektPlan } from "@/lib/types";
import { Button, EmptyState, Field, Select } from "@/components/ui";

export interface MarkierungsWert {
  plan_datei_id: number;
  x_prozent: number;
  y_prozent: number;
  seite: number;
}

const ZOOMSTUFEN = [1, 1.75, 2.75];

export function PlanMarkierungFeld({
  plaene,
  wert,
  onWert,
  planName = "",
}: {
  plaene: ProjektPlan[];
  wert: MarkierungsWert | null;
  onWert: (wert: MarkierungsWert | null) => void;
  /** Dateiname der gespeicherten Markierung (für die Kopfzeile). */
  planName?: string;
}) {
  const [planId, setPlanId] = useState<number | null>(
    wert?.plan_datei_id ?? plaene[0]?.id ?? null
  );
  const [seite, setSeite] = useState(wert?.seite ?? 1);
  const [entwurf, setEntwurf] = useState<{ x: number; y: number } | null>(null);
  const [zoomIndex, setZoomIndex] = useState(0);

  // Wechselt der Mangel (oder wird die Markierung gespeichert), muss die
  // Ansicht der neuen Vorgabe folgen. Bewusst auf die einzelnen Werte
  // gehorcht und nicht auf das Objekt: Sonst würde jedes Neuzeichnen des
  // Elternteils die gerade gesetzte, noch nicht übernommene Nadel verwerfen.
  const vorgabePlan = wert?.plan_datei_id ?? plaene[0]?.id ?? null;
  const vorgabeSeite = wert?.seite ?? 1;
  useEffect(() => {
    setPlanId(vorgabePlan);
    setSeite(vorgabeSeite);
    setEntwurf(null);
  }, [vorgabePlan, vorgabeSeite, wert?.x_prozent, wert?.y_prozent]);

  const plan = plaene.find((p) => p.id === planId) || null;
  const zoom = ZOOMSTUFEN[zoomIndex];

  if (plaene.length === 0) {
    return (
      <EmptyState>
        Für dieses Projekt sind noch keine Pläne hinterlegt. Unter
        „Stammdaten → Pläne“ lassen sich Grundrisse als PDF oder Bild
        hochladen — danach kann die Stelle hier direkt angetippt werden.
      </EmptyState>
    );
  }

  const gespeichertHier =
    wert && plan && wert.plan_datei_id === plan.id && wert.seite === seite;
  const nadel = entwurf
    ? { x: entwurf.x, y: entwurf.y, vorlaeufig: true }
    : gespeichertHier
    ? { x: wert.x_prozent, y: wert.y_prozent, vorlaeufig: false }
    : null;

  function tippen(event: React.MouseEvent<HTMLDivElement>) {
    const flaeche = event.currentTarget.getBoundingClientRect();
    if (!flaeche.width || !flaeche.height) return;
    const x = ((event.clientX - flaeche.left) / flaeche.width) * 100;
    const y = ((event.clientY - flaeche.top) / flaeche.height) * 100;
    setEntwurf({
      x: Math.min(100, Math.max(0, Number(x.toFixed(2)))),
      y: Math.min(100, Math.max(0, Number(y.toFixed(2)))),
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="text-[13px] text-ui-text-muted">
        {wert ? (
          <span className="inline-flex items-center gap-1.5 text-ui-text">
            <MapPin size={14} className="text-ui-accent" />
            {planName || plaene.find((p) => p.id === wert.plan_datei_id)?.dateiname}
            {" · "}Seite {wert.seite}
            {" · "}
            {wert.x_prozent.toFixed(0)} % / {wert.y_prozent.toFixed(0)} %
          </span>
        ) : (
          "Es ist keine Markierung vorhanden."
        )}
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <Field label="Plan auswählen" className="min-w-[240px] flex-1">
          <Select
            value={planId ?? ""}
            onChange={(e) => {
              setPlanId(Number(e.target.value));
              setSeite(1);
              setEntwurf(null);
            }}
          >
            {plaene.map((p) => (
              <option key={p.id} value={p.id}>
                {p.dateiname}
                {p.seiten > 1 ? ` (${p.seiten} Seiten)` : ""}
              </option>
            ))}
          </Select>
        </Field>

        {plan && plan.seiten > 1 && (
          <div className="flex items-center gap-1">
            <Button
              variante="sekundaer"
              icon={ChevronLeft}
              onClick={() => {
                setSeite((s) => Math.max(1, s - 1));
                setEntwurf(null);
              }}
              disabled={seite <= 1}
              aria-label="Vorherige Seite"
            >
            </Button>
            <span className="px-1 font-mono text-[11px] text-ui-text-muted">
              {seite} / {plan.seiten}
            </span>
            <Button
              variante="sekundaer"
              icon={ChevronRight}
              onClick={() => {
                setSeite((s) => Math.min(plan.seiten, s + 1));
                setEntwurf(null);
              }}
              disabled={seite >= plan.seiten}
              aria-label="Nächste Seite"
            >
            </Button>
          </div>
        )}

        <div className="flex items-center gap-1">
          <Button
            variante="sekundaer"
            icon={ZoomOut}
            onClick={() => setZoomIndex((i) => Math.max(0, i - 1))}
            disabled={zoomIndex === 0}
            aria-label="Kleiner"
          >
          </Button>
          <Button
            variante="sekundaer"
            icon={ZoomIn}
            onClick={() =>
              setZoomIndex((i) => Math.min(ZOOMSTUFEN.length - 1, i + 1))
            }
            disabled={zoomIndex === ZOOMSTUFEN.length - 1}
            aria-label="Größer"
          >
          </Button>
        </div>
      </div>

      {plan && (
        <div className="max-h-[68vh] overflow-auto rounded-ui border border-ui-line bg-ui-surface-muted">
          <div
            className="relative inline-block cursor-crosshair select-none"
            style={{ width: `${zoom * 100}%` }}
            onClick={tippen}
            role="presentation"
          >
            {/* Plan-Vorschau kommt als Bild vom eigenen Backend; next/image
                bringt hier keinen Vorteil und würde die Maßverhältnisse
                verkomplizieren. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              key={`${plan.id}-${seite}`}
              src={api.plaene.vorschauUrl(plan.id, seite)}
              alt={`${plan.dateiname}, Seite ${seite}`}
              className="block h-auto w-full"
              draggable={false}
            />
            {nadel && (
              <span
                className="pointer-events-none absolute -translate-x-1/2 -translate-y-full drop-shadow"
                style={{ left: `${nadel.x}%`, top: `${nadel.y}%` }}
              >
                <MapPin
                  size={30}
                  className={
                    nadel.vorlaeufig
                      ? "text-ui-warn"
                      : "text-ui-danger"
                  }
                  strokeWidth={2.2}
                  fill="currentColor"
                  fillOpacity={0.18}
                />
              </span>
            )}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-auto inline-flex items-center gap-1.5 text-[12px] text-ui-text-muted">
          <Crosshair size={13} />
          {entwurf
            ? `Vorläufige Position ${entwurf.x.toFixed(0)} % / ${entwurf.y.toFixed(0)} %`
            : "In den Plan tippen, um die Stelle zu markieren."}
        </span>
        {entwurf && plan && (
          <>
            <Button
              icon={MapPin}
              onClick={() =>
                onWert({
                  plan_datei_id: plan.id,
                  x_prozent: entwurf.x,
                  y_prozent: entwurf.y,
                  seite,
                })
              }
            >
              Markierung übernehmen
            </Button>
            <Button variante="still" onClick={() => setEntwurf(null)}>
              Verwerfen
            </Button>
          </>
        )}
        {!entwurf && wert && (
          <Button variante="gefahr" icon={Trash2} onClick={() => onWert(null)}>
            Markierung entfernen
          </Button>
        )}
      </div>
    </div>
  );
}
