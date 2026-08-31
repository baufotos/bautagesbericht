import type {
  Baufoto,
  Bearbeiter,
  Einreichung,
  EinreichungFaehigkeiten,
  Empfaenger,
  Fotosatz,
  FotosatzFilter,
  FotosatzListItem,
  FotosatzMailAnfrage,
  FotosatzMailErgebnis,
  FotosatzMailFaehigkeiten,
  FotosatzMailVorschlag,
  FotosatzVersand,
  GliederungHauptkapitel,
  Gewerk,
  MaengelanzeigeAnfrage,
  MaengelanzeigeVorbelegung,
  MaengelanzeigeVorschau,
  Mangel,
  MangelCreateInput,
  MangelDatei,
  MangelFilter,
  MangelFoto,
  MangelListItem,
  MangelPlanMarkierung,
  MangelRueckmeldungStatus,
  MangelStammdaten,
  MangelStatus,
  MangelTyp,
  MangelUpdateInput,
  MangelVersandErgebnis,
  Projekt,
  Projektbericht,
  ProjektberichtEingabe,
  ProjektberichtFoto,
  ProjektberichtListItem,
  ProjektberichtVorschau,
  ProjektPlan,
  WochenAnalyse,
  WochenErgebnis,
  WochenTag,
} from "./types";

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

/**
 * Anzahl betroffener abhängiger Datensätze aus einem 409-Konflikt, sonst null.
 *
 * Die Endpunkte melden je nach Zusammenhang `anzahl_einreichungen`,
 * `anzahl_maengel` oder — allgemein — `anzahl`; hier wird der erste
 * vorhandene Wert genommen, damit dieselbe Rückfrage-Logik überall passt.
 */
export function konfliktAnzahl(err: unknown): number | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const detail = err.detail as Record<string, unknown> | undefined;
  for (const feld of ["anzahl", "anzahl_einreichungen", "anzahl_maengel"]) {
    const wert = detail?.[feld];
    if (typeof wert === "number" && wert > 0) return wert;
  }
  return null;
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
        : typeof detail === "string" && detail
        ? detail
        : `API ${res.status}: ${text}`;
    throw new ApiError(res.status, detail, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

/** Eine Datei vom API holen (ZIP, .eml) statt JSON — mit demselben Fehlerweg.
 *
 * ``fetchAPI`` liest immer JSON. Für Antworten, die eine Datei sind, braucht es
 * diesen zweiten Weg: Er wirft denselben ``ApiError`` (damit die Oberfläche
 * Meldungen wie "Archiv zu groß" anzeigen kann) und liefert sonst den Inhalt
 * samt Dateinamen aus dem ``Content-Disposition``-Kopf.
 */
async function fetchDatei(
  path: string,
  options?: RequestInit
): Promise<{ blob: Blob; dateiname: string }> {
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
    throw new ApiError(
      res.status,
      detail,
      typeof detail === "string" && detail ? detail : `API ${res.status}`
    );
  }
  return {
    blob: await res.blob(),
    dateiname: dateinameAus(res.headers.get("Content-Disposition")),
  };
}

/** Dateiname aus dem Content-Disposition-Kopf, RFC-5987-Fassung bevorzugt. */
function dateinameAus(kopfzeile: string | null): string {
  if (!kopfzeile) return "";
  const mitKodierung = /filename\*=UTF-8''([^;]+)/i.exec(kopfzeile);
  if (mitKodierung) {
    try {
      return decodeURIComponent(mitKodierung[1].trim());
    } catch {
      /* kaputt kodiert — dann der schlichte Name unten */
    }
  }
  const schlicht = /filename="?([^";]+)"?/i.exec(kopfzeile);
  return schlicht ? schlicht[1].trim() : "";
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

/** Baut einen Query-String und lässt leere Werte weg. */
function query(params: Record<string, string | number | boolean | undefined | null>) {
  const suche = new URLSearchParams();
  for (const [schluessel, wert] of Object.entries(params)) {
    if (wert === undefined || wert === null || wert === "") continue;
    suche.set(schluessel, String(wert));
  }
  const text = suche.toString();
  return text ? `?${text}` : "";
}

