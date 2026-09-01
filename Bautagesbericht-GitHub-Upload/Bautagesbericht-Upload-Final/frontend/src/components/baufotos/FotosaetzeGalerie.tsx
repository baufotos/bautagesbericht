"use client";

/**
 * Fotosätze eines Projekts — nach Tagen gruppiert.
 *
 * Die Gruppierung nach Datum ist nicht Kosmetik: Man sucht hier fast immer
 * "die Fotos von gestern" oder "die vom Tag der Abnahme". Innerhalb eines Tages
 * unterscheiden sich die Sätze durch die Kategorie.
 *
 * Jede Karte trägt den Archivnamen sichtbar — das ist der Name, unter dem die
 * Datei im Projektordner landet, und damit die Information, die beim Ablegen
 * wirklich zählt.
 */

import {
  ChevronDown,
  ChevronRight,
  FileArchive,
  ImageOff,
  Images,
  Mail,
  Plus,
  Search,
  Send,
  Trash2,
  X,
} from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { formatBytes, formatDatumIso, relativeZeit } from "@/lib/formate";
import type {
  Baufoto,
  Empfaenger,
  FotosatzListItem,
  Gewerk,
  Projekt,
} from "@/lib/types";
import { FotosatzMailDialog } from "@/components/baufotos/FotosatzMailDialog";
import {
  Karte,
  KarteInhalt,
  KarteKopf,
  LeerHinweis,
  Plakette,
} from "@/components/dashboard";
import { Button, Chip, ChipLeiste, Input, LinkButton, Meldung, Select } from "@/components/ui";

const MONATSNAMEN = [
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
];

/** "2026-08-19" → "August 2026" */
function monatsTitel(iso: string): string {
  const [jahr, monat] = iso.slice(0, 7).split("-");
  const index = Number(monat) - 1;
  return `${MONATSNAMEN[index] ?? monat} ${jahr}`;
}

