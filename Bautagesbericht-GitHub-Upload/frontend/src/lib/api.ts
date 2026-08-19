import type { Projekt, Empfaenger, Einreichung } from "./types";

// Relativer Pfad: Aufrufe gehen an denselben Host, von dem die Seite geladen
// wurde (z. B. http://192.168.1.134:3000/api/…). Next.js leitet /api per
// Rewrite serverseitig ans Backend weiter — so funktioniert die App auch,
// wenn Team-Mitglieder sie über die Netzwerk-Adresse öffnen.
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

/** Fehler eines API-Aufrufs — trägt Status und ausgewertete Antwort mit. */
export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Anzahl betroffener Einreichungen aus einem 409-Konflikt, sonst null. */
export function konfliktAnzahl(err: unknown): number | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const detail = err.detail as { anzahl_einreichungen?: number } | undefined;
  return typeof detail?.anzahl_einreichungen === "number"
    ? detail.anzahl_einreichungen
    : null;
}

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let detail: unknown = text;
    try {
      const parsed = JSON.parse(text);
      detail = parsed?.detail ?? parsed;
    } catch {
      /* keine JSON-Antwort — Rohtext behalten */
    }
    const message =
      typeof detail === "object" && detail !== null && "nachricht" in detail
        ? String((detail as { nachricht: unknown }).nachricht)
        : `API ${res.status}: ${text}`;
    throw new ApiError(res.status, detail, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  projekte: {
    list: () => fetchAPI<Projekt[]>("/projekte"),
    create: (data: { name: string; adresse: string }) =>
      fetchAPI<Projekt>("/projekte", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
    delete: (id: number, force = false) =>
      fetchAPI<void>(`/projekte/${id}${force ? "?force=true" : ""}`, {
        method: "DELETE",
      }),
  },
  empfaenger: {
    list: () => fetchAPI<Empfaenger[]>("/empfaenger"),
    create: (data: { label: string; email: string }) =>
      fetchAPI<Empfaenger>("/empfaenger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }),
    delete: (id: number, force = false) =>
      fetchAPI<void>(`/empfaenger/${id}${force ? "?force=true" : ""}`, {
        method: "DELETE",
      }),
  },
  einreichungen: {
    list: () => fetchAPI<Einreichung[]>("/einreichungen"),
    get: (id: number) => fetchAPI<Einreichung>(`/einreichungen/${id}`),
    submit: (formData: FormData) =>
      fetchAPI<Einreichung>("/einreichungen", {
        method: "POST",
        body: formData,
      }),
    bestaetigen: (id: number) =>
      fetchAPI<Einreichung>(`/einreichungen/${id}/bestaetigen`, {
        method: "POST",
      }),
    downloadUrl: (id: number) => `${API_BASE}/einreichungen/${id}/dokument`,
  },
};
