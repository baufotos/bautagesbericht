export interface Projekt {
  id: number;
  name: string;
  adresse: string;
  lat: number | null;
  lon: number | null;
  teams_webhook_url: string;
  /**
   * Zielordner der Baufotos im Netzlaufwerk, z. B.
   * "L:\\Bauleitung-Hamburg\\K30159 Kita Nord\\01 FOTOS".
   * Leer = das Abholskript im Büro bildet den Pfad nach seiner Standardregel.
   */
  foto_zielpfad: string;
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
  /**
   * Hält den Bericht auf, bis jemand bestätigt.
   * false = nur ein Hinweis, das Dokument entsteht trotzdem.
   */
  blockiert?: boolean;
}

/* ───────── Wochenpaket: einmal hochladen, fünf Tagesberichte ───────── */

export interface WochenQuelle {
  /** Nur der Dateiname innerhalb des Pakets, nie ein Pfad. */
  datei: string;
  /** 1-basiert wie im PDF-Betrachter. Leer = ganze Datei. */
  seiten: number[];
}

export interface WochenTag {
  /** null = kein Datum erkannt, muss von Hand gesetzt werden. */
  datum: string | null;
  quellen: WochenQuelle[];
  anzahl_seiten: number;
  ergaenzende_angaben: string;
}

export interface WochenAnalyse {
  /** Kennung der Zwischenablage — gehört in den zweiten Aufruf. */
  kennung: string;
  dateien: string[];
  tage: WochenTag[];
  ohne_datum: WochenTag | null;
  hinweise: string[];
}

export interface WochenErgebnis {
  einreichungen: Einreichung[];
  hinweise: string[];
}

/** Was die App auf diesem Rechner kann. */
export interface EinreichungFaehigkeiten {
  /** Können Fotos und Scans gelesen werden? Braucht einen Anthropic-Schlüssel. */
  handschrift: boolean;
  hinweis: string;
}

/* ───────── Mängelmanagement ───────── */

export type Prioritaet = "hoch" | "mittel" | "niedrig";
export type Versendemodus = "manuell" | "automatisch";

export interface Gewerk {
  id: number;
  projekt_id: number;
  firma_name: string;
  vergabeeinheit_code: string;
  vergabeeinheit_bezeichnung: string;
  email: string | null;
  /* Postanschrift für den Adressblock der Mängelanzeige — sonst nicht gebraucht. */
  ansprechpartner: string;
  strasse: string;
  plz: string;
  ort: string;
  teams_webhook_url: string;
  erstellt_am: string;
  /** "Rolfes Bau GmbH | VE300-01 Erweiterter Rohbau" */
  anzeige_name: string;
}

export interface MangelTyp {
  id: number;
  bezeichnung: string;
  sortierung: number;
}

export interface MangelStatus {
  id: number;
  bezeichnung: string;
  sortierung: number;
  farbe: string;
  ist_abgeschlossen: boolean;
}

export interface MangelRueckmeldungStatus {
  id: number;
  bezeichnung: string;
  sortierung: number;
}

export interface Bearbeiter {
  id: number;
  name: string;
  email: string | null;
  /** Kürzel und Durchwahl für die Kopfzeile des Besprechungsprotokolls. */
  kuerzel: string;
  durchwahl: string;
}

export interface MangelStammdaten {
  typen: MangelTyp[];
  status: MangelStatus[];
  rueckmeldung_status: MangelRueckmeldungStatus[];
  bearbeiter: Bearbeiter[];
  prioritaeten: Prioritaet[];
  versendemodi: Versendemodus[];
}

export interface ProjektPlan {
  id: number;
  projekt_id: number;
  dateiname: string;
  seiten: number;
  hochgeladen_am: string;
}

export interface MangelPlanMarkierung {
  id: number;
  mangel_id: number;
  plan_datei_id: number;
  plan_dateiname: string;
  /** Position in Prozent der Planfläche — bildschirmunabhängig. */
  x_prozent: number;
  y_prozent: number;
  seite: number;
}

export interface MangelFoto {
  id: number;
  mangel_id: number;
  bildunterschrift: string;
  reihenfolge: number;
  aufgenommen_am: string | null;
}

