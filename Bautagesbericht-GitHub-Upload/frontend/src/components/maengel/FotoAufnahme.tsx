"use client";

/**
 * Fotos aufnehmen und auswählen.
 *
 * Zwei Bausteine:
 *   • ``FotoAuswahl``  — vor dem Speichern: die Dateien liegen noch lokal,
 *                        Vorschau aus dem Objekt-URL, einzeln entfernbar.
 *   • ``FotoGalerie``  — nach dem Speichern: die Fotos liegen am Mangel,
 *                        neue kommen sofort hoch, vorhandene sind löschbar.
 *
 * Zur Kamera: ``capture="environment"`` öffnet auf Handy und Tablet direkt die
 * rückseitige Kamera. Weil derselbe Knopf dann keine Galerie mehr anbietet,
 * gibt es bewusst zwei Knöpfe — auf der Baustelle wird fotografiert, im Büro
 * wird nachgereicht.
 */

import { Camera, ImagePlus, Loader2, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { formatiereGroesse } from "@/lib/bildkompression";
import { ladeFotosHoch } from "@/lib/fotoupload";
import type { MangelFoto } from "@/lib/types";
import { Button, EmptyState, Label, Meldung } from "@/components/ui";

const MAX_FOTOS = 20;

/* ───────── Auswahl vor dem Speichern ───────── */

export function FotoAuswahl({
  dateien,
  onChange,
  hinweis = "Noch keine Fotos. Für die Mängelrüge zählt vor allem, dass die Stelle erkennbar ist.",
}: {
  dateien: File[];
  onChange: (dateien: File[]) => void;
  /**
   * Text unter den Knöpfen, solange nichts gewählt ist. Als Prop, weil dieser
   * Baustein auch bei den Baufotos benutzt wird — dort geht es nicht um eine
   * Mängelrüge, und ein falscher Hinweis ist schlimmer als keiner.
   */
  hinweis?: string;
}) {
  const kameraRef = useRef<HTMLInputElement>(null);
  const galerieRef = useRef<HTMLInputElement>(null);
  const [vorschauen, setVorschauen] = useState<string[]>([]);

  useEffect(() => {
    const urls = dateien.map((datei) => URL.createObjectURL(datei));
    setVorschauen(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [dateien]);

  function hinzufuegen(event: React.ChangeEvent<HTMLInputElement>) {
    const neue = Array.from(event.target.files || []);
    onChange([...dateien, ...neue].slice(0, MAX_FOTOS));
    event.target.value = "";
  }

  return (
    <div>
      <Label>Fotos</Label>
      <div className="mt-1.5 flex gap-2">
        <Button
          type="button"
          variante="sekundaer"
          icon={Camera}
          onClick={() => kameraRef.current?.click()}
          className="flex-1"
        >
          Foto aufnehmen
        </Button>
        <Button
          type="button"
          variante="sekundaer"
          icon={ImagePlus}
          onClick={() => galerieRef.current?.click()}
          className="flex-1"
        >
          Aus Galerie
        </Button>
      </div>

      <input
        ref={kameraRef}
        type="file"
        accept="image/*,.heic,.heif,.avif,.tif,.tiff"
        capture="environment"
        multiple
        className="hidden"
        onChange={hinzufuegen}
      />
      <input
        ref={galerieRef}
        type="file"
        accept="image/*,.heic,.heif,.avif,.tif,.tiff"
        multiple
        className="hidden"
        onChange={hinzufuegen}
      />

      {dateien.length > 0 ? (
        <>
          <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
            {dateien.map((datei, i) => (
              <div
                key={`${datei.name}-${i}`}
                className="relative aspect-square overflow-hidden rounded-ui-sm border border-ui-line bg-ui-surface-muted"
              >
                {vorschauen[i] && (
                  // Lokale Objekt-URL: next/image kann damit nicht optimieren,
                  // deshalb bewusst ein einfaches img-Element.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={vorschauen[i]}
                    alt={`Foto ${i + 1}`}
                    className="size-full object-cover"
                  />
                )}
                <button
                  type="button"
                  onClick={() => onChange(dateien.filter((_, j) => j !== i))}
                  aria-label={`Foto ${i + 1} entfernen`}
                  className="absolute right-1 top-1 rounded-full bg-white/90 p-1 text-ui-text-muted hover:text-ui-danger cursor-pointer transition-colors"
                >
                  <X size={13} />
                </button>
                <span className="absolute inset-x-0 bottom-0 bg-black/45 px-1.5 py-0.5 text-[10px] text-white">
                  {formatiereGroesse(datei.size)}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[12px] text-ui-text-muted">
            {dateien.length} Foto(s) ausgewählt. Sie werden beim Speichern
            verkleinert und einzeln übertragen — das funktioniert auch bei
            schwacher Verbindung.
          </p>
        </>
      ) : (
        <p className="mt-2 text-[12px] text-ui-text-muted">{hinweis}</p>
      )}
    </div>
  );
}

/* ───────── Galerie eines gespeicherten Mangels ───────── */

export function FotoGalerie({
  mangelId,
  fotos,
  onAendern,
}: {
  mangelId: number;
  fotos: MangelFoto[];
  onAendern: () => void;
}) {
  const kameraRef = useRef<HTMLInputElement>(null);
  const galerieRef = useRef<HTMLInputElement>(null);
  const [laeuft, setLaeuft] = useState<string | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [gross, setGross] = useState<MangelFoto | null>(null);

  async function hochladen(event: React.ChangeEvent<HTMLInputElement>) {
    const neue = Array.from(event.target.files || []);
    event.target.value = "";
    if (neue.length === 0) return;

    setFehler(null);
    const ergebnis = await ladeFotosHoch(mangelId, neue, (stand) =>
      setLaeuft(`Foto ${stand.aktuell} von ${stand.gesamt} wird übertragen…`)
    );
    setLaeuft(null);
    if (ergebnis.fehlgeschlagen.length > 0) {
      setFehler(
        `${ergebnis.fehlgeschlagen.length} Foto(s) konnten nicht übertragen werden ` +
          `(${ergebnis.fehlgeschlagen[0].fehler}). Bitte erneut versuchen.`
      );
    }
    onAendern();
  }

  async function entfernen(foto: MangelFoto) {
    if (!window.confirm("Dieses Foto endgültig entfernen?")) return;
    try {
      await api.maengel.deleteFoto(foto.id);
      onAendern();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Löschen fehlgeschlagen");
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {fehler && <Meldung art="fehler">{fehler}</Meldung>}

      {fotos.length === 0 ? (
        <EmptyState>Noch keine Fotos zu diesem Mangel.</EmptyState>
      ) : (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {fotos.map((foto) => (
            <div
              key={foto.id}
              className="relative aspect-square overflow-hidden rounded-ui-sm border border-ui-line bg-ui-surface-muted"
            >
              <button
                type="button"
                onClick={() => setGross(foto)}
                className="size-full cursor-zoom-in"
                aria-label="Foto groß anzeigen"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={api.maengel.fotoUrl(foto.id, true)}
                  alt={foto.bildunterschrift || "Mangelfoto"}
                  className="size-full object-cover"
                  loading="lazy"
                />
              </button>
              <button
                type="button"
                onClick={() => entfernen(foto)}
                aria-label="Foto löschen"
                className="absolute right-1 top-1 rounded-full bg-white/90 p-1 text-ui-text-muted hover:text-ui-danger cursor-pointer transition-colors"
              >
                <Trash2 size={13} />
              </button>
              {foto.bildunterschrift && (
                <span className="absolute inset-x-0 bottom-0 truncate bg-black/45 px-1.5 py-0.5 text-[10px] text-white">
                  {foto.bildunterschrift}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <Button
          type="button"
          variante="sekundaer"
          icon={Camera}
          onClick={() => kameraRef.current?.click()}
          disabled={laeuft !== null}
        >
          Foto aufnehmen
        </Button>
        <Button
          type="button"
          variante="sekundaer"
          icon={ImagePlus}
          onClick={() => galerieRef.current?.click()}
          disabled={laeuft !== null}
        >
          Aus Galerie
        </Button>
        {laeuft && (
          <span className="flex items-center gap-1.5 text-[12px] text-ui-text-muted">
            <Loader2 size={13} className="animate-spin" />
            {laeuft}
          </span>
        )}
      </div>

      <input
        ref={kameraRef}
        type="file"
        accept="image/*,.heic,.heif,.avif,.tif,.tiff"
        capture="environment"
        multiple
        className="hidden"
        onChange={hochladen}
      />
      <input
        ref={galerieRef}
        type="file"
        accept="image/*,.heic,.heif,.avif,.tif,.tiff"
        multiple
        className="hidden"
        onChange={hochladen}
      />

      {gross && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setGross(null)}
          role="presentation"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={api.maengel.fotoUrl(gross.id)}
            alt={gross.bildunterschrift || "Mangelfoto"}
            className="max-h-full max-w-full object-contain"
          />
          <button
            type="button"
            onClick={() => setGross(null)}
            aria-label="Schließen"
            className="absolute right-4 top-4 rounded-full bg-white/90 p-2 text-ui-text cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>
      )}
    </div>
  );
}
