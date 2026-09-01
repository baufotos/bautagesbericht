/**
 * Eine im Browser erzeugte Datei zum Speichern anbieten.
 *
 * Nötig, weil die Mail-Entwurfsdatei nicht per Link erreichbar ist: Sie
 * entsteht erst durch einen POST mit Empfängern und Text. Der Umweg über einen
 * Objekt-URL ist der übliche Weg dafür.
 *
 * Der URL wird gleich wieder freigegeben — sonst hält der Browser den ganzen
 * Anhang im Speicher, und bei zwanzig Fotos sind das schnell 15 MB.
 */
export function dateiSpeichern(blob: Blob, dateiname: string): void {
  const url = URL.createObjectURL(blob);
  const anker = document.createElement("a");
  anker.href = url;
  anker.download = dateiname;
  document.body.appendChild(anker);
  anker.click();
  anker.remove();
  // Erst im nächsten Zyklus freigeben, sonst bricht der Download in Safari ab.
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/**
 * ``mailto:``-Adresse mit Betreff und Text — der Notausgang ohne Anhang.
 *
 * Anhänge kann ``mailto:`` nicht, das lässt kein Mailprogramm zu. Der Weg ist
 * für die Kollegen gedacht, bei denen sich die ``.eml`` nicht öffnet (neues
 * Outlook, Outlook im Browser): Mailfenster öffnen, ZIP daneben herunterladen
 * und selbst anhängen.
 */
export function mailtoAdresse(
  empfaenger: string[],
  betreff: string,
  text: string
): string {
  const felder = new URLSearchParams();
  if (betreff) felder.set("subject", betreff);
  if (text) felder.set("body", text);
  // URLSearchParams kodiert Leerzeichen als "+", was in mailto: als Plus
  // ankommt. Deshalb auf die Prozentschreibweise umstellen.
  const anhang = felder.toString().replace(/\+/g, "%20");
  return `mailto:${empfaenger.join(",")}${anhang ? `?${anhang}` : ""}`;
}