export interface MangelDatei {
  id: number;
  mangel_id: number;
  dateiname: string;
  hochgeladen_am: string | null;
}

/** Eine Zeile der Mängel-Übersicht. */
export interface MangelListItem {
  id: number;
  projekt_id: number;
  projekt_name: string;
  nummer: string;
  typ: string;
  status: string;
  status_farbe: string;
  gewerk_id: number | null;
  gewerk_anzeige: string;
  firma_name: string;
  raumnummer: string | null;
  hinweis_ort: string;
  prioritaet: string;
  kurzbezeichnung: string;
  farbmarkierung: string;
  erstellt_am: string;
  erste_frist_bis: string | null;
  /** Nachfrist schlägt die erste Frist. */
  aktuelle_frist: string | null;
  ist_ueberfaellig: boolean;
  ist_abgeschlossen: boolean;
  anzahl_fotos: number;
  titel_foto_id: number | null;
  eltern_mangel_id: number | null;
  anzahl_duplikate: number;
}

export interface Mangel extends MangelListItem {
  beschreibung: string;
  interne_bemerkung: string;
  aufgenommen_von: string;
  zustaendiger_user_id: number | null;
  zustaendiger_user_name: string;
  erste_nachfrist_gesetzt_am: string | null;
  erste_nachfrist_bis: string | null;
  anmerkung_nachfrist: string;
  beseitigungsanzeige_am: string | null;
  freigemeldet_am: string | null;
  erledigt_am: string | null;
  zurueckweisung_am: string | null;
  rueckmeldung_status: string;
  mail_autosend: boolean;
  mail_versendemodus: string;
  zuletzt_versendet_am: string | null;
  angelegt_am: string | null;
  eltern_nummer: string;
  eltern_kurzbezeichnung: string;
  /** "Fehler! Firma/Büro hat keine Email-Adresse" o. ä., sonst null. */
  mail_fehler: string | null;
  fotos: MangelFoto[];
  dateien: MangelDatei[];
  markierung: MangelPlanMarkierung | null;
}

export interface MangelVersandErgebnis {
  mangel_id: number;
  versendet: boolean;
  kanal: string;
  nachricht: string;
  zuletzt_versendet_am: string | null;
}

/** Felder, die beim Anlegen eines Mangels mitgegeben werden können. */
export interface MangelCreateInput {
  projekt_id: number;
  kurzbezeichnung: string;
  typ?: string;
  status?: string;
  gewerk_id?: number | null;
  raumnummer?: string | null;
  hinweis_ort?: string;
  prioritaet?: Prioritaet;
  beschreibung?: string;
  farbmarkierung?: string;
  interne_bemerkung?: string;
  erstellt_am?: string | null;
  erste_frist_bis?: string | null;
  aufgenommen_von?: string;
  zustaendiger_user_id?: number | null;
  rueckmeldung_status?: string;
  mail_autosend?: boolean;
  mail_versendemodus?: Versendemodus;
  nummer?: string | null;
}

/** Teil-Aktualisierung: Nur mitgesendete Felder werden geschrieben. */
export type MangelUpdateInput = Partial<
  Omit<MangelCreateInput, "projekt_id"> & {
    erste_nachfrist_gesetzt_am: string | null;
    erste_nachfrist_bis: string | null;
    anmerkung_nachfrist: string;
    beseitigungsanzeige_am: string | null;
    freigemeldet_am: string | null;
    erledigt_am: string | null;
    zurueckweisung_am: string | null;
  }
>;

export interface MangelFilter {
  projekt_id?: number;
  status?: string;
  gewerk_id?: number;
  prioritaet?: string;
  typ?: string;
  ueberfaellig?: boolean;
  abgeschlossen?: boolean;
  suche?: string;
}

/* ───────── Baufotos ───────── */

export interface Baufoto {
  id: number;
  fotosatz_id: number;
  /** Der umbenannte Name — so heißt die Datei später im Projektordner. */
  dateiname: string;
  original_dateiname: string;
  reihenfolge: number;
  groesse_bytes: number;
  hochgeladen_am: string | null;
}

