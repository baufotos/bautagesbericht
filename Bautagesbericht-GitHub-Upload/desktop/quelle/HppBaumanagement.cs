// HPP Baumanagement — Startprogramm für Windows
// =============================================
//
// WAS DIESES PROGRAMM IST
// -----------------------
// Eine kleine Datei zum Doppelklicken, die die App in einem eigenen Fenster
// öffnet: kein Adressfeld, keine Lesezeichen, keine fremden Tabs, eigenes
// Symbol in der Taskleiste.
//
// ZWEI BETRIEBSARTEN — das Programm erkennt sie selbst
// ---------------------------------------------------
// 1. PAKET: Liegt neben der Datei ein Ordner "laufzeit" mit portablem Python,
//    dann bringt das Paket die ganze App mit. Das Programm startet den Server
//    selbst, wartet, bis er antwortet, öffnet das Fenster und beendet den
//    Server wieder, wenn das Fenster geschlossen wird. Kein Internet nötig,
//    keine Installation, keine Administratorrechte.
//
// 2. FERN: Ohne "laufzeit"-Ordner wird die zentrale Adresse geöffnet (aus
//    app-url.txt oder der eingebauten Standardadresse). Das ist der Weg, wenn
//    die App auf einem Server läuft und alle im Team denselben Stand sehen.
//
// Beide Wege zeigen dieselbe Oberfläche. Der Unterschied ist nur, WO die Daten
// liegen — beim Paket standardmäßig auf diesem Rechner, in der Fernvariante
// zentral. Für gemeinsames Arbeiten mit dem Paket trägt man in
// einstellungen.txt eine zentrale Datenbank ein (siehe Zuerst-lesen.txt).
//
// WARUM DER APP-MODUS DES BROWSERS
// --------------------------------
// Gestartet wird Edge (auf jedem Windows vorhanden) bzw. Chrome mit "--app=".
// Das ist kein "Browser aufmachen": Der App-Modus hat kein Adressfeld, keine
// Tab-Leiste und ein eigenes Fenster. Dazu ein eigenes Browserprofil unter
// %LOCALAPPDATA%\HPP-Baumanagement, damit das App-Fenster nicht zwischen
// vierzig privaten Tabs verschwindet und der Offline-Speicher erhalten bleibt.
//
// Übersetzt wird mit dem C#-Compiler, der auf jedem Windows liegt
// (siehe quelle\bauen.ps1). Kein SDK, kein NuGet, keine Abhängigkeit.
//
// AUFRUFE
//   HPP-Baumanagement.exe                    App öffnen
//   HPP-Baumanagement.exe --pruefen          Selbsttest
//   HPP-Baumanagement.exe --verknuepfung     Desktop-Verknüpfung anlegen
//   HPP-Baumanagement.exe --url <adresse>    einmalig andere Adresse (Fernmodus)
//   HPP-Baumanagement.exe --port 9000        anderer Port (Paketmodus)

using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("HPP Baumanagement")]
[assembly: AssemblyProduct("HPP Baumanagement")]
[assembly: AssemblyCompany("HPP Architekten")]
[assembly: AssemblyDescription("Bautagesberichte, Mängelberichte und Baufotos")]
[assembly: AssemblyVersion("1.1.0.0")]
[assembly: AssemblyFileVersion("1.1.0.0")]

internal static class Programm
{
    /// <summary>
    /// Adresse für den Fernmodus, wenn keine app-url.txt daneben liegt.
    /// </summary>
    private const string StandardAdresse = "https://bautagesbericht-jwga.onrender.com";

    private const string Titel = "HPP Baumanagement";
    private const string Fenstergroesse = "--window-size=1400,920";

    /// <summary>
    /// Startport im Paketmodus. Ist er belegt, wird weitergezählt; antwortet
    /// dort schon unsere eigene App, wird sie mitbenutzt.
    /// </summary>
    private const int StartPort = 8765;

    /// <summary>
    /// Wie lange auf den Server gewartet wird. Der erste Start eines Rechners
    /// muss Python-Module einlesen und die Datenbank anlegen — das dauert
    /// spürbar länger als jeder weitere.
    /// </summary>
    private const int WartenSekunden = 90;

    private static string _adressQuelle = "eingebaute Standardadresse";

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            if (HatSchalter(args, "--verknuepfung"))
            {
                return VerknuepfungAnlegen();
            }

            bool nurPruefen = HatSchalter(args, "--pruefen");