export function FotosaetzeGalerie({
  projekt,
  fotosaetze,
  empfaenger,
  gewerke,
  laedt,
  onAendern,
  onNeu,
}: {
  projekt: Projekt;
  fotosaetze: FotosatzListItem[];
  /** Adressvorschläge für den Mailversand — Stammdaten-Empfänger. */
  empfaenger: Empfaenger[];
  /** … und die Firmen des Projekts, soweit eine Adresse hinterlegt ist. */
  gewerke: Gewerk[];
  laedt: boolean;
  onAendern: () => void;
  onNeu: () => void;
}) {
  const [suche, setSuche] = useState("");
  const [kategorie, setKategorie] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  const [mailFuer, setMailFuer] = useState<FotosatzListItem | null>(null);

  const kategorien = Array.from(new Set(fotosaetze.map((f) => f.kategorie))).sort();

  const gefiltert = fotosaetze.filter((f) => {
    if (kategorie && f.kategorie !== kategorie) return false;
    if (!suche.trim()) return true;
    const begriff = suche.trim().toLowerCase();
    return (
      f.kategorie.toLowerCase().includes(begriff) ||
      f.notiz.toLowerCase().includes(begriff) ||
      f.zip_dateiname.toLowerCase().includes(begriff)
    );
  });

  // Nach Monaten gruppieren; die Liste kommt schon nach Datum absteigend.
  // Monat und nicht Tag: Ein Bautag bringt meist einen Satz, und eine einzelne
  // Karte in einer dreispaltigen Reihe sieht nach Fehler aus. Der genaue Tag
  // steht auf jeder Karte.
  const monate: { schluessel: string; titel: string; saetze: FotosatzListItem[] }[] = [];
  for (const satz of gefiltert) {
    const schluessel = satz.datum.slice(0, 7);
    const letzter = monate[monate.length - 1];
    if (letzter && letzter.schluessel === schluessel) letzter.saetze.push(satz);
    else monate.push({ schluessel, titel: monatsTitel(satz.datum), saetze: [satz] });
  }

  const anzahlFotos = fotosaetze.reduce((summe, f) => summe + f.anzahl_fotos, 0);
  const summeBytes = fotosaetze.reduce((summe, f) => summe + f.groesse_bytes, 0);

  async function loeschen(satz: FotosatzListItem) {
    if (
      !window.confirm(
        `Fotosatz „${satz.kategorie}“ vom ${satz.datum} mit ${satz.anzahl_fotos} ` +
          `Foto(s) endgültig löschen?`
      )
    ) {
      return;
    }
    setFehler(null);
    try {
      await api.baufotos.delete(satz.id);
      onAendern();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Löschen fehlgeschlagen.");
    }
  }

  async function melden(satz: FotosatzListItem) {
    setMeldung(null);
    setFehler(null);
    try {
      const ergebnis = await api.baufotos.melden(satz.id);
      setMeldung(ergebnis.nachricht);
      if (ergebnis.gemeldet) onAendern();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Melden fehlgeschlagen.");
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Kopfzeile: Umfang und Werkzeuge */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-app-text-still">
          {fotosaetze.length} Fotosatz/Fotosätze · {anzahlFotos} Fotos
          {summeBytes > 0 && ` · ${formatBytes(summeBytes)}`}
        </span>
        <div className="ml-auto hidden sm:block">
          <Button icon={Plus} onClick={onNeu}>
            Fotos hochladen
          </Button>
        </div>
      </div>

      {fehler && <Meldung art="fehler">{fehler}</Meldung>}
      {meldung && <Meldung art="hinweis">{meldung}</Meldung>}

      {/* Filter */}
      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ui-text-faint"
          />
          <Input
            className="pl-8"
            placeholder="Kategorie, Notiz, Archivname…"
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
          />
        </div>
        <div className="w-full sm:w-[200px]">
          <Select value={kategorie} onChange={(e) => setKategorie(e.target.value)}>
            <option value="">Alle Kategorien</option>
            {kategorien.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {kategorien.length > 1 && (
        <ChipLeiste>
          <Chip aktiv={kategorie === ""} onClick={() => setKategorie("")}>
            Alle
          </Chip>
          {kategorien.map((k) => (
            <Chip key={k} aktiv={kategorie === k} onClick={() => setKategorie(k)}>
              {k}
            </Chip>
          ))}
        </ChipLeiste>
      )}

      {/* Runder Knopf am Handy, wie in der Mängelübersicht */}
      <div className="sm:hidden">
        <button
          type="button"
          onClick={onNeu}
          aria-label="Fotos hochladen"
          className="fixed right-4 bottom-[calc(5rem+env(safe-area-inset-bottom))] z-30 flex size-14 cursor-pointer items-center justify-center rounded-full bg-app-akzent text-app-akzent-text schatten-akzent transition-colors hover:bg-app-akzent-hover"
        >
          <Plus size={24} />
        </button>
      </div>

      {laedt && fotosaetze.length === 0 ? (
        <LeerHinweis>Fotosätze werden geladen…</LeerHinweis>
      ) : gefiltert.length === 0 ? (
        <LeerHinweis>
          {fotosaetze.length === 0
            ? `Für ${projekt.name} sind noch keine Baufotos hinterlegt. Ein Fotosatz ist ein Tag plus eine Kategorie — genau daraus entsteht der Name der ZIP-Datei.`
            : "Kein Fotosatz passt zu dieser Suche."}
        </LeerHinweis>
      ) : (
        monate.map(({ schluessel, titel, saetze }) => (
          <div key={schluessel} className="flex flex-col gap-2">
            <div className="flex items-center gap-2 pt-1">
              <span className="text-[12px] font-semibold text-app-text">{titel}</span>
              <span className="h-px flex-1 bg-app-linie" />
              <span className="text-[11.5px] text-app-text-still">
                {saetze.length} Satz/Sätze
              </span>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {saetze.map((satz) => (
                <FotosatzKarte
                  key={satz.id}
                  satz={satz}
                  onLoeschen={() => loeschen(satz)}
                  onMelden={() => melden(satz)}
                  onMail={() => setMailFuer(satz)}
                  onAendern={onAendern}
                />
              ))}
            </div>
          </div>
        ))
      )}

      {mailFuer && (
        <FotosatzMailDialog
          satz={mailFuer}
          empfaenger={empfaenger}
          gewerke={gewerke}
          onSchliessen={() => setMailFuer(null)}
          onVersendet={onAendern}
        />
      )}
    </div>
  );
}

/* ───────────────────────────── Eine Karte ───────────────────────────── */

function FotosatzKarte({
  satz,
  onLoeschen,
  onMelden,
  onMail,
  onAendern,
}: {
  satz: FotosatzListItem;
  onLoeschen: () => void;
  onMelden: () => void;
  onMail: () => void;
  onAendern: () => void;
}) {
  const [offen, setOffen] = useState(false);
  const [fotos, setFotos] = useState<Baufoto[] | null>(null);
  const [gross, setGross] = useState<Baufoto | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  async function aufklappen() {
    const neuerZustand = !offen;
    setOffen(neuerZustand);
    // Die Einzelfotos erst beim Aufklappen holen — die Übersicht soll auch mit
    // dreißig Sätzen zügig stehen.
    if (neuerZustand && fotos === null) {
      try {
        const detail = await api.baufotos.get(satz.id);
        setFotos(detail.fotos);
      } catch (err) {
        setFehler(err instanceof Error ? err.message : "Fotos nicht ladbar.");
      }
    }
  }

  async function fotoLoeschen(foto: Baufoto) {
    if (!window.confirm(`Foto ${foto.dateiname} entfernen?`)) return;
    try {
      await api.baufotos.deleteFoto(foto.id);
      setFotos((alt) => (alt ? alt.filter((f) => f.id !== foto.id) : alt));
      onAendern();
    } catch (err) {
      setFehler(err instanceof Error ? err.message : "Löschen fehlgeschlagen.");
    }
  }

  return (
    <Karte className="overflow-hidden">
      {/* Titelbild */}
      <div className="aspect-[16/10] w-full overflow-hidden border-b border-app-linie bg-app-flaeche-still">
        {satz.titel_foto_id ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={api.baufotos.fotoUrl(satz.titel_foto_id, true)}
            alt={`Baufoto ${satz.kategorie}`}
            className="size-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex size-full items-center justify-center text-app-text-leise">
            <ImageOff size={22} />
          </div>
        )}
      </div>

      <KarteKopf
        titel={satz.kategorie}
        unterzeile={
          <>
            {formatDatumIso(satz.datum)} · {satz.anzahl_fotos} Foto(s) ·{" "}
            {formatBytes(satz.groesse_bytes)}
            {satz.erstellt_am && ` · ${relativeZeit(satz.erstellt_am)}`}
          </>
        }
        icon={Images}
        aktion={
          // Der Mailvermerk hat Vorrang: "Ist das schon raus?" ist die Frage,
          // die man vor der Karte stellt. Der Teams-Zustand steht darunter im
          // Versandvermerk, wenn es einen gibt.
          satz.mail_versendet_am ? (
            <Plakette art="ok">
              {satz.mail_weg === "smtp" ? "gemailt" : "Entwurf"}
            </Plakette>
          ) : satz.zuletzt_gemeldet_am ? (
            <Plakette art="ok">gemeldet</Plakette>
          ) : (
            <Plakette art="neutral">nicht versendet</Plakette>
          )
        }
      />

      <KarteInhalt className="flex flex-col gap-2.5">
        {satz.notiz && (
          <p className="text-[12.5px] text-app-text-still">{satz.notiz}</p>
        )}

        <div className="rounded-app-sm border border-app-linie bg-app-flaeche-still px-2.5 py-2">
          <div className="text-[10px] uppercase tracking-[0.1em] text-app-text-still">
            Archivname
          </div>
          <div className="mt-0.5 font-mono text-[11.5px] break-all text-app-text">
            {satz.zip_dateiname}
          </div>
        </div>

        {/* Versandvermerk: an wen ging der Satz, und wann? */}
        {(satz.mail_versendet_am || satz.zuletzt_gemeldet_am) && (
          <div className="flex flex-col gap-0.5 text-[11.5px] text-app-text-still">
            {satz.mail_versendet_am && (
              <span className="flex items-start gap-1.5">
                <Mail size={12} className="mt-0.5 shrink-0" />
                <span className="min-w-0">
                  {satz.mail_weg === "smtp" ? "Versendet" : "Entwurf erstellt"} am{" "}
                  {formatDatumIso(satz.mail_versendet_am)}
                  {satz.mail_empfaenger && (
                    <span className="block truncate">{satz.mail_empfaenger}</span>
                  )}
                </span>
              </span>
            )}
            {satz.zuletzt_gemeldet_am && (
              <span className="flex items-center gap-1.5">
                <Send size={12} className="shrink-0" />
                In Teams gemeldet am {formatDatumIso(satz.zuletzt_gemeldet_am)}
              </span>
            )}
          </div>
        )}

        {fehler && <Meldung art="fehler">{fehler}</Meldung>}

        <div className="flex flex-wrap items-center gap-1.5">
          <Button variante="primaer" icon={Mail} onClick={onMail}>
            Per Mail
          </Button>
          <LinkButton
            href={api.baufotos.zipUrl(satz.id)}
            icon={FileArchive}
            variante="sekundaer"
          >
            ZIP
          </LinkButton>
          <Button variante="still" icon={Send} onClick={onMelden}>
            Teams
          </Button>
          <Button
            variante="still"
            icon={offen ? ChevronDown : ChevronRight}
            onClick={aufklappen}
          >
            {satz.anzahl_fotos} Fotos
          </Button>
          <button
            type="button"
            onClick={onLoeschen}
            aria-label={`Fotosatz ${satz.kategorie} löschen`}
            className="ml-auto cursor-pointer p-1.5 text-app-text-leise transition-colors hover:text-app-gefahr"
          >
            <Trash2 size={15} />
          </button>
        </div>

        {offen && (
          <div className="border-t border-app-linie pt-2.5">
            {fotos === null ? (
              <div className="text-[12px] text-app-text-still">Fotos werden geladen…</div>
            ) : fotos.length === 0 ? (
              <div className="text-[12px] text-app-text-still">
                Dieser Satz enthält kein Foto mehr.
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-1.5">
                {fotos.map((foto) => (
                  <div
                    key={foto.id}
                    className="relative aspect-square overflow-hidden rounded-app-sm border border-app-linie bg-app-flaeche-still"
                  >
                    <button
                      type="button"
                      onClick={() => setGross(foto)}
                      className="size-full cursor-zoom-in"
                      aria-label={`${foto.dateiname} groß anzeigen`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={api.baufotos.fotoUrl(foto.id, true)}
                        alt={foto.dateiname}
                        className="size-full object-cover"
                        loading="lazy"
                      />
                    </button>
                    <button
                      type="button"
                      onClick={() => fotoLoeschen(foto)}
                      aria-label={`${foto.dateiname} löschen`}
                      className="absolute top-1 right-1 cursor-pointer rounded-full bg-white/90 p-1 text-app-text-still transition-colors hover:text-app-gefahr"
                    >
                      <Trash2 size={12} />
                    </button>
                    <span className="absolute inset-x-0 bottom-0 truncate bg-black/50 px-1 py-0.5 font-mono text-[9px] text-white">
                      {foto.dateiname}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </KarteInhalt>

      {gross && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setGross(null)}
          role="presentation"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={api.baufotos.fotoUrl(gross.id)}
            alt={gross.dateiname}
            className="max-h-full max-w-full object-contain"
          />
          <span className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-app-sm bg-black/60 px-2.5 py-1 font-mono text-[11.5px] text-white">
            {gross.dateiname}
          </span>
          <button
            type="button"
            onClick={() => setGross(null)}
            aria-label="Schließen"
            className="absolute top-4 right-4 cursor-pointer rounded-full bg-white/90 p-2 text-app-text"
          >
            <X size={18} />
          </button>
        </div>
      )}
    </Karte>
  );
}
