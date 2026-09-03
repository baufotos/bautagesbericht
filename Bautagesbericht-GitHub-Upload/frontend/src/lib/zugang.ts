/**
 * Passwortschutz der Weboberfläche — siehe app.security auf dem Server.
 *
 * Das Passwort wird nach der ersten erfolgreichen Anmeldung im Browser
 * gespeichert (localStorage), damit nicht bei jedem Aufruf neu gefragt
 * wird. Es verlässt den Browser nur als Kopf ``X-Seiten-Passwort`` bei
 * jedem API-Aufruf — dort prüft der Server es gegen
 * ``BTB_SEITEN_PASSWORT``.
 *
 * Try/catch überall: Im privaten Modus oder mit blockiertem Speicher
 * wirft localStorage — dann wird eben bei jedem Aufruf erneut gefragt,
 * statt dass die ganze App abstürzt.
 */

const SCHLUESSEL = "hpp-seiten-passwort";

export function passwortLesen(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(SCHLUESSEL) || "";
  } catch {
    return "";
  }
}

export function passwortSpeichern(passwort: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SCHLUESSEL, passwort);
  } catch {
    /* siehe Hinweis oben */
  }
}