export const api = {
  projekte: {
    list: () => fetchAPI<Projekt[]>("/projekte"),
    create: (data: {
      name: string;
      adresse: string;
      teams_webhook_url?: string;
      foto_zielpfad?: string;
    }) => fetchAPI<Projekt>("/projekte", json("POST", data)),
    update: (
      id: number,
      data: {
        name?: string;
        adresse?: string;
        teams_webhook_url?: string;
        foto_zielpfad?: string;
      }
    ) => fetchAPI<Projekt>(`/projekte/${id}`, json("PATCH", data)),
    delete: (id: number, force = false) =>
      fetchAPI<void>(`/projekte/${id}${force ? "?force=true" : ""}`, {
        method: "DELETE",
      }),
  },
  empfaenger: {
    list: () => fetchAPI<Empfaenger[]>("/empfaenger"),
    create: (data: { label: string; email: string; teams_webhook_url?: string }) =>
      fetchAPI<Empfaenger>("/empfaenger", json("POST", data)),
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

    /**
     * Wochenpaket in zwei Schritten.
     *
     * ``analysieren`` lädt die Dateien hoch und meldet nur, welche Tage darin
     * stecken — es entsteht noch kein Bericht. Erst ``erzeugen`` legt je Tag
     * eine Einreichung an. Dazwischen wird nichts erneut hochgeladen; die
     * ``kennung`` verweist auf die Zwischenablage auf dem Server.
     */
    wocheAnalysieren: (dateien: File[], von: string, bis: string) => {
      const formular = new FormData();
      dateien.forEach((datei) => formular.append("dateien", datei));
      if (von) formular.append("woche_von", von);
      if (bis) formular.append("woche_bis", bis);
      return fetchAPI<WochenAnalyse>("/einreichungen/woche/analyse", {
        method: "POST",
        body: formular,
      });
    },

    /** Kann dieser Rechner Fotos und Handschrift lesen? */
    faehigkeiten: () =>
      fetchAPI<EinreichungFaehigkeiten>("/einreichungen/faehigkeiten"),
    wocheErzeugen: (daten: {
      kennung: string;
      projekt_id: number;
      empfaenger_id: number;
      tage: WochenTag[];
    }) => fetchAPI<WochenErgebnis>("/einreichungen/woche", json("POST", daten)),

    /** Mehrere fertige Berichte in einem Archiv. */
    dokumenteAlsZip: (ids: number[]) =>
      fetchDatei(`/einreichungen/dokumente.zip?ids=${ids.join(",")}`),
  },

  /* ───────── Mängelmanagement ───────── */

  mangelStammdaten: {
    alle: () => fetchAPI<MangelStammdaten>("/mangel-stammdaten"),
    createTyp: (data: { bezeichnung: string; sortierung?: number }) =>
      fetchAPI<MangelTyp>("/mangel-stammdaten/typen", json("POST", data)),
    deleteTyp: (id: number) =>
      fetchAPI<void>(`/mangel-stammdaten/typen/${id}`, { method: "DELETE" }),
    createStatus: (data: {
      bezeichnung: string;
      farbe?: string;
      ist_abgeschlossen?: boolean;
      sortierung?: number;
    }) => fetchAPI<MangelStatus>("/mangel-stammdaten/status", json("POST", data)),
    deleteStatus: (id: number) =>
      fetchAPI<void>(`/mangel-stammdaten/status/${id}`, { method: "DELETE" }),
    createRueckmeldung: (data: { bezeichnung: string; sortierung?: number }) =>
      fetchAPI<MangelRueckmeldungStatus>(
        "/mangel-stammdaten/rueckmeldung-status",
        json("POST", data)
      ),
    deleteRueckmeldung: (id: number) =>
      fetchAPI<void>(`/mangel-stammdaten/rueckmeldung-status/${id}`, {
        method: "DELETE",
      }),
    createBearbeiter: (data: { name: string; email?: string }) =>
      fetchAPI<Bearbeiter>("/mangel-stammdaten/bearbeiter", json("POST", data)),
    deleteBearbeiter: (id: number) =>
      fetchAPI<void>(`/mangel-stammdaten/bearbeiter/${id}`, { method: "DELETE" }),
  },

  gewerke: {
    list: (projektId?: number) =>
      fetchAPI<Gewerk[]>(`/gewerke${query({ projekt_id: projektId })}`),
    create: (data: {
      projekt_id: number;
      firma_name: string;
      vergabeeinheit_code?: string;
      vergabeeinheit_bezeichnung?: string;
      email?: string;
      /* Postanschrift — nur die Mängelanzeige braucht sie. */
      ansprechpartner?: string;
      strasse?: string;
      plz?: string;
      ort?: string;
      teams_webhook_url?: string;
    }) => fetchAPI<Gewerk>("/gewerke", json("POST", data)),
    update: (
      id: number,
      data: Partial<{
        firma_name: string;
        vergabeeinheit_code: string;
        vergabeeinheit_bezeichnung: string;
        email: string;
        teams_webhook_url: string;
      }>
    ) => fetchAPI<Gewerk>(`/gewerke/${id}`, json("PATCH", data)),
    delete: (id: number, force = false) =>
      fetchAPI<void>(`/gewerke/${id}${force ? "?force=true" : ""}`, {
        method: "DELETE",
      }),
  },

  plaene: {
    list: (projektId?: number) =>
      fetchAPI<ProjektPlan[]>(`/plaene${query({ projekt_id: projektId })}`),
    upload: (projektId: number, datei: File) => {
      const formData = new FormData();
      formData.append("projekt_id", String(projektId));
      formData.append("datei", datei);
      return fetchAPI<ProjektPlan>("/plaene", { method: "POST", body: formData });
    },
    delete: (id: number, force = false) =>
      fetchAPI<void>(`/plaene/${id}${force ? "?force=true" : ""}`, {
        method: "DELETE",
      }),
    /** Planseite als Bild — die Fläche, auf die für die Markierung getippt wird. */
    vorschauUrl: (id: number, seite = 1) =>
      `${API_BASE}/plaene/${id}/vorschau?seite=${seite}`,
    dateiUrl: (id: number) => `${API_BASE}/plaene/${id}/datei`,
  },

  maengel: {
    list: (filter: MangelFilter = {}) =>
      fetchAPI<MangelListItem[]>(`/maengel${query({ ...filter })}`),
    get: (id: number) => fetchAPI<Mangel>(`/maengel/${id}`),
    create: (data: MangelCreateInput) =>
      fetchAPI<Mangel>("/maengel", json("POST", data)),
    update: (id: number, data: MangelUpdateInput) =>
      fetchAPI<Mangel>(`/maengel/${id}`, json("PATCH", data)),
    delete: (id: number) => fetchAPI<void>(`/maengel/${id}`, { method: "DELETE" }),
    duplizieren: (id: number) =>
      fetchAPI<Mangel>(`/maengel/${id}/duplizieren`, { method: "POST" }),

    uploadFotos: (id: number, dateien: File[], bildunterschrift = "") => {
      const formData = new FormData();
      dateien.forEach((datei) => formData.append("dateien", datei));
      if (bildunterschrift) formData.append("bildunterschrift", bildunterschrift);
      return fetchAPI<MangelFoto[]>(`/maengel/${id}/fotos`, {
        method: "POST",
        body: formData,
      });
    },
    updateFoto: (
      fotoId: number,
      data: Partial<{ bildunterschrift: string; reihenfolge: number }>
    ) => fetchAPI<MangelFoto>(`/maengel/fotos/${fotoId}`, json("PATCH", data)),
    deleteFoto: (fotoId: number) =>
      fetchAPI<void>(`/maengel/fotos/${fotoId}`, { method: "DELETE" }),
    fotoUrl: (fotoId: number, thumb = false) =>
      `${API_BASE}/maengel/fotos/${fotoId}/bild${thumb ? "?thumb=true" : ""}`,

    uploadDateien: (id: number, dateien: File[]) => {
      const formData = new FormData();
      dateien.forEach((datei) => formData.append("dateien", datei));
      return fetchAPI<MangelDatei[]>(`/maengel/${id}/dateien`, {
        method: "POST",
        body: formData,
      });
    },
    deleteDatei: (dateiId: number) =>
      fetchAPI<void>(`/maengel/dateien/${dateiId}`, { method: "DELETE" }),
    dateiUrl: (dateiId: number) => `${API_BASE}/maengel/dateien/${dateiId}/download`,

    setzeMarkierung: (
      id: number,
      data: { plan_datei_id: number; x_prozent: number; y_prozent: number; seite: number }
    ) => fetchAPI<MangelPlanMarkierung>(`/maengel/${id}/markierung`, json("PUT", data)),
    loescheMarkierung: (id: number) =>
      fetchAPI<void>(`/maengel/${id}/markierung`, { method: "DELETE" }),

    senden: (id: number) =>
      fetchAPI<MangelVersandErgebnis>(`/maengel/${id}/senden`, { method: "POST" }),

    exportUrl: (filter: MangelFilter & { intern?: boolean }) =>
      `${API_BASE}/maengel/export${query({ ...filter })}`,
  },

  /* ───────── Baufotos ───────── */

  baufotos: {
    list: (filter: FotosatzFilter = {}) =>
      fetchAPI<FotosatzListItem[]>(`/fotosaetze${query({ ...filter })}`),
    /** Bisher benutzte Kategorien — Vorschläge für das Formular. */
    kategorien: (projektId?: number) =>
      fetchAPI<string[]>(`/fotosaetze/kategorien${query({ projekt_id: projektId })}`),
    get: (id: number) => fetchAPI<Fotosatz>(`/fotosaetze/${id}`),
    create: (data: {
      projekt_id: number;
      kategorie: string;
      datum?: string | null;
      notiz?: string;
    }) => fetchAPI<Fotosatz>("/fotosaetze", json("POST", data)),
    update: (
      id: number,
      data: Partial<{ kategorie: string; datum: string | null; notiz: string }>
    ) => fetchAPI<Fotosatz>(`/fotosaetze/${id}`, json("PATCH", data)),
    delete: (id: number) =>
      fetchAPI<void>(`/fotosaetze/${id}`, { method: "DELETE" }),

    uploadFotos: (id: number, dateien: File[]) => {
      const formData = new FormData();
      dateien.forEach((datei) => formData.append("dateien", datei));
      return fetchAPI<Baufoto[]>(`/fotosaetze/${id}/fotos`, {
        method: "POST",
        body: formData,
      });
    },
    deleteFoto: (fotoId: number) =>
      fetchAPI<void>(`/fotosaetze/fotos/${fotoId}`, { method: "DELETE" }),
    fotoUrl: (fotoId: number, thumb = false) =>
      `${API_BASE}/fotosaetze/fotos/${fotoId}/bild${thumb ? "?thumb=true" : ""}`,

    /** Fertiges Archiv — genau die Datei, die ins Projektarchiv gehört. */
    zipUrl: (id: number) => `${API_BASE}/fotosaetze/${id}/zip`,
    melden: (id: number) =>
      fetchAPI<FotosatzVersand>(`/fotosaetze/${id}/melden`, { method: "POST" }),

    /* ── Per E-Mail verschicken ── */

    /** Kann der Server selbst senden? Bestimmt, welche Knöpfe erscheinen. */
    mailFaehigkeiten: () =>
      fetchAPI<FotosatzMailFaehigkeiten>("/fotosaetze/mail/faehigkeiten"),
    /** Vorbelegung des Dialogs (Betreff, Text, Größe des Anhangs). */
    mailVorschlag: (id: number) =>
      fetchAPI<FotosatzMailVorschlag>(`/fotosaetze/${id}/mail/vorschlag`),
    /** Wirklich verschicken — nur mit hinterlegtem Postausgangsserver. */
    mailSenden: (id: number, data: FotosatzMailAnfrage) =>
      fetchAPI<FotosatzMailErgebnis>(
        `/fotosaetze/${id}/mail/senden`,
        json("POST", data)
      ),
    /** Fertige Mail als .eml — Outlook öffnet sie als Entwurf zum Senden. */
    mailEntwurf: (id: number, data: FotosatzMailAnfrage) =>
      fetchDatei(`/fotosaetze/${id}/mail/entwurf`, json("POST", data)),
  },

  /**
   * Projektberichte (Monatsberichte).
   *
   * ``gliederung`` liefert das Kapitelgerüst — das Formular baut sich daraus
   * auf, damit ein neues Kapitel im Backend genügt (siehe
   * services/projektbericht_gliederung).
   */
  projektberichte: {
    gliederung: () =>
      fetchAPI<GliederungHauptkapitel[]>("/projektberichte/gliederung"),
    list: (projektId?: number) =>
      fetchAPI<ProjektberichtListItem[]>(
        `/projektberichte${query({ projekt_id: projektId })}`
      ),
    vorlage: (projektId: number) =>
      fetchAPI<ProjektberichtEingabe & { projekt_id: number }>(
        `/projektberichte/vorlage${query({ projekt_id: projektId })}`
      ),
    get: (id: number) => fetchAPI<Projektbericht>(`/projektberichte/${id}`),
    create: (data: ProjektberichtEingabe & { projekt_id: number; aus_letztem_bericht?: boolean }) =>
      fetchAPI<Projektbericht>("/projektberichte", json("POST", data)),
    update: (id: number, data: ProjektberichtEingabe) =>
      fetchAPI<Projektbericht>(`/projektberichte/${id}`, json("PATCH", data)),
    delete: (id: number) =>
      fetchAPI<void>(`/projektberichte/${id}`, { method: "DELETE" }),

    vorschau: (id: number) =>
      fetchAPI<ProjektberichtVorschau>(`/projektberichte/${id}/vorschau`),

    fotosHochladen: (id: number, dateien: File[]) => {
      const formData = new FormData();
      dateien.forEach((datei) => formData.append("dateien", datei));
      return fetchAPI<ProjektberichtFoto[]>(`/projektberichte/${id}/fotos`, {
        method: "POST",
        body: formData,
      });
    },
    fotoAendern: (fotoId: number, data: { bildunterschrift?: string; reihenfolge?: number }) =>
      fetchAPI<ProjektberichtFoto>(`/projektberichte/fotos/${fotoId}`, json("PATCH", data)),
    fotoLoeschen: (fotoId: number) =>
      fetchAPI<void>(`/projektberichte/fotos/${fotoId}`, { method: "DELETE" }),
    fotoUrl: (fotoId: number) => `${API_BASE}/projektberichte/fotos/${fotoId}/bild`,

    /** Erzeugt neu und legt am Bericht ab. */
    erzeugen: (id: number, format: "docx" | "pdf") =>
      fetchDatei(`/projektberichte/${id}/dokument?format=${format}`, { method: "POST" }),
    /** Holt das zuletzt erzeugte Dokument aus der Ablage. */
    abrufen: (id: number, format: "docx" | "pdf") =>
      fetchDatei(`/projektberichte/${id}/dokument?format=${format}`),
  },

  /**
   * Mängelanzeige: Anschreiben und Anlage als zwei Word-Dateien.
   *
   * ``dokumente`` liefert absichtlich ein ZIP mit beiden Dateien — ein Vorgang
   * besteht aus Brief und Fotoanlage. Einzeln geht auch, zusammengeführt nie.
   */
  maengelanzeige: {
    vorbelegung: (projektId: number, gewerkId?: number | null) =>
      fetchAPI<MaengelanzeigeVorbelegung>(
        `/maengelanzeige/vorbelegung${query({
          projekt_id: projektId,
          gewerk_id: gewerkId ?? undefined,
        })}`
      ),
    vorschau: (data: MaengelanzeigeAnfrage) =>
      fetchAPI<MaengelanzeigeVorschau>(
        "/maengelanzeige/vorschau",
        json("POST", data)
      ),
    /** Beide Dokumente als ZIP. */
    dokumente: (data: MaengelanzeigeAnfrage) =>
      fetchDatei("/maengelanzeige/dokumente", json("POST", data)),
    /** Nur eines der beiden — für den Nachschub, wenn eines schon verschickt ist. */
    dokument: (data: MaengelanzeigeAnfrage, nur: "anschreiben" | "anlage") =>
      fetchDatei(`/maengelanzeige/dokumente?nur=${nur}`, json("POST", data)),
  },
};
