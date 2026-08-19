"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Plus,
  Trash2,
  Upload,
  FileText,
  X,
  ClipboardList,
  MapPin,
  Mail,
  Loader2,
  Download,
  AlertTriangle,
} from "lucide-react";
import { api, konfliktAnzahl } from "@/lib/api";
import type { Projekt, Empfaenger, Einreichung } from "@/lib/types";

/**
 * Löschen mit Rückfrage: Der Server lehnt den ersten Versuch mit 409 ab, wenn
 * noch Einreichungen daran hängen, und nennt deren Anzahl. Erst nach dem OK
 * des Nutzers wird mit force=true wirklich gelöscht.
 */
async function loeschenMitRueckfrage(
  entfernen: (force: boolean) => Promise<void>,
  bezeichnung: string
): Promise<string | null> {
  try {
    await entfernen(false);
    return null;
  } catch (err) {
    const anzahl = konfliktAnzahl(err);
    if (anzahl === null) {
      return err instanceof Error ? err.message : "Löschen fehlgeschlagen.";
    }
    const ok = window.confirm(
      `${bezeichnung} wird gelöscht.\n\n` +
        `Dazu gehören noch ${anzahl} Einreichung(en) — diese werden mit ` +
        `entfernt (inklusive der erzeugten Word-Dokumente).\n\n` +
        `Wirklich löschen?`
    );
    if (!ok) return null;
    try {
      await entfernen(true);
      return null;
    } catch (err2) {
      return err2 instanceof Error ? err2.message : "Löschen fehlgeschlagen.";
    }
  }
}

type Tab = "einreichen" | "projekte" | "emails";