/** Eine Karte in der Fotosatz-Übersicht. */
export interface FotosatzListItem {
  id: number;
  projekt_id: number;
  projekt_name: string;
  kategorie: string;
  datum: string;
  notiz: string;
  anzahl_fotos: number;
  titel_foto_id: number | null;
  /** Name des ZIP-Archivs, so wie es heruntergeladen wird. */
  zip_dateiname: string;
  groesse_bytes: number;
  erstellt_am: string | null;
  zuletzt_gemeldet_am: string | null;
  /** Wann der Satz per E-Mail herausging (oder als Entwurf erzeugt wurde). */
  mail_versendet_am: string | null;
  /** Alle Adressen, an die er ging — zur Nachvollziehbarkeit. */
  mail_empfaenger: string;
  /** "smtp" = die App hat verschickt, "entwurf" = Outlook hat den Entwurf. */
  mail_weg: string;
  /** Wann ein Bürorechner den Satz ins Projektverzeichnis gelegt hat. */
  abgeholt_am: string | null;
  /** Welcher Rechner das war — steht im Protokoll der Abholung. */
  abgeholt_von: string;
  /** Der vollständige Ordner, in dem die Fotos jetzt liegen. */
  abgeholt_ziel: string;
}

export interface Fotosatz extends FotosatzListItem {
  fotos: Baufoto[];
}

export interface FotosatzVersand {
  fotosatz_id: number;
  gemeldet: boolean;
  kanal: string;
  nachricht: string;
}

/** Was der Server beim Mailversand kann — steuert die Knöpfe im Dialog. */
export interface FotosatzMailFaehigkeiten {
  smtp: boolean;
  absender: string;
  max_anhang_mb: number;
}

/** Vorbelegung des Mail-Dialogs, vom Server berechnet. */
export interface FotosatzMailVorschlag {
  betreff: string;
  nachricht: string;
  zip_dateiname: string;
  groesse_bytes: number;
  passt: boolean;
  hinweis: string;
}

export interface FotosatzMailAnfrage {
  empfaenger: string[];
  kopie?: string[];
  betreff?: string;
  nachricht?: string;
}

export interface FotosatzMailErgebnis {
  fotosatz_id: number;
  versendet: boolean;
  empfaenger: string[];
  nachricht: string;
}

/* ───────────────────────── Projektbericht (Monatsbericht) ───────────────────────── */

export interface Baubegehung {
  datum: string;
  teilnehmer: string;
  firma: string;
}

export interface Besprechung {
  bezeichnung: string;
  rhythmus: string;
  uhrzeit: string;
}

export interface SollIstZeile {
  bezeichnung: string;
  soll: string;
  ist: string;
  verzug: string;
}

export interface ProjektberichtFoto {
  id: number;
  bericht_id: number;
  bildunterschrift: string;
  reihenfolge: number;
  hochgeladen_am: string | null;
}

export interface GliederungUnterkapitel {
  schluessel: string;
  titel: string;
  /** "text" | "baubegehungen" | "besprechungen" | "sollist" | "fotos" */
  art: string;
  /** Erscheint auch ohne Inhalt (1.1-1.4). */
  immer_zeigen: boolean;
}

export interface GliederungHauptkapitel {
  schluessel: string;
  titel: string;
  art: string;
  ohne_ueberschrift: boolean;
  unterkapitel: GliederungUnterkapitel[];
}

export interface ProjektberichtListItem {
  id: number;
  projekt_id: number;
  projekt_name: string;
  nummer: number;
  berichtsdatum: string;
  zeitraum_von: string | null;
  zeitraum_bis: string | null;
  ersteller: string;
  projektname: string;
  projektkuerzel: string;
  anzahl_fotos: number;
  /** Wie viele Kapitel im Dokument erschienen. */
  anzahl_kapitel: number;
  hat_dokument: boolean;
  hat_pdf: boolean;
  erzeugt_am: string | null;
  erstellt_am: string | null;
  geaendert_am: string | null;
}