            if (IstPaket() && !HatWert(args, "--url"))
            {
                return nurPruefen ? SelbsttestPaket(args) : StartenAusPaket(args);
            }

            string adresse = AdresseErmitteln(args);
            return nurPruefen ? SelbsttestFern(adresse) : StartenFern(adresse);
        }
        catch (Exception fehler)
        {
            Melden("Die App konnte nicht gestartet werden.\n\n" + fehler.Message,
                   MessageBoxIcon.Error);
            return 1;
        }
    }

    // ─────────────────────────── Kommandozeile ───────────────────────────

    private static bool HatSchalter(string[] args, string name)
    {
        string kurz = name.TrimStart('-');
        foreach (string wert in args)
        {
            if (string.Equals(wert.TrimStart('-'), kurz, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }
        return false;
    }

    private static bool HatWert(string[] args, string name)
    {
        return WertVon(args, name) != null;
    }

    private static string WertVon(string[] args, string name)
    {
        string kurz = name.TrimStart('-');
        for (int i = 0; i < args.Length - 1; i++)
        {
            if (string.Equals(args[i].TrimStart('-'), kurz, StringComparison.OrdinalIgnoreCase))
            {
                return args[i + 1];
            }
        }
        return null;
    }

    // ──────────────────────────── Pfade, Paket ───────────────────────────

    private static string Ordner()
    {
        return AppDomain.CurrentDomain.BaseDirectory;
    }

    private static string PythonPfad()
    {
        return Path.Combine(Ordner(), @"laufzeit\python\python.exe");
    }

    private static string ServerSkript()
    {
        return Path.Combine(Ordner(), @"laufzeit\server_starten.py");
    }

    /// <summary>Paketmodus, wenn Python und Serverskript daneben liegen.</summary>
    private static bool IstPaket()
    {
        return File.Exists(PythonPfad()) && File.Exists(ServerSkript());
    }

    private static string DatenOrdner()
    {
        // Muss zur Vorgabe in server_starten.py passen. Nur für Hinweistexte —
        // aber genau dann wichtig, wenn der Server NICHT startet: Dann schickt
        // die Meldung den Kollegen zur protokoll.txt. Steht in
        // einstellungen.txt ein eigener "datenordner" (Teambetrieb auf dem
        // Netzlaufwerk), liegt das Protokoll dort und nicht neben dem Programm.
        string ausDatei = EinstellungLesen("datenordner");
        if (!string.IsNullOrEmpty(ausDatei))
        {
            return ausDatei;
        }
        return Path.Combine(Ordner(), "daten");
    }

    /// <summary>
    /// Liest einen Wert aus einstellungen.txt (Schlüssel=Wert, # ist ein
    /// Kommentar). Dieselbe Datei liest server_starten.py; hier wird nur
    /// nachgelesen, damit Hinweistexte denselben Ort nennen.
    /// </summary>
    private static string EinstellungLesen(string schluessel)
    {
        string pfad = Path.Combine(Ordner(), "einstellungen.txt");
        if (!File.Exists(pfad))
        {
            return null;
        }
        try
        {
            foreach (string zeile in File.ReadAllLines(pfad, Encoding.UTF8))
            {
                string text = zeile.Trim();
                if (text.Length == 0 || text.StartsWith("#"))
                {
                    continue;
                }
                int trenner = text.IndexOf('=');
                if (trenner <= 0)
                {
                    continue;
                }
                string name = text.Substring(0, trenner).Trim();
                if (string.Equals(name, schluessel, StringComparison.OrdinalIgnoreCase))
                {
                    string wert = text.Substring(trenner + 1).Trim();
                    return wert.Length > 0 ? wert : null;
                }
            }
        }
        catch (Exception)
        {
            // Eine unlesbare Einstellungsdatei darf den Start nicht verhindern;
            // dann gilt eben der Ordner neben dem Programm.
        }
        return null;
    }

    // ──────────────────────────── Paketmodus ─────────────────────────────

    private static int StartenAusPaket(string[] args)
    {
        int port = PortWaehlen(args);
        string adresse = "http://127.0.0.1:" + port + "/";

        Process server = null;
        if (!ServerAntwortet(adresse, 1500))
        {
            server = ServerStarten(port);
            if (!AufServerWarten(adresse, WartenSekunden))
            {
                if (server != null && !server.HasExited)
                {
                    Beenden(server);
                }
                Melden(
                    "Der Programmteil, der die Daten verwaltet, ist nicht "
                    + "gestartet.\n\nBitte im Ordner\n" + DatenOrdner()
                    + "\ndie Datei protokoll.txt öffnen — dort steht der Grund.\n\n"
                    + "Hilfreich ist auch ein Aufruf mit --pruefen.",
                    MessageBoxIcon.Error);
                return 1;
            }
        }

        Process fenster = FensterOeffnen(adresse);

        // Der Server soll nicht weiterlaufen, wenn niemand mehr hinsieht.
        // Nur beenden, wenn wir ihn selbst gestartet haben UND unser
        // Browserfenster auch wirklich das Fenster war: Läuft die App schon,
        // gibt der neu gestartete Vorgang sofort ab — dann gehört der Server
        // der anderen Sitzung und bleibt stehen.
        if (server != null && fenster != null)
        {
            DateTime start = DateTime.UtcNow;
            try
            {
                fenster.WaitForExit();
            }
            catch (Exception)
            {
                return 0;
            }

            bool warEigenesFenster = (DateTime.UtcNow - start).TotalSeconds > 3;
            if (warEigenesFenster)
            {
                Beenden(server);
            }
        }

        return 0;
    }

    /// <summary>
    /// Freien Port suchen. Antwortet auf einem Port schon unsere App, wird er
    /// genommen — dann öffnet ein zweiter Start einfach ein zweites Fenster
    /// auf dieselbe laufende App statt eine zweite Datenbank anzufassen.
    /// </summary>
    private static int PortWaehlen(string[] args)
    {
        string vorgabe = WertVon(args, "--port");
        int gewuenscht;
        if (vorgabe != null && int.TryParse(vorgabe, out gewuenscht))
        {
            return gewuenscht;
        }

        for (int port = StartPort; port < StartPort + 20; port++)
        {
            if (ServerAntwortet("http://127.0.0.1:" + port + "/", 700))
            {
                return port;   // unsere App läuft schon hier
            }
            if (PortFrei(port))
            {
                return port;
            }
        }
        return StartPort;
    }

    private static bool PortFrei(int port)
    {
        TcpListener horcher = null;
        try
        {
            horcher = new TcpListener(IPAddress.Loopback, port);
            horcher.Start();
            return true;
        }
        catch (SocketException)
        {
            return false;
        }
        finally
        {
            if (horcher != null)
            {
                try { horcher.Stop(); } catch (Exception) { }
            }
        }
    }

    private static Process ServerStarten(int port)
    {
        var start = new ProcessStartInfo
        {
            FileName = PythonPfad(),
            // Anführungszeichen: Der Pfad kann Leerzeichen enthalten
            // ("C:\Users\Vorname Nachname\...").
            Arguments = "\"" + ServerSkript() + "\" --port " + port,
            WorkingDirectory = Ordner(),
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
        };
        return Process.Start(start);
    }

    private static void Beenden(Process vorgang)
    {
        try
        {
            if (!vorgang.HasExited)
            {
                vorgang.Kill();
            }
        }
        catch (Exception)
        {
            // Ein bereits beendeter Vorgang ist kein Fehler.
        }
    }

    private static bool AufServerWarten(string adresse, int sekunden)
    {
        DateTime ende = DateTime.UtcNow.AddSeconds(sekunden);
        while (DateTime.UtcNow < ende)
        {
            if (ServerAntwortet(adresse, 1200))
            {
                return true;
            }
            Thread.Sleep(400);
        }
        return false;
    }

    /// <summary>Fragt /api/health ab — antwortet dort etwas, läuft die App.</summary>
    private static bool ServerAntwortet(string adresse, int zeitlimitMillis)
    {
        try
        {
            var anfrage = (HttpWebRequest)WebRequest.Create(adresse.TrimEnd('/') + "/api/health");
            anfrage.Timeout = zeitlimitMillis;
            anfrage.ReadWriteTimeout = zeitlimitMillis;
            anfrage.Method = "GET";
            using (var antwort = (HttpWebResponse)anfrage.GetResponse())
            {
                return antwort.StatusCode == HttpStatusCode.OK;
            }
        }
        catch (Exception)
        {
            return false;
        }
    }

    // ───────────────────────────── Fernmodus ─────────────────────────────

    private static string AdresseErmitteln(string[] args)
    {
        string ausArgument = WertVon(args, "--url");
        if (ausArgument != null)
        {
            _adressQuelle = "Kommandozeile (--url)";
            return Normalisieren(ausArgument);
        }

        string ausDatei = AusKonfigurationsdatei();
        if (!string.IsNullOrEmpty(ausDatei))
        {
            _adressQuelle = "app-url.txt";
            return Normalisieren(ausDatei);
        }

        _adressQuelle = "eingebaute Standardadresse";
        return Normalisieren(StandardAdresse);
    }

    private static string KonfigurationsPfad()
    {
        return Path.Combine(Ordner(), "app-url.txt");
    }

    private static string AusKonfigurationsdatei()
    {
        string pfad = KonfigurationsPfad();
        if (!File.Exists(pfad))
        {
            return null;
        }
        foreach (string zeile in File.ReadAllLines(pfad, Encoding.UTF8))
        {
            string wert = zeile.Trim();
            if (wert.Length > 0 && !wert.StartsWith("#"))
            {
                return wert;
            }
        }
        return null;
    }

    private static string Normalisieren(string adresse)
    {
        string wert = (adresse ?? string.Empty).Trim();
        if (wert.Length == 0)
        {
            return StandardAdresse;
        }
        if (!wert.StartsWith("http://") && !wert.StartsWith("https://"))
        {
            wert = "https://" + wert;
        }
        return wert;
    }

    private static int StartenFern(string adresse)
    {
        FensterOeffnen(adresse);
        return 0;
    }

    // ───────────────────────────── Browser ──────────────────────────────

    private static string BrowserFinden()
    {
        string programme = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        string programmeX86 = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86);
        string lokal = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);

        string[] kandidaten =
        {
            Path.Combine(programme, @"Microsoft\Edge\Application\msedge.exe"),
            Path.Combine(programmeX86, @"Microsoft\Edge\Application\msedge.exe"),
            Path.Combine(programme, @"Google\Chrome\Application\chrome.exe"),
            Path.Combine(programmeX86, @"Google\Chrome\Application\chrome.exe"),
            Path.Combine(lokal, @"Google\Chrome\Application\chrome.exe"),
        };

        foreach (string pfad in kandidaten)
        {
            if (File.Exists(pfad))
            {
                return pfad;
            }
        }
        return null;
    }

    private static string ProfilOrdner()
    {
        string basis = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string ordner = Path.Combine(basis, "HPP-Baumanagement", "Browserprofil");
        Directory.CreateDirectory(ordner);
        return ordner;
    }

    /// <summary>
    /// Öffnet das App-Fenster. Gibt den Vorgang zurück, oder null, wenn auf den
    /// Standardbrowser ausgewichen wurde (dann lässt sich nichts überwachen).
    /// </summary>
    private static Process FensterOeffnen(string adresse)
    {
        string browser = BrowserFinden();
        if (browser == null)
        {
            Process.Start(new ProcessStartInfo(adresse) { UseShellExecute = true });
            return null;
        }

        var start = new ProcessStartInfo
        {
            FileName = browser,
            UseShellExecute = false,
        };
        start.Arguments = string.Join(" ", new[]
        {
            "--app=" + adresse,
            "--new-window",
            Fenstergroesse,
            "--user-data-dir=\"" + ProfilOrdner() + "\"",
            "--no-first-run",
            "--no-default-browser-check",
        });
        return Process.Start(start);
    }

    // ─────────────────────────── Verknüpfung ────────────────────────────

    private static int VerknuepfungAnlegen()
    {
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        string ziel = Path.Combine(desktop, Titel + ".lnk");
        string programm = Path.Combine(Ordner(), "HPP-Baumanagement.exe");

        Type shellTyp = Type.GetTypeFromProgID("WScript.Shell");
        if (shellTyp == null)
        {
            Melden("Verknüpfungen können auf diesem Rechner nicht angelegt werden. "
                   + "Stattdessen die Programmdatei selbst auf den Desktop kopieren.",
                   MessageBoxIcon.Warning);
            return 1;
        }

        object shell = Activator.CreateInstance(shellTyp);
        object verknuepfung = shellTyp.InvokeMember(
            "CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { ziel });
        Type typ = verknuepfung.GetType();

        SetzeEigenschaft(typ, verknuepfung, "TargetPath", programm);
        SetzeEigenschaft(typ, verknuepfung, "WorkingDirectory", Ordner());
        SetzeEigenschaft(typ, verknuepfung, "Description",
            Titel + " — Bautagesberichte, Mängel und Baufotos");
        SetzeEigenschaft(typ, verknuepfung, "IconLocation", programm + ",0");
        typ.InvokeMember("Save", BindingFlags.InvokeMethod, null, verknuepfung, null);

        Melden("Verknüpfung auf dem Desktop angelegt.", MessageBoxIcon.Information);
        return 0;
    }

    private static void SetzeEigenschaft(Type typ, object ziel, string name, object wert)
    {
        typ.InvokeMember(name, BindingFlags.SetProperty, null, ziel, new[] { wert });
    }

    // ──────────────────────────── Selbsttest ────────────────────────────

    private static int SelbsttestFern(string adresse)
    {
        var text = new StringBuilder();
        text.AppendLine("Betriebsart:    fern (zentrale App)");
        text.AppendLine("Adresse:        " + adresse);
        text.AppendLine("Quelle:         " + _adressQuelle);
        text.AppendLine("Browser:        " + (BrowserFinden() ?? "keiner gefunden (Standardbrowser)"));
        text.AppendLine("Profilordner:   " + ProfilOrdner());
        text.AppendLine("Server:         " + ServerZustand(adresse));
        return Ausgeben(text.ToString());
    }

    private static int SelbsttestPaket(string[] args)
    {
        var text = new StringBuilder();
        text.AppendLine("Betriebsart:    Paket (App liegt daneben)");
        text.AppendLine("Programmordner: " + Ordner());
        text.AppendLine("Python:         " + PythonPfad());
        text.AppendLine("Serverskript:   " + ServerSkript());
        text.AppendLine("Datenordner:    " + DatenOrdner());
        text.AppendLine("Browser:        " + (BrowserFinden() ?? "keiner gefunden (Standardbrowser)"));

        int port = PortWaehlen(args);
        string adresse = "http://127.0.0.1:" + port + "/";
        text.AppendLine("Port:           " + port);

        if (ServerAntwortet(adresse, 1500))
        {
            text.AppendLine("Server:         läuft bereits und antwortet");
            return Ausgeben(text.ToString());
        }

        text.AppendLine("Server:         wird zum Testen gestartet …");
        Process server = ServerStarten(port);
        bool bereit = AufServerWarten(adresse, WartenSekunden);
        text.AppendLine("Ergebnis:       " + (bereit
            ? "gestartet und antwortet"
            : "nicht gestartet — siehe daten\\protokoll.txt"));
        if (server != null)
        {
            Beenden(server);
            text.AppendLine("Testserver:     wieder beendet");
        }
        return Ausgeben(text.ToString());
    }

    private static string ServerZustand(string adresse)
    {
        try
        {
            ServicePointManager.SecurityProtocol =
                SecurityProtocolType.Tls12 | SecurityProtocolType.Tls11 | SecurityProtocolType.Tls;
            var anfrage = (HttpWebRequest)WebRequest.Create(adresse.TrimEnd('/') + "/api/health");
            anfrage.Timeout = 8000;
            using (var antwort = (HttpWebResponse)anfrage.GetResponse())
            {
                return "erreichbar (" + (int)antwort.StatusCode + ")";
            }
        }
        catch (WebException fehler)
        {
            return "nicht erreichbar — " + fehler.Message
                   + " (bei Render dauert der erste Aufruf 30-60 Sekunden)";
        }
        catch (Exception fehler)
        {
            return "nicht prüfbar — " + fehler.Message;
        }
    }

    /// <summary>
    /// Ergebnis auf die Konsole des Aufrufers schreiben, wenn es eine gibt,
    /// sonst als Fenster zeigen. Beides gleichzeitig wäre falsch: Ein
    /// Meldungsfenster wartet auf einen Klick und würde jeden Aufruf aus einem
    /// Skript blockieren.
    /// </summary>
    private static int Ausgeben(string text)
    {
        if (AnKonsoleHaengen())
        {
            Console.WriteLine();
            Console.WriteLine(Titel + " — Selbsttest");
            Console.WriteLine(text);
        }
        else
        {
            Melden(text, MessageBoxIcon.Information);
        }
        return 0;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AttachConsole(int prozessId);

    private static bool AnKonsoleHaengen()
    {
        const int ElternProzess = -1;
        try
        {
            return AttachConsole(ElternProzess);
        }
        catch (Exception)
        {
            return false;
        }
    }

    private static void Melden(string text, MessageBoxIcon symbol)
    {
        MessageBox.Show(text, Titel, MessageBoxButtons.OK, symbol);
    }
}