export default function Home() {
  const [tab, setTab] = useState<Tab>("einreichen");
  const [projects, setProjects] = useState<Projekt[]>([]);
  const [emails, setEmails] = useState<Empfaenger[]>([]);
  const [submissions, setSubmissions] = useState<Einreichung[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [p, e, s] = await Promise.all([
        api.projekte.list(),
        api.empfaenger.list(),
        api.einreichungen.list(),
      ]);
      setProjects(p);
      setEmails(e);
      setSubmissions(s);
      setError(null);
    } catch (err) {
      setError(
        "Verbindung zum Server fehlgeschlagen. Bitte prüfen Sie, ob das Backend läuft."
      );
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const hasInFlight = submissions.some(
    (s) => s.status === "eingereicht" || s.status === "wird_verarbeitet"
  );

  useEffect(() => {
    if (!hasInFlight) return;
    const interval = setInterval(async () => {
      try {
        const s = await api.einreichungen.list();
        setSubmissions(s);
      } catch {}
    }, 4000);
    return () => clearInterval(interval);
  }, [hasInFlight]);

  return (
    <div className="min-h-full">
      {/* Header */}
      <div className="border-b-2 border-hpp-black px-7 py-[18px] flex justify-between items-end">
        <div>
          <div className="font-mono text-[11px] tracking-[0.12em] text-hpp-gray">
            HPP ARCHITEKTEN BAUMANAGEMENT
          </div>
          <div className="text-[21px] font-bold mt-0.5">
            Bautagesbericht — Eingabe
          </div>
        </div>
        <div className="font-mono text-[11px] text-hpp-gray text-right leading-relaxed">
          <div>PROJEKTE: {projects.length}</div>
          <div>E-MAILS: {emails.length}</div>
          <div>EINREICHUNGEN: {submissions.length}</div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="bg-hpp-warn-bg text-hpp-warn-text px-7 py-2 text-[13px]">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-hpp-stone px-7 overflow-x-auto">
        {(
          [
            ["einreichen", "Bericht einreichen"],
            ["projekte", "Stammdaten · Projekt"],
            ["emails", "Stammdaten · E-Mail"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`font-mono text-xs tracking-[0.08em] uppercase px-4 py-3 border-b-2 whitespace-nowrap cursor-pointer transition-colors ${
              tab === key
                ? "text-hpp-navy border-hpp-gold"
                : "text-hpp-gray border-transparent hover:text-hpp-navy"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="max-w-[720px] mx-auto p-7">
        {loading ? (
          <div className="flex items-center gap-2 text-hpp-gray text-sm">
            <Loader2
              size={16}
              className="animate-spin"
            />
            Lade Daten…
          </div>
        ) : tab === "projekte" ? (
          <ProjekteTab
            projects={projects}
            onUpdate={loadAll}
          />
        ) : tab === "emails" ? (
          <EmailsTab emails={emails} onUpdate={loadAll} />
        ) : (
          <EinreichenTab
            projects={projects}
            emails={emails}
            submissions={submissions}
            onUpdate={loadAll}
          />
        )}
      </div>
    </div>
  );
}

/* ───────── Projekte Tab ───────── */
function ProjekteTab({
  projects,
  onUpdate,
}: {
  projects: Projekt[];
  onUpdate: () => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [adresse, setAdresse] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleAdd() {
    if (!name.trim()) return;
    setSaving(true);
    try {
      await api.projekte.create({ name: name.trim(), adresse: adresse.trim() });
      setName("");
      setAdresse("");
      setShowForm(false);
      onUpdate();
    } catch {
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number, projektName: string) {
    setDeleteError(null);
    const fehler = await loeschenMitRueckfrage(
      (force) => api.projekte.delete(id, force),
      `Projekt „${projektName}"`
    );
    if (fehler) setDeleteError(fehler);
    onUpdate();
  }

  return (
    <div>
      <div className="font-mono text-[11px] tracking-[0.1em] text-hpp-gray mb-3.5">
        PROJEKTE — NAME + STANDORT, EINMAL ANLEGEN, DANACH IM FORMULAR WÄHLBAR
      </div>

      {deleteError && (
        <div className="bg-hpp-warn-bg text-hpp-warn-text px-3.5 py-2.5 text-[13px] mb-3.5">
          {deleteError}
        </div>
      )}

      {projects.length === 0 && !showForm && (
        <div className="border border-dashed border-hpp-stone p-7 text-center text-hpp-gray text-sm mb-4">
          Noch keine Projekte angelegt. Lege ein Projekt mit Standort an — die
          Adresse wird für den automatischen Wetterdaten-Abruf verwendet.
        </div>
      )}

      <div className="flex flex-col gap-2.5 mb-4">
        {projects.map((p) => (
          <div
            key={p.id}
            className="bg-white border border-hpp-stone p-3.5 px-4 flex justify-between items-start"
          >
            <div>
              <div className="font-semibold text-[15px]">{p.name}</div>
              <div className="flex items-center gap-1.5 text-hpp-text-secondary text-[13px] mt-1">
                <MapPin size={13} />
                {p.adresse || "— keine Adresse hinterlegt —"}
              </div>
              {p.lat && p.lon && (
                <div className="text-[11px] text-hpp-muted mt-0.5 font-mono">
                  {p.lat.toFixed(4)}, {p.lon.toFixed(4)}
                </div>
              )}
            </div>
            <button
              onClick={() => handleDelete(p.id, p.name)}
              aria-label={`${p.name} entfernen`}
              className="text-hpp-muted hover:text-hpp-warn-text p-1 cursor-pointer transition-colors"
            >
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </div>

      {showForm ? (
        <div className="bg-white border border-hpp-navy p-4 flex flex-col gap-2.5">
          <input
            className="w-full bg-white border border-hpp-stone px-3 py-2.5 text-sm focus:border-hpp-navy outline-none transition-colors placeholder:text-hpp-muted"
            placeholder="Projektname / -nummer"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          />
          <input
            className="w-full bg-white border border-hpp-stone px-3 py-2.5 text-sm focus:border-hpp-navy outline-none transition-colors placeholder:text-hpp-muted"
            placeholder="Adresse des Bauvorhabens (für Wetterdaten)"
            value={adresse}
            onChange={(e) => setAdresse(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          />
          <div className="flex gap-2">
            <button
              onClick={handleAdd}
              disabled={saving || !name.trim()}
              className="inline-flex items-center gap-1.5 bg-hpp-navy text-hpp-cream px-4 py-2.5 text-[13px] font-semibold tracking-wide cursor-pointer hover:bg-hpp-navy-dark disabled:bg-hpp-muted disabled:cursor-not-allowed transition-colors"
            >
              <Plus size={14} /> Projekt speichern
            </button>
            <button
              onClick={() => {
                setShowForm(false);
                setName("");
                setAdresse("");
              }}
              className="inline-flex items-center gap-1.5 border border-hpp-navy text-hpp-navy px-4 py-2.5 text-[13px] font-semibold cursor-pointer hover:bg-hpp-navy hover:text-hpp-cream transition-colors"
            >
              Abbrechen
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowForm(true)}
          className="inline-flex items-center gap-1.5 bg-hpp-navy text-hpp-cream px-4 py-2.5 text-[13px] font-semibold tracking-wide cursor-pointer hover:bg-hpp-navy-dark transition-colors"
        >
          <Plus size={14} /> Projekt anlegen
        </button>
      )}
    </div>
  );
}

/* ───────── Emails Tab ───────── */
function EmailsTab({
  emails,
  onUpdate,
}: {
  emails: Empfaenger[];
  onUpdate: () => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const [label, setLabel] = useState("");
  const [email, setEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleAdd() {
    if (!label.trim() || !email.trim()) return;
    setSaving(true);
    try {
      await api.empfaenger.create({
        label: label.trim(),
        email: email.trim(),
      });
      setLabel("");
      setEmail("");
      setShowForm(false);
      onUpdate();
    } catch {
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number, empfaengerLabel: string) {
    setDeleteError(null);
    const fehler = await loeschenMitRueckfrage(
      (force) => api.empfaenger.delete(id, force),
      `Empfänger „${empfaengerLabel}"`
    );
    if (fehler) setDeleteError(fehler);
    onUpdate();
  }

  return (
    <div>
      <div className="font-mono text-[11px] tracking-[0.1em] text-hpp-gray mb-3.5">
        E-MAIL-EMPFÄNGER — EINMAL ANLEGEN, DANACH IM FORMULAR WÄHLBAR
      </div>

      {deleteError && (
        <div className="bg-hpp-warn-bg text-hpp-warn-text px-3.5 py-2.5 text-[13px] mb-3.5">
          {deleteError}
        </div>
      )}

      {emails.length === 0 && !showForm && (
        <div className="border border-dashed border-hpp-stone p-7 text-center text-hpp-gray text-sm mb-4">
          Noch keine Empfänger angelegt. Lege die Personen an, die den fertigen
          Bautagesbericht per E-Mail erhalten sollen.
        </div>
      )}

      <div className="flex flex-col gap-2.5 mb-4">
        {emails.map((e) => (
          <div
            key={e.id}
            className="bg-white border border-hpp-stone p-3.5 px-4 flex justify-between items-start"
          >
            <div>
              <div className="font-semibold text-[15px]">{e.label}</div>
              <div className="flex items-center gap-1.5 text-hpp-text-secondary text-[13px] mt-1">
                <Mail size={13} /> {e.email}
              </div>
            </div>
            <button
              onClick={() => handleDelete(e.id, e.label)}
              aria-label={`${e.label} entfernen`}
              className="text-hpp-muted hover:text-hpp-warn-text p-1 cursor-pointer transition-colors"
            >
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </div>

      {showForm ? (
        <div className="bg-white border border-hpp-navy p-4 flex flex-col gap-2.5">
          <input
            className="w-full bg-white border border-hpp-stone px-3 py-2.5 text-sm focus:border-hpp-navy outline-none transition-colors placeholder:text-hpp-muted"
            placeholder="Bezeichnung (z. B. Name oder Rolle)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <input
            className="w-full bg-white border border-hpp-stone px-3 py-2.5 text-sm focus:border-hpp-navy outline-none transition-colors placeholder:text-hpp-muted"
            placeholder="E-Mail-Adresse"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          />
          <div className="flex gap-2">
            <button
              onClick={handleAdd}
              disabled={saving || !label.trim() || !email.trim()}
              className="inline-flex items-center gap-1.5 bg-hpp-navy text-hpp-cream px-4 py-2.5 text-[13px] font-semibold tracking-wide cursor-pointer hover:bg-hpp-navy-dark disabled:bg-hpp-muted disabled:cursor-not-allowed transition-colors"
            >
              <Plus size={14} /> Empfänger speichern
            </button>
            <button
              onClick={() => {
                setShowForm(false);
                setLabel("");
                setEmail("");
              }}
              className="inline-flex items-center gap-1.5 border border-hpp-navy text-hpp-navy px-4 py-2.5 text-[13px] font-semibold cursor-pointer hover:bg-hpp-navy hover:text-hpp-cream transition-colors"
            >
              Abbrechen
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setShowForm(true)}
          className="inline-flex items-center gap-1.5 bg-hpp-navy text-hpp-cream px-4 py-2.5 text-[13px] font-semibold tracking-wide cursor-pointer hover:bg-hpp-navy-dark transition-colors"
        >
          <Plus size={14} /> Empfänger anlegen
        </button>
      )}
    </div>
  );
}

/* ───────── Einreichen Tab ───────── */
function EinreichenTab({
  projects,
  emails,
  submissions,
  onUpdate,
}: {
  projects: Projekt[];
  emails: Empfaenger[];
  submissions: Einreichung[];
  onUpdate: () => void;
}) {
  const [projektId, setProjektId] = useState("");
  const [emailId, setEmailId] = useState("");
  const [datum, setDatum] = useState(new Date().toISOString().slice(0, 10));
  const [ergaenzendeAngaben, setErgaenzendeAngaben] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [justSubmitted, setJustSubmitted] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedProject = projects.find((p) => p.id === Number(projektId));
  const selectedEmail = emails.find((e) => e.id === Number(emailId));
  const canSubmit = projektId && emailId && datum && files.length > 0 && !submitting;

  function handleFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const list = Array.from(e.target.files || []);
    setFiles((prev) => [...prev, ...list].slice(0, 20));
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("projekt_id", projektId);
      formData.append("empfaenger_id", emailId);
      formData.append("datum", datum);
      formData.append("ergaenzende_angaben", ergaenzendeAngaben);
      files.forEach((f) => formData.append("dateien", f));

      await api.einreichungen.submit(formData);
      setFiles([]);
      setErgaenzendeAngaben("");
      setJustSubmitted(true);
      onUpdate();
      setTimeout(() => setJustSubmitted(false), 4000);
    } catch {
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      {justSubmitted && (
        <div className="bg-hpp-success-bg text-hpp-success-text border border-hpp-success-border px-3.5 py-2.5 text-[13px] mb-4">
          Eingereicht. Die Weiterverarbeitung (Auslesen der Berichte,
          Wetterdaten, Word-Erstellung, Versand) läuft im Backend-System.
        </div>
      )}

      <div className="flex flex-col gap-3.5 mb-5">
        {/* Projekt */}
        <div>
          <label className="font-mono text-[11px] tracking-[0.08em] text-hpp-gray">
            PROJEKT
          </label>
          <select
            className="w-full bg-white border border-hpp-stone px-3 py-2.5 text-sm focus:border-hpp-navy outline-none mt-1.5 transition-colors"
            value={projektId}
            onChange={(e) => setProjektId(e.target.value)}
          >
            <option value="">— Projekt wählen —</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          {projects.length === 0 && (
            <div className="text-xs text-hpp-hint-text mt-1.5">
              Noch keine Projekte hinterlegt — bitte zuerst unter „Stammdaten ·
              Projekt" anlegen.
            </div>
          )}
          {selectedProject && (
            <div className="text-xs text-hpp-gray mt-1.5">
              Wetterdaten via{" "}
              {selectedProject.adresse || "Adresse fehlt"}
            </div>
          )}
        </div>

        {/* Datum */}
        <div>
          <label className="font-mono text-[11px] tracking-[0.08em] text-hpp-gray">
            DATUM
          </label>
          <input
            type="date"
            className="w-full bg-white border border-hpp-stone px-3 py-2.5 text-sm focus:border-hpp-navy outline-none mt-1.5 transition-colors"
            value={datum}
            onChange={(e) => setDatum(e.target.value)}
          />
        </div>

        {/* Datei-Upload */}
        <div>
          <label className="font-mono text-[11px] tracking-[0.08em] text-hpp-gray">
            BAUTAGESBERICHTE DER UNTERNEHMEN
          </label>
          <label
            htmlFor="btb-upload"
            className="mt-1.5 flex items-center justify-center gap-2 border border-dashed border-hpp-navy px-3.5 py-5 cursor-pointer text-hpp-navy text-[13px] hover:bg-hpp-navy/5 transition-colors"
          >
            <Upload size={16} /> PDF oder Foto hochladen (mehrere möglich)
          </label>
          <input
            ref={fileInputRef}
            id="btb-upload"
            type="file"
            multiple
            accept=".pdf,image/*"
            className="hidden"
            onChange={handleFiles}
          />

          {files.length > 0 && (
            <div className="mt-2 flex flex-col gap-1.5">
              {files.map((f, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between bg-white border border-hpp-stone px-2.5 py-[7px] text-[13px]"
                >
                  <span className="flex items-center gap-1.5 overflow-hidden text-ellipsis whitespace-nowrap">
                    <FileText size={14} className="text-hpp-gray shrink-0" />
                    {f.name}
                  </span>
                  <button
                    onClick={() => removeFile(i)}
                    className="text-hpp-muted hover:text-hpp-warn-text cursor-pointer transition-colors"
                    aria-label="Datei entfernen"
                  >
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Ergänzende Angaben */}
        <div>
          <label className="font-mono text-[11px] tracking-[0.08em] text-hpp-gray">
            ERGÄNZENDE ANGABEN
          </label>
          <textarea
            className="w-full bg-white border border-hpp-stone px-3 py-2.5 text-sm focus:border-hpp-navy outline-none mt-1.5 min-h-[80px] resize-y transition-colors placeholder:text-hpp-muted"
            placeholder="Zusätzliche Hinweise zum Tag…"
            value={ergaenzendeAngaben}
            onChange={(e) => setErgaenzendeAngaben(e.target.value)}
          />
        </div>

        {/* E-Mail-Empfänger */}
        <div>
          <label className="font-mono text-[11px] tracking-[0.08em] text-hpp-gray">
            E-MAIL-EMPFÄNGER
          </label>
          <select
            className="w-full bg-white border border-hpp-stone px-3 py-2.5 text-sm focus:border-hpp-navy outline-none mt-1.5 transition-colors"
            value={emailId}
            onChange={(e) => setEmailId(e.target.value)}
          >
            <option value="">— Empfänger wählen —</option>
            {emails.map((e) => (
              <option key={e.id} value={e.id}>
                {e.label} ({e.email})
              </option>
            ))}
          </select>
          {emails.length === 0 && (
            <div className="text-xs text-hpp-hint-text mt-1.5">
              Noch keine Empfänger hinterlegt — bitte zuerst unter „Stammdaten ·
              E-Mail" anlegen.
            </div>
          )}
          {selectedEmail && (
            <div className="text-xs text-hpp-gray mt-1.5">
              Versand an {selectedEmail.email}
            </div>
          )}
        </div>

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={!canSubmit}
          className="flex items-center justify-center gap-1.5 bg-hpp-navy text-hpp-cream px-4 py-2.5 text-[13px] font-semibold tracking-wide cursor-pointer hover:bg-hpp-navy-dark disabled:bg-hpp-muted disabled:cursor-not-allowed mt-1 transition-colors"
        >
          {submitting ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <ClipboardList size={14} />
          )}
          {submitting ? "Wird eingereicht…" : "Einreichen"}
        </button>
      </div>

      {/* Letzte Einreichungen */}
      {submissions.length > 0 && (
        <div>
          <div className="font-mono text-[11px] tracking-[0.1em] text-hpp-gray mb-2 border-t border-hpp-stone pt-4">
            LETZTE EINREICHUNGEN
          </div>
          <div className="flex flex-col gap-1.5">
            {submissions.slice(0, 6).map((s) => (
              <SubmissionRow key={s.id} s={s} onUpdate={onUpdate} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SubmissionRow({
  s,
  onUpdate,
}: {
  s: Einreichung;
  onUpdate: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const inFlight = s.status === "eingereicht" || s.status === "wird_verarbeitet";
  const needsConfirm = s.status === "wartet_auf_bestaetigung";

  async function handleConfirm() {
    setConfirming(true);
    try {
      await api.einreichungen.bestaetigen(s.id);
      onUpdate();
    } catch {
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className="bg-white border border-hpp-stone">
      <div className="flex justify-between items-center text-[13px] px-3 py-2">
        <button
          onClick={() =>
            s.warnungen.length > 0 ? setExpanded((v) => !v) : undefined
          }
          className={
            s.warnungen.length > 0
              ? "text-left flex-1 cursor-pointer"
              : "text-left flex-1"
          }
        >
          {s.projekt_name} · {s.datum}
        </button>
        <div className="flex items-center gap-2">
          {inFlight && (
            <Loader2 size={13} className="animate-spin text-hpp-hint-text" />
          )}
          {s.warnungen.length > 0 && (
            <span className="flex items-center gap-1 text-hpp-hint-text">
              <AlertTriangle size={13} />
              {s.warnungen.length}
            </span>
          )}
          <span
            className={
              s.status === "abgeschlossen"
                ? "text-hpp-success-text"
                : s.status === "fehlgeschlagen"
                ? "text-hpp-warn-text"
                : "text-hpp-hint-text"
            }
          >
            {s.status}
          </span>
          {s.status === "abgeschlossen" && (
            <a
              href={api.einreichungen.downloadUrl(s.id)}
              className="text-hpp-navy hover:underline"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Word-Dokument herunterladen"
            >
              <Download size={13} />
            </a>
          )}
        </div>
      </div>

      {(expanded || needsConfirm) && s.warnungen.length > 0 && (
        <div className="border-t border-hpp-stone bg-hpp-hint-bg px-3 py-2 text-[12px]">
          <div className="font-mono text-[10px] tracking-[0.1em] text-hpp-gray mb-1">
            WARNUNGEN
          </div>
          <ul className="flex flex-col gap-1 mb-2">
            {s.warnungen.map((w, i) => (
              <li key={i} className="text-hpp-hint-text">
                <span className="font-semibold">{w.feld}:</span> {w.problem}
                {w.quelle_datei ? (
                  <span className="text-hpp-gray"> ({w.quelle_datei})</span>
                ) : null}
              </li>
            ))}
          </ul>
          {needsConfirm && (
            <button
              onClick={handleConfirm}
              disabled={confirming}
              className="inline-flex items-center gap-1.5 bg-hpp-navy text-hpp-cream px-3 py-1.5 text-[12px] font-semibold cursor-pointer hover:bg-hpp-navy-dark disabled:bg-hpp-muted disabled:cursor-not-allowed transition-colors"
            >
              {confirming ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <ClipboardList size={12} />
              )}
              {confirming ? "Wird erstellt…" : "Trotzdem erstellen"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