export interface Projektbericht extends ProjektberichtListItem {
  buero: string;
  kapitel: Record<string, string>;
  baubegehungen: Baubegehung[];
  besprechungen: Besprechung[];
  soll_ist: SollIstZeile[];
  fotos: ProjektberichtFoto[];
}

export interface ProjektberichtEingabe {
  nummer?: number | null;
  berichtsdatum?: string | null;
  zeitraum_von?: string | null;
  zeitraum_bis?: string | null;
  ersteller?: string;
  projektname?: string;
  projektkuerzel?: string;
  buero?: string;
  kapitel?: Record<string, string>;
  baubegehungen?: Baubegehung[];
  besprechungen?: Besprechung[];
  soll_ist?: SollIstZeile[];
}

export interface ProjektberichtVorschauKapitel {
  nummer: string;
  titel: string;
  ebene: number;
  schluessel: string;
  art: string;
  hat_inhalt: boolean;
}

export interface ProjektberichtVorschau {
  dateiname_docx: string;
  dateiname_pdf: string;
  kapitel: ProjektberichtVorschauKapitel[];
  /** Kapitel, die mangels Inhalt entfallen. */
  entfallen: string[];
  anzahl_fotos: number;
  /** PDF geht nur, wo Word installiert ist. */
  pdf_moeglich: boolean;
}

/* ───────────────────────── Mängelanzeige (zwei Word-Dateien) ───────────────────────── */

export interface MaengelanzeigeEmpfaenger {
  firma: string;
  /** Wie im Adressfeld, also „Herrn Hey“ — die Anrede formt der Server daraus. */
  ansprechpartner: string;
  strasse_hausnummer: string;
  plz_ort: string;
  versandart: string;
  email: string | null;
}

export interface MaengelanzeigeSachbearbeiter {
  name: string;
  funktion: string;
  zeichen: string;
  auftragsnummer: string;
  email: string | null;
}

export interface MaengelanzeigeVorbelegung {
  projektbezeichnung: string;
  vergabeeinheit: string;
  dokumentkuerzel: string;
  begehungsdatum: string;
  briefdatum: string;
  fristsetzungsdatum: string;
  empfaenger: MaengelanzeigeEmpfaenger;
  betreff_dritte_zeile: string;
}

export interface MaengelanzeigeAnfrage {
  projekt_id: number;
  gewerk_id: number | null;
  mangel_ids: number[];
  empfaenger: MaengelanzeigeEmpfaenger;
  sachbearbeiter: MaengelanzeigeSachbearbeiter;
  begehungsdatum: string;
  briefdatum?: string | null;
  fristsetzungsdatum?: string | null;
  anlagedatum?: string | null;
  projektbezeichnung?: string;
  vergabeeinheit?: string;
  dokumentkuerzel?: string;
}

export interface MaengelanzeigeBereichVorschau {
  bereich: string;
  anzahl_fotos: number;
  beschreibungen: string[];
}

export interface MaengelanzeigeVorschau {
  dateiname_anschreiben: string;
  dateiname_anlage: string;
  fristsetzungsdatum: string;
  anzahl_fotos: number;
  bereiche: MaengelanzeigeBereichVorschau[];
  /** Übersprungene Mängel (kein Foto, Datei fehlt) — Hinweis, kein Fehler. */
  hinweise: string[];
}

export interface FotosatzFilter {
  projekt_id?: number;
  kategorie?: string;
  suche?: string;
}

/* ───────────────────────── Baubesprechungsprotokolle ─────────────────────────
 *
 * Der Zuschnitt spiegelt das Backend: Ein `BesprechungsThema` lebt am Projekt
 * und überdauert beliebig viele Sitzungen, ein `ThemaUpdate` ist sein Stand in
 * genau einem Protokoll — und damit die Zeile, die gedruckt wird.
 */

/** k kritisch · b in Bearbeitung · e erledigt · n neu · i informativ */
export type BesprechungStatus = "k" | "b" | "e" | "n" | "i";

export type ProtokollStatus = "entwurf" | "geprueft" | "freigegeben";

