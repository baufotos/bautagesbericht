export interface Projekt {
  id: number;
  name: string;
  adresse: string;
  lat: number | null;
  lon: number | null;
  erstellt_am: string;
}

export interface Empfaenger {
  id: number;
  label: string;
  email: string;
  teams_webhook_url: string;
  erstellt_am: string;
}

export interface Einreichung {
  id: number;
  projekt_id: number;
  projekt_name: string;
  empfaenger_id: number;
  empfaenger_label: string;
  empfaenger_email: string;
  datum: string;
  ergaenzende_angaben: string | null;
  status: string;
  quelle_dateien: string[];
  warnungen: Warnung[];
  eingereicht_am: string;
  verarbeitet_am: string | null;
}

export interface Warnung {
  feld: string;
  problem: string;
  quelle_datei?: string;
}