export interface BesprechungsKapitel {
  id: number;
  projekt_id: number;
  nummer: string;
  titel: string;
  sortierung: number;
  gewerk_id: number | null;
  anzahl_themen: number;
}

export interface Projektbeteiligter {
  id: number;
  projekt_id: number;
  kuerzel: string;
  name: string;
  rolle: string;
  ansprechpartner: string;
  telefon: string;
  sortierung: number;
}

/** Ein Sachverhalt der laufenden Themenliste des Projekts. */
export interface BesprechungsThema {
  id: number;
  projekt_id: number;
  kapitel_id: number;
  kapitel_nummer: string;
  kapitel_titel: string;
  inhalt_nr: string;
  thema: string;
  zustaendig: string;
  bearb_bis: string;
  status: BesprechungStatus;
  erledigt_am: string | null;
  zuletzt_bb: number | null;
  erstmals_bb: number | null;
  /** "02. 08." — Kapitel und laufende Nummer ohne die BB-Nummer. */
  kennung: string;
}

/** Eine Druckzeile: der Stand eines Themas in diesem Protokoll. */
export interface ThemaUpdate {
  id: number;
  protokoll_id: number;
  thema_id: number;
  thema_text: string;
  zustaendig: string;
  bearb_bis: string;
  status: BesprechungStatus;
  hervorheben: boolean;
  sortierung: number;
  bestaetigt: boolean;
  herkunft: "ki" | "mensch" | "fortschreibung";
  /** Vollständig, wie gedruckt: "02. 08. 16". */
  nummer: string;
  /** Die Sitzung, aus der die Zeile stammt — bei Übernahmen eine ältere. */
  bb_nr: string;
  uebernommen: boolean;
  kapitel_id: number;
  kapitel_nummer: string;
  kapitel_titel: string;
  inhalt_nr: string;
  vorher_text: string;
  vorher_status: string;
  vorher_bb: number | null;
}

export interface BesprechungsTeilnehmer {
  id: number;
  protokoll_id: number;
  name: string;
  firma_kuerzel: string;
  telefon: string;
  anwesend: boolean;
  reihenfolge: number;
  aus_transkript: boolean;
}

export interface BesprechungsAnlage {
  id: number;
  protokoll_id: number;
  dateiname: string;
  bezeichnung: string;
  reihenfolge: number;
  hochgeladen_am: string | null;
}

export interface ProtokollListItem {
  id: number;
  projekt_id: number;
  projekt_name: string;
  nummer: number;
  leistung: string;
  besprechungsort: string;
  besprechungsdatum: string;
  ersteller_name: string;
  ersteller_kuerzel: string;
  status: ProtokollStatus;
  anzahl_themen: number;
  anzahl_offen: number;
  anzahl_teilnehmer: number;
  anzahl_anlagen: number;
  anzahl_ungeprueft: number;
  hat_transkript: boolean;
  hat_dokument: boolean;
  hat_pdf: boolean;
  analyse_am: string | null;
  erzeugt_am: string | null;
  erstellt_am: string | null;
  geaendert_am: string | null;
}

export interface Protokoll extends ProtokollListItem {
  ersteller_id: number | null;
  ersteller_durchwahl: string;
  ersteller_email: string;
  tldv_transkript_roh: string;
  tldv_notizen_roh: string;
  analyse_hinweise: string[];
  geprueft_am: string | null;
  freigegeben_am: string | null;
  themen_updates: ThemaUpdate[];
  teilnehmer: BesprechungsTeilnehmer[];
  anlagen: BesprechungsAnlage[];
  projekt_nummer: string;
  bauherr: string;
  projekt_adresse: string;
}

export interface ProtokollAnlegen {
  projekt_id: number;
  besprechungsdatum: string;
  leistung?: string;
  besprechungsort?: string;
  ersteller_id?: number | null;
  ersteller_name?: string;
  ersteller_kuerzel?: string;
  ersteller_durchwahl?: string;
  ersteller_email?: string;
  offene_punkte_uebernehmen?: boolean;
}

export interface AnalyseErgebnis {
  neue_themen: number;
  fortschreibungen: number;
  teilnehmer: number;
  hinweise: string[];
}
