from datetime import date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Projekt(Base):
    __tablename__ = "projekte"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    adresse = Column(String, nullable=True, default="")
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    # Optional: Webhook-URL des Projekt-Teams-Kanals. Im Mängelmanagement der
    # Fallback, wenn am Gewerk kein eigener Kanal hinterlegt ist
    # (siehe app.services.teams_notifier).
    teams_webhook_url = Column(String, nullable=False, default="")
    # Wohin die Baufotos dieses Projekts im Netzlaufwerk gehoeren, z. B.
    # "L:\\Bauleitung-Hamburg\\K30159 Kita Nord\\01 FOTOS". Leer = die
    # Standardregel des Buerorechners greift (siehe abholung.ps1). Der Pfad
    # steht hier und nicht auf den einzelnen PCs, damit ihn jeder abholende
    # Rechner kennt, ohne dass jemand fuenf Textdateien pflegt.
    foto_zielpfad = Column(String, nullable=False, default="")
    # Kopfdaten des Besprechungsprotokolls (Deckblatt): Die Projektnummer des
    # Büros ("225100") und der Bauherr ("SBH | Schulbau Hamburg"). Stammdaten
    # des Projekts, keine Angabe je Protokoll — sie ändern sich nicht.
    projekt_nummer = Column(String, nullable=False, default="")
    bauherr = Column(String, nullable=False, default="")
    erstellt_am = Column(DateTime, default=func.now())

    einreichungen = relationship("Einreichung", back_populates="projekt")
    gewerke = relationship("Gewerk", back_populates="projekt")
    maengel = relationship("Mangel", back_populates="projekt")
    plaene = relationship("ProjektPlan", back_populates="projekt")
    fotosaetze = relationship("Fotosatz", back_populates="projekt")
    projektberichte = relationship("Projektbericht", back_populates="projekt")
    besprechungsprotokolle = relationship(
        "Besprechungsprotokoll", back_populates="projekt"
    )
    besprechungs_kapitel = relationship(
        "BesprechungsKapitel", back_populates="projekt"
    )
    besprechungs_themen = relationship("BesprechungsThema", back_populates="projekt")
    projektbeteiligte = relationship("Projektbeteiligter", back_populates="projekt")


class Empfaenger(Base):
    __tablename__ = "empfaenger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String, nullable=False)
    email = Column(String, nullable=False)
    # Optional: Webhook-URL eines eigenen Teams-Kanals für diese Person/Firma —
    # Alternative zum E-Mail-Versand, siehe app.services.teams_notifier.
    teams_webhook_url = Column(String, nullable=False, default="")
    erstellt_am = Column(DateTime, default=func.now())

    einreichungen = relationship("Einreichung", back_populates="empfaenger")


class Einreichung(Base):
    __tablename__ = "einreichungen"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projekt_id = Column(Integer, ForeignKey("projekte.id"), nullable=False)
    empfaenger_id = Column(Integer, ForeignKey("empfaenger.id"), nullable=False)
    datum = Column(Date, nullable=False)
    ergaenzende_angaben = Column(Text, nullable=True, default="")
    status = Column(String, nullable=False, default="eingereicht")
    quelle_dateien = Column(JSON, default=list)
    ergebnis_dokument_pfad = Column(String, nullable=True)
    warnungen = Column(JSON, default=list)
    eingereicht_am = Column(DateTime, default=func.now())
    verarbeitet_am = Column(DateTime, nullable=True)

    projekt = relationship("Projekt", back_populates="einreichungen")
    empfaenger = relationship("Empfaenger", back_populates="einreichungen")
    logs = relationship("VerarbeitungsLog", back_populates="einreichung")


class Firmenname(Base):
    """Firmen, die auf diesem Projekt schon einmal in einem Bericht standen.

    WOZU
    ====
    Die Erkennung eines handschriftlichen Firmennamens gelingt viel sicherer,
    wenn bekannt ist, welche Firmen überhaupt in Frage kommen. Aus "Riedd Bau"
    wird dann "Riedel Bau" statt einer vierten Schreibweise.

    Die Firmen der Stammdaten (``Gewerk``) sind die eine Quelle. Die zweite
    wächst von selbst: Was einmal in einem Bericht stand, ist beim nächsten
    Mal bekannt. Nach der ersten Woche kennt ein Projekt seine Nachunternehmer,
    ohne dass jemand etwas gepflegt hat.

    ``anzahl`` gewichtet: Eine Firma, die zwanzigmal vorkam, ist ein besserer
    Anker als eine, die einmal auftauchte und vielleicht selbst ein Lesefehler
    war.
    """

    __tablename__ = "firmennamen"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projekt_id = Column(Integer, ForeignKey("projekte.id"), nullable=False)
    name = Column(String, nullable=False)
    anzahl = Column(Integer, nullable=False, default=1)
    zuletzt_am = Column(DateTime, default=func.now())


class VerarbeitungsLog(Base):
    __tablename__ = "verarbeitungs_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    einreichung_id = Column(Integer, ForeignKey("einreichungen.id"), nullable=False)
    schritt = Column(String, nullable=False)
    ergebnis = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    dauer_ms = Column(Integer, nullable=True)
    erstellt_am = Column(DateTime, default=func.now())

    einreichung = relationship("Einreichung", back_populates="logs")


# ─────────────────────────────────────────────────────────────────────────────
# Mängelmanagement
#
# Wertelisten (Typ, Status, Rückmeldestatus, Bearbeiter) liegen absichtlich in
# eigenen kleinen Stammdaten-Tabellen statt als Python-Enum im Code: Das Büro
# soll sie in der App pflegen können, ohne dass ein Deploy nötig ist. In
# ``Mangel`` wird deshalb die *Bezeichnung* als String gespeichert (kein FK) —
# so bleibt ein bereits erfasster Mangel lesbar, auch wenn ein Listeneintrag
# später umbenannt oder entfernt wird. Die Startwerte legt
# ``app.database._seed_mangel_stammdaten`` an.
#
# Auch ``prioritaet`` und ``mail_versendemodus`` sind Strings und keine
# SQL-Enums: Postgres-Enums müssten sonst per ALTER TYPE migriert werden, und
# das Projekt nutzt bewusst kein Alembic (siehe database._ensure_columns).
# Die erlaubten Werte prüft app.schemas über Literal-Typen.
# ─────────────────────────────────────────────────────────────────────────────


class Gewerk(Base):
    """Zuständige Firma / Büro einer Vergabeeinheit.

    Beispiel: "Rolfes Bau GmbH | VE300-01 Erweiterter Rohbau".
    """

    __tablename__ = "gewerke"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projekt_id = Column(Integer, ForeignKey("projekte.id"), nullable=False)
    firma_name = Column(String, nullable=False)
    vergabeeinheit_code = Column(String, nullable=False, default="")
    vergabeeinheit_bezeichnung = Column(String, nullable=False, default="")
    # Nullable und damit bewusst optional: Genau daran hängt die
    # Autosend-Prüfung ("Fehler! Firma/Büro hat keine Email-Adresse"),
    # siehe app.services.mangel_versand.
    email = Column(String, nullable=True)
    # Postanschrift fuer den Adressblock der Maengelanzeige (siehe
    # app.services.maengelanzeige_generation). Stammdaten: Einmal je Firma
    # eintragen, statt bei jedem Schreiben abzutippen.
    ansprechpartner = Column(String, nullable=False, default="")
    strasse = Column(String, nullable=False, default="")
    plz = Column(String, nullable=False, default="")
    ort = Column(String, nullable=False, default="")
    # Optional eigener Teams-Kanal der Firma; sonst greift der Kanal des
    # Projekts bzw. der globale Fallback BTB_TEAMS_WEBHOOK_URL.
    teams_webhook_url = Column(String, nullable=False, default="")
    erstellt_am = Column(DateTime, default=func.now())

    projekt = relationship("Projekt", back_populates="gewerke")
    maengel = relationship("Mangel", back_populates="gewerk")


class MangelTyp(Base):
    """Konfigurierbare Typ-Liste.

    Im Formular erscheint "Sortiernummer Bezeichnung", z. B. "2 Hinweis".
    """

    __tablename__ = "mangel_typen"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bezeichnung = Column(String, nullable=False)
    sortierung = Column(Integer, nullable=False, default=0)
    erstellt_am = Column(DateTime, default=func.now())


class MangelStatus(Base):
    """Konfigurierbare Status-Liste mit Farbe für die Badges in der Übersicht."""

    __tablename__ = "mangel_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bezeichnung = Column(String, nullable=False)
    sortierung = Column(Integer, nullable=False, default=0)
    farbe = Column(String, nullable=False, default="#6B7280")
    # Status, in denen ein Mangel als abgeschlossen gilt — daran hängt die
    # Überfälligkeits-Rechnung (ein erledigter Mangel ist nie überfällig).
    ist_abgeschlossen = Column(Boolean, nullable=False, default=False)
    erstellt_am = Column(DateTime, default=func.now())


class MangelRueckmeldungStatus(Base):
    """Konfigurierbare Liste für den Rückmeldestatus der Firma."""

    __tablename__ = "mangel_rueckmeldung_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bezeichnung = Column(String, nullable=False)
    sortierung = Column(Integer, nullable=False, default=0)
    erstellt_am = Column(DateTime, default=func.now())


class Bearbeiter(Base):
    """Bearbeiter des Büros — Auswahl für "Aufgenommen von" und "User".

    Die App hat (noch) keine Anmeldung; diese Tabelle ist die Stammdatenliste
    hinter dem User-Feld und der Anknüpfungspunkt, falls später echte
    Benutzerkonten dazukommen.
    """

    __tablename__ = "bearbeiter"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    # Für die Kopfzeile des Besprechungsprotokolls: "Ze: kbl  T - 22". Das
    # Kürzel steht in jedem Bürodokument, die Durchwahl ist die Nummer hinter
    # der Zentrale. Einmal hier gepflegt, füllt sich jedes Protokoll selbst;
    # überschreiben lässt es sich am Protokoll trotzdem (Vertretungsfall).
    kuerzel = Column(String, nullable=False, default="")
    durchwahl = Column(String, nullable=False, default="")
    erstellt_am = Column(DateTime, default=func.now())


class Mangel(Base):
    __tablename__ = "maengel"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projekt_id = Column(Integer, ForeignKey("projekte.id"), nullable=False)
    # "Ist Kopie von": über "Duplikat NU erstellen" abgeleitete Mängel zeigen
    # auf ihren Ursprung, siehe app.services.mangel_nummern.
    eltern_mangel_id = Column(Integer, ForeignKey("maengel.id"), nullable=True)

    nummer = Column(String, nullable=False)
    typ = Column(String, nullable=False, default="Mangel")
    status = Column(String, nullable=False, default="offen")

    gewerk_id = Column(Integer, ForeignKey("gewerke.id"), nullable=True)
    # Freitext; perspektivisch aus einer Raumliste pro Projekt wählbar.
    raumnummer = Column(String, nullable=True)
    hinweis_ort = Column(String, nullable=False, default="")
    prioritaet = Column(String, nullable=False, default="mittel")

    kurzbezeichnung = Column(String, nullable=False)
    # Ausführliche Beschreibung — für eine rechtssichere Mängelrüge muss der
    # Mangel so beschrieben sein, dass die Firma ihn ohne Rückfrage findet.
    beschreibung = Column(Text, nullable=False, default="")
    farbmarkierung = Column(String, nullable=False, default="")
    # ACHTUNG: "Für Firmen nicht sichtbar". Dieses Feld darf NIE in einen
    # Export gelangen, der an eine Firma geht. Der Export baut deshalb ein
    # eigenes DTO, das das Feld nur bei ausdrücklich internem Export
    # überhaupt enthält — siehe app.services.maengelliste_generation.
    interne_bemerkung = Column(Text, nullable=False, default="")

    # "Erstellt / 1. Frist gesetzt" — vom Nutzer änderbares Aufnahmedatum.
    erstellt_am = Column(Date, nullable=False, default=date.today)
    # Technischer Zeitstempel des Anlegens (nicht änderbar, für Sortierung und
    # Nachvollziehbarkeit) — erstellt_am ist dagegen ein fachliches Datum.
    angelegt_am = Column(DateTime, default=func.now())
    erste_frist_bis = Column(Date, nullable=True)

    aufgenommen_von = Column(String, nullable=False, default="HPP Architekten GmbH")
    zustaendiger_user_id = Column(Integer, ForeignKey("bearbeiter.id"), nullable=True)

    erste_nachfrist_gesetzt_am = Column(Date, nullable=True)
    erste_nachfrist_bis = Column(Date, nullable=True)
    anmerkung_nachfrist = Column(Text, nullable=False, default="")

    beseitigungsanzeige_am = Column(Date, nullable=True)
    freigemeldet_am = Column(Date, nullable=True)
    erledigt_am = Column(Date, nullable=True)
    zurueckweisung_am = Column(Date, nullable=True)

    rueckmeldung_status = Column(String, nullable=False, default="")

    mail_autosend = Column(Boolean, nullable=False, default=False)
    mail_versendemodus = Column(String, nullable=False, default="manuell")
    zuletzt_versendet_am = Column(Date, nullable=True)

    projekt = relationship("Projekt", back_populates="maengel")
    gewerk = relationship("Gewerk", back_populates="maengel")
    zustaendiger_user = relationship("Bearbeiter")
    eltern_mangel = relationship("Mangel", remote_side=[id], backref="duplikate")
    fotos = relationship(
        "MangelFoto",
        back_populates="mangel",
        order_by="MangelFoto.reihenfolge",
    )
    dateien = relationship("MangelDatei", back_populates="mangel")
    markierungen = relationship("MangelPlanMarkierung", back_populates="mangel")


class MangelFoto(Base):
    __tablename__ = "mangel_fotos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mangel_id = Column(Integer, ForeignKey("maengel.id"), nullable=False)
    dateipfad = Column(String, nullable=False)
    aufgenommen_am = Column(DateTime, default=func.now())
    bildunterschrift = Column(String, nullable=False, default="")
    reihenfolge = Column(Integer, nullable=False, default=0)

    mangel = relationship("Mangel", back_populates="fotos")


class MangelDatei(Base):
    """Sonstige Anhänge (PDF, Schriftverkehr, …) — getrennt von den Fotos."""

    __tablename__ = "mangel_dateien"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mangel_id = Column(Integer, ForeignKey("maengel.id"), nullable=False)
    dateipfad = Column(String, nullable=False)
    dateiname = Column(String, nullable=False)
    hochgeladen_am = Column(DateTime, default=func.now())

    mangel = relationship("Mangel", back_populates="dateien")


class ProjektPlan(Base):
    """Hochgeladener Grundriss/Plan (PDF oder Bild) zum Setzen von Markierungen."""

    __tablename__ = "projekt_plaene"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projekt_id = Column(Integer, ForeignKey("projekte.id"), nullable=False)
    dateiname = Column(String, nullable=False)
    dateipfad = Column(String, nullable=False)
    # Seitenzahl mehrseitiger PDF-Pläne, beim Upload ermittelt (Bilder: 1).
    seiten = Column(Integer, nullable=False, default=1)
    hochgeladen_am = Column(DateTime, default=func.now())

    projekt = relationship("Projekt", back_populates="plaene")
    markierungen = relationship("MangelPlanMarkierung", back_populates="plan")


class MangelPlanMarkierung(Base):
    """Stecknadel auf einem Plan.

    Die Position wird in Prozent der Plan-Darstellung gespeichert (nicht in
    Pixeln), damit die Markierung auf jedem Bildschirm und in jedem Zoom an
    derselben Stelle des Plans sitzt.
    """

    __tablename__ = "mangel_plan_markierungen"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mangel_id = Column(Integer, ForeignKey("maengel.id"), nullable=False)
    plan_datei_id = Column(Integer, ForeignKey("projekt_plaene.id"), nullable=False)
    x_prozent = Column(Float, nullable=False)
    y_prozent = Column(Float, nullable=False)
    seite = Column(Integer, nullable=False, default=1)
    erstellt_am = Column(DateTime, default=func.now())

    mangel = relationship("Mangel", back_populates="markierungen")
    plan = relationship("ProjektPlan", back_populates="markierungen")


# ─────────────────────────────────────────────────────────────────────────────
# Baufotos
#
# Holt den bisherigen lokalen Ablauf des Büros in die zentrale App: Fotos einer
# Baustelle werden nach festen Regeln umbenannt, verkleinert und als ZIP
# ausgeliefert — genau die Datei, die bisher das Windows-Programm
# "Baustellenfotos-Tool" per Outlook verschickt hat.
#
# Der Zusammenhang ist der **Fotosatz**: ein Projekt, eine Kategorie, ein Datum.
# Genau daraus setzt sich auch der ZIP-Name zusammen, deshalb ist das eine
# eigene Tabelle und keine Sammlung loser Fotos mit drei wiederholten Feldern.
# ─────────────────────────────────────────────────────────────────────────────


class Fotosatz(Base):
    """Ein Satz Baustellenfotos: Projekt + Kategorie + Datum.

    Beispiel: "2451 Neubau Verwaltungsgebäude Süd", Kategorie "Rohbau",
    19.08.2026 → ZIP-Datei ``260819_2451_Neubau_Verwaltungsgebäude_Süd_Rohbau.zip``.
    """

    __tablename__ = "fotosaetze"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projekt_id = Column(Integer, ForeignKey("projekte.id"), nullable=False)
    # Freitext und keine Stammdatenliste: Die Kategorien wachsen mit dem Bau
    # ("Rohbau", "Fenster EG", "Abnahme Dach"). Die Oberfläche schlägt die
    # bisher benutzten vor, blockiert aber nichts.
    kategorie = Column(String, nullable=False)
    # Aufnahmedatum, nicht Uploadzeitpunkt — es steht im Dateinamen und die
    # Fotos werden häufig erst abends im Büro hochgeladen.
    datum = Column(Date, nullable=False, default=date.today)
    notiz = Column(Text, nullable=False, default="")
    zuletzt_gemeldet_am = Column(Date, nullable=True)
    # E-Mail-Versand (app.services.fotoversand): wann, an wen und auf welchem
    # Weg. ``mail_weg`` unterscheidet "smtp" (die App hat wirklich verschickt)
    # von "entwurf" (Outlook hat den fertigen Entwurf bekommen) — das ist ein
    # echter Unterschied, den die Karte auch anzeigt.
    mail_versendet_am = Column(Date, nullable=True)
    mail_empfaenger = Column(Text, nullable=False, default="")
    mail_weg = Column(String, nullable=False, default="")
    erstellt_am = Column(DateTime, default=func.now())

    # ── Abholung durch einen Bürorechner ──
    #
    # Der Weg auf das Netzlaufwerk L: kann nur von einem Rechner im Büronetz
    # gegangen werden; ein Server im Internet kommt dort nicht hinein. Deshalb
    # holt ein Skript in der Aufgabenplanung die fertigen Sätze ab. Diese drei
    # Felder verhindern, dass zwei Rechner denselben Satz abholen und er
    # doppelt im Projektordner landet.
    abgeholt_am = Column(DateTime, nullable=True)
    #: Rechnername, der abgeholt hat — steht auch im Protokoll.
    abgeholt_von = Column(String, nullable=False, default="")
    #: Wohin der Satz gelegt wurde. Für Rückfragen im Büro Gold wert.
    abgeholt_ziel = Column(Text, nullable=False, default="")

    projekt = relationship("Projekt", back_populates="fotosaetze")
    fotos = relationship(
        "Baufoto",
        back_populates="fotosatz",
        order_by="Baufoto.reihenfolge",
    )


class Fotoblob(Base):
    """Die Bilddaten eines Baufotos, wenn sie in der Datenbank liegen.

    Eigene Tabelle und nicht eine Spalte an ``Baufoto``: Die Fotoliste wird
    bei jedem Aufbau der Galerie abgefragt, und ein ``SELECT *`` würde sonst
    jedes Mal mehrere Megabyte mitschleppen. So bleibt ``baufotos`` schmal und
    die Bilddaten werden nur geholt, wenn wirklich jemand ein Bild ansieht.

    Der Schlüssel entspricht dem Pfad, den die Dateiablage benutzt hätte
    ("baufotos/12/260819_Rohbau_1.jpg") — dadurch sehen die Verweise in
    ``Baufoto.dateipfad`` in beiden Fällen gleich aus.

    Wann hier etwas liegt und wann es wieder verschwindet, steht in
    app.services.fotospeicher.
    """

    __tablename__ = "fotoblobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    schluessel = Column(String, nullable=False, unique=True, index=True)
    # LargeBinary wird auf Postgres zu BYTEA, auf SQLite zu BLOB.
    daten = Column(LargeBinary, nullable=False)
    groesse_bytes = Column(Integer, nullable=False, default=0)
    erstellt_am = Column(DateTime, default=func.now())


class Baufoto(Base):
    """Ein Foto innerhalb eines Fotosatzes.

    ``dateiname`` ist der **umbenannte** Name nach der Büroregel
    (``{JJMMTT}_{Kategorie}_{Nummer}.jpg``) und damit der Name, der später im
    Projektordner landet. ``original_dateiname`` bleibt erhalten, damit man ein
    Foto notfalls dem Handy-Original zuordnen kann.
    """

    __tablename__ = "baufotos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fotosatz_id = Column(Integer, ForeignKey("fotosaetze.id"), nullable=False)
    dateipfad = Column(String, nullable=False)
    dateiname = Column(String, nullable=False)
    original_dateiname = Column(String, nullable=False, default="")
    # Bestimmt die laufende Nummer im Dateinamen und die Reihenfolge im ZIP.
    reihenfolge = Column(Integer, nullable=False, default=0)
    groesse_bytes = Column(Integer, nullable=False, default=0)
    hochgeladen_am = Column(DateTime, default=func.now())

    fotosatz = relationship("Fotosatz", back_populates="fotos")


# ─────────────────────────────────────────────────────────────────────────────
# Projektberichte (Monatsberichte)
#
# Ein Projekt hat viele Berichte, fortlaufend nummeriert. Die Kapitelinhalte
# liegen als JSON am Bericht und nicht in einer eigenen Tabelle: Die Gliederung
# steht in app.services.projektbericht_gliederung und darf wachsen, ohne dass
# dafür jedes Mal eine Migration nötig wäre. Ein Kapitel ist ein Text — kein
# Datensatz, den man einzeln abfragen müsste.
# ─────────────────────────────────────────────────────────────────────────────


class Projektbericht(Base):
    __tablename__ = "projektberichte"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projekt_id = Column(Integer, ForeignKey("projekte.id"), nullable=False)
    nummer = Column(Integer, nullable=False)
    berichtsdatum = Column(Date, nullable=False, default=date.today)
    zeitraum_von = Column(Date, nullable=True)
    zeitraum_bis = Column(Date, nullable=True)
    ersteller = Column(String, nullable=False, default="")
    # Kopfzeile links; standardmäßig der Projektname, aber überschreibbar —
    # im Bericht steht "BOB Boulevard Berlin", im System vielleicht
    # "2451 BOB Boulevard Berlin".
    projektname = Column(String, nullable=False, default="")
    # Kürzel für Fußzeile und Dateiname ("BoB").
    projektkuerzel = Column(String, nullable=False, default="")
    buero = Column(String, nullable=False, default="HPP")

    # Kapitelschlüssel -> Text, plus die wiederholbaren Listen.
    kapitel = Column(JSON, default=dict)
    baubegehungen = Column(JSON, default=list)
    besprechungen = Column(JSON, default=list)
    soll_ist = Column(JSON, default=list)

    # Zuletzt erzeugte Dateien — die Historie soll abrufbar bleiben, nicht nur
    # der Download im Moment des Erzeugens.
    dokument_pfad = Column(String, nullable=True)
    pdf_pfad = Column(String, nullable=True)
    erzeugt_am = Column(DateTime, nullable=True)

    erstellt_am = Column(DateTime, default=func.now())
    geaendert_am = Column(DateTime, default=func.now(), onupdate=func.now())

    projekt = relationship("Projekt", back_populates="projektberichte")
    fotos = relationship(
        "ProjektberichtFoto",
        back_populates="bericht",
        order_by="ProjektberichtFoto.reihenfolge",
    )


class ProjektberichtFoto(Base):
    __tablename__ = "projektbericht_fotos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bericht_id = Column(Integer, ForeignKey("projektberichte.id"), nullable=False)
    dateipfad = Column(String, nullable=False)
    bildunterschrift = Column(String, nullable=False, default="")
    reihenfolge = Column(Integer, nullable=False, default=0)
    hochgeladen_am = Column(DateTime, default=func.now())

    bericht = relationship("Projektbericht", back_populates="fotos")


# ─────────────────────────────────────────────────────────────────────────────
# Baubesprechungsprotokolle
#
# Löst die Excel-Vorlage ``{JJMMTT}_BB_{Nr}.xlsm`` ab. Deren Aufbau ist der
# Grund für den Zuschnitt dieser Tabellen — vor allem für den, der auf den
# ersten Blick zu kompliziert wirkt:
#
# Das Blatt "LOP" (Liste offener Punkte) der Vorlage ist **keine** Liste zu
# einer Besprechung. Es ist die laufende Themenliste des Projekts, die von
# Sitzung zu Sitzung fortgeschrieben wird; im Beispielprotokoll Nr. 16 stehen
# über 100 Zeilen, gedruckt werden nur die, die an diesem Tag eine Rolle
# spielten. Die Nummer ``Kapitel.Inhalt.BB`` ist deshalb projektweit und
# dauerhaft: "02. 08. 16" heißt "Kapitel 2, Thema 8, zuletzt behandelt in
# Baubesprechung 16" — und "02. 08. 10" ist derselbe Sachverhalt sechs
# Sitzungen früher.
#
# Daraus folgt die Aufteilung:
#
#   BesprechungsThema        der Sachverhalt selbst, lebt am Projekt
#   BesprechungsThemaUpdate  sein Stand in genau einer Sitzung (das ist die
#                            Zeile, die gedruckt wird — die BB-Nummer steckt
#                            hier, nicht am Thema)
#   Besprechungsprotokoll    die Sitzung
#
# Ein Protokoll ist damit: der Schnappschuss der Themenliste zu diesem Datum.
# Genau wie in der Excel-Vorlage, nur ohne Kopieren von Hand.
# ─────────────────────────────────────────────────────────────────────────────


#: Statuswerte der Spalte "Status" (Legende auf Seite 3 des Protokolls).
#: Reihenfolge wie im Blatt "nicht löschen" der Excel-Vorlage.
BESPRECHUNG_STATUS = ("k", "b", "e", "n", "i")

#: Status, in dem ein Thema als abgeschlossen gilt und beim nächsten Protokoll
#: nicht mehr von selbst als offener Punkt vorgeschlagen wird.
BESPRECHUNG_STATUS_ERLEDIGT = ("e",)


class BesprechungsKapitel(Base):
    """Ein Kapitel der Themenliste — die graue Balkenzeile im Protokoll.

    Beispiele aus der Vorlage: "01. Allgemein/ Projektorganisation",
    "2. VE01 Erweiterte Rohbauarbeiten - Rolfes Bau (VE300.01)".

    Die Kapitel ab dem zweiten sind die Vergabeeinheiten des Projekts, stehen
    aber trotzdem in einer eigenen Tabelle und nicht als Verweis auf
    ``Gewerk``: Ein Kapitel überlebt das Gewerk (die Firma wechselt, die
    Themen bleiben), es gibt Kapitel ohne Gewerk ("Allgemein", "Termine"), und
    die Reihenfolge im Protokoll ist eine eigene Entscheidung. ``gewerk_id``
    merkt sich nur, woher der Vorschlag kam.
    """

    __tablename__ = "besprechungs_kapitel"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projekt_id = Column(Integer, ForeignKey("projekte.id"), nullable=False)
    #: Wie gedruckt: "01." oder "2." — die Vorlage ist da uneinheitlich, und
    #: das soll sie bleiben dürfen. Deshalb String und keine Zahl.
    nummer = Column(String, nullable=False, default="")
    titel = Column(String, nullable=False, default="")
    sortierung = Column(Integer, nullable=False, default=0)
    gewerk_id = Column(Integer, ForeignKey("gewerke.id"), nullable=True)
    erstellt_am = Column(DateTime, default=func.now())

    projekt = relationship("Projekt", back_populates="besprechungs_kapitel")
    gewerk = relationship("Gewerk")
    themen = relationship("BesprechungsThema", back_populates="kapitel")


class BesprechungsThema(Base):
    """Ein Sachverhalt der laufenden Themenliste des Projekts.

    Lebt am Projekt, nicht am Protokoll — analog zu ``Mangel``. Der Text hier
    ist der *aktuelle* Stand; was in einer bestimmten Sitzung dazu gesagt
    wurde, steht im zugehörigen ``BesprechungsThemaUpdate``.
    """

    __tablename__ = "besprechungs_themen"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projekt_id = Column(Integer, ForeignKey("projekte.id"), nullable=False)
    kapitel_id = Column(Integer, ForeignKey("besprechungs_kapitel.id"), nullable=False)
    #: Laufende Nummer innerhalb des Kapitels — die mittlere Zahl der
    #: Protokollnummer ("02. 08. 16" -> "08"). String, weil die Vorlage "08"
    #: schreibt und nicht 8.
    inhalt_nr = Column(String, nullable=False, default="")

    thema = Column(Text, nullable=False, default="")
    zustaendig = Column(String, nullable=False, default="")
    bearb_bis = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, default="n")

    erstmals_protokoll_id = Column(
        Integer, ForeignKey("besprechungsprotokolle.id"), nullable=True
    )
    zuletzt_protokoll_id = Column(
        Integer, ForeignKey("besprechungsprotokolle.id"), nullable=True
    )
    erledigt_am = Column(Date, nullable=True)
    erstellt_am = Column(DateTime, default=func.now())
    geaendert_am = Column(DateTime, default=func.now(), onupdate=func.now())

    projekt = relationship("Projekt", back_populates="besprechungs_themen")
    kapitel = relationship("BesprechungsKapitel", back_populates="themen")
    updates = relationship(
        "BesprechungsThemaUpdate",
        back_populates="thema",
        cascade="all, delete-orphan",
    )


class Besprechungsprotokoll(Base):
    """Eine Baubesprechung: Kopfdaten, Teilnehmer, Themenstände, Dokument."""

    __tablename__ = "besprechungsprotokolle"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projekt_id = Column(Integer, ForeignKey("projekte.id"), nullable=False)
    #: "Protokoll-Nr." — fortlaufend je Projekt, zugleich die BB-Nummer, die
    #: als dritte Zahl in jeder Themenzeile steht.
    nummer = Column(Integer, nullable=False)
    leistung = Column(String, nullable=False, default="Baubesprechung")
    besprechungsort = Column(String, nullable=False, default="")
    besprechungsdatum = Column(Date, nullable=False, default=date.today)

    ersteller_id = Column(Integer, ForeignKey("bearbeiter.id"), nullable=True)
    #: Kopfzeile "25.08.2026  Ze: kbl  T - 22  katharina.blanck@hpp.com".
    #: Beim Anlegen aus dem Bearbeiter vorbelegt, danach frei änderbar — ein
    #: Protokoll kann in Vertretung geschrieben werden.
    ersteller_name = Column(String, nullable=False, default="")
    ersteller_kuerzel = Column(String, nullable=False, default="")
    ersteller_durchwahl = Column(String, nullable=False, default="")
    ersteller_email = Column(String, nullable=False, default="")

    #: Rohdaten aus tl;dv. Bleiben erhalten, damit die KI-Analyse
    #: nachvollziehbar und wiederholbar ist.
    tldv_transkript_roh = Column(Text, nullable=False, default="")
    tldv_notizen_roh = Column(Text, nullable=False, default="")
    analyse_am = Column(DateTime, nullable=True)
    analyse_hinweise = Column(JSON, default=list)

    #: entwurf -> geprueft -> freigegeben. Erst "freigegeben" schreibt die
    #: Themenliste fort und erzeugt das Dokument.
    status = Column(String, nullable=False, default="entwurf")
    geprueft_von_id = Column(Integer, ForeignKey("bearbeiter.id"), nullable=True)
    geprueft_am = Column(DateTime, nullable=True)
    freigegeben_am = Column(DateTime, nullable=True)

    dokument_pfad = Column(String, nullable=True)
    pdf_pfad = Column(String, nullable=True)
    erzeugt_am = Column(DateTime, nullable=True)

    erstellt_am = Column(DateTime, default=func.now())
    geaendert_am = Column(DateTime, default=func.now(), onupdate=func.now())

    projekt = relationship("Projekt", back_populates="besprechungsprotokolle")
    ersteller = relationship("Bearbeiter", foreign_keys=[ersteller_id])
    geprueft_von = relationship("Bearbeiter", foreign_keys=[geprueft_von_id])
    teilnehmer = relationship(
        "BesprechungsTeilnehmer",
        back_populates="protokoll",
        cascade="all, delete-orphan",
        order_by="BesprechungsTeilnehmer.reihenfolge",
    )
    themen_updates = relationship(
        "BesprechungsThemaUpdate",
        back_populates="protokoll",
        cascade="all, delete-orphan",
        foreign_keys="BesprechungsThemaUpdate.protokoll_id",
    )
    anlagen = relationship(
        "BesprechungsAnlage",
        back_populates="protokoll",
        cascade="all, delete-orphan",
        order_by="BesprechungsAnlage.reihenfolge",
    )


class BesprechungsThemaUpdate(Base):
    """Der Stand eines Themas in genau einer Besprechung — eine Druckzeile.

    Der Text steht hier noch einmal und nicht nur am Thema: Ein Protokoll ist
    ein Dokument mit Datum. Was am 25.08. beschlossen wurde, muss auch dann
    noch nachlesbar sein, wenn das Thema drei Sitzungen später umformuliert
    wurde.
    """

    __tablename__ = "besprechungs_thema_updates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    #: In welchem Protokoll diese Zeile **gedruckt** wird.
    protokoll_id = Column(
        Integer, ForeignKey("besprechungsprotokolle.id"), nullable=False
    )
    #: Aus welcher Sitzung die Zeile **stammt** — daraus wird die BB-Nummer
    #: gedruckt, die dritte Zahl von "02. 08. 16".
    #:
    #: Das ist nicht dasselbe wie ``protokoll_id``, und der Unterschied ist der
    #: Kern der ganzen Fortschreibung: Im Beispielprotokoll Nr. 16 stehen die
    #: Zeilen "02. 08. 10", "02. 08. 15" und "02. 08. 16" untereinander —
    #: dreimal derselbe Sachverhalt, festgehalten in den Sitzungen 10, 15 und
    #: 16. Ein offener Punkt, der heute nicht besprochen wurde, wird deshalb
    #: unverändert mitgenommen und behält seine alte BB-Nummer; eine neue
    #: bekommt er erst, wenn zu ihm wirklich wieder etwas gesagt wurde.
    ursprung_protokoll_id = Column(
        Integer, ForeignKey("besprechungsprotokolle.id"), nullable=True
    )
    thema_id = Column(Integer, ForeignKey("besprechungs_themen.id"), nullable=False)

    thema_text = Column(Text, nullable=False, default="")
    zustaendig = Column(String, nullable=False, default="")
    #: Freitext: mal "25.08.26", mal "KW 35'26". Beides steht so im Original,
    #: ein Datumsfeld könnte nur die Hälfte davon.
    bearb_bis = Column(String, nullable=False, default="")
    status = Column(String, nullable=False, default="n")
    #: Hebt die Zelle "Bearb. bis" hell hervor. In der Excel-Vorlage macht das
    #: die Bearbeiterin von Hand bei Fristen, die sie im Blick behalten will —
    #: es gibt dafür keine Regel, deshalb hier auch keine.
    hervorheben = Column(Boolean, nullable=False, default=False)

    sortierung = Column(Integer, nullable=False, default=0)
    #: Woher die Zeile kommt: "ki" (Vorschlag der Analyse), "mensch" (von Hand
    #: angelegt), "fortschreibung" (offener Punkt aus einer früheren Sitzung).
    herkunft = Column(String, nullable=False, default="mensch")
    #: Vom Menschen angesehen? Solange das falsch ist, zeigt die Prüfansicht
    #: die Zeile als "bitte prüfen" — und die Freigabe warnt.
    bestaetigt = Column(Boolean, nullable=False, default=False)
    erstellt_am = Column(DateTime, default=func.now())

    protokoll = relationship(
        "Besprechungsprotokoll",
        back_populates="themen_updates",
        foreign_keys=[protokoll_id],
    )
    ursprung_protokoll = relationship(
        "Besprechungsprotokoll", foreign_keys=[ursprung_protokoll_id]
    )
    thema = relationship("BesprechungsThema", back_populates="updates")

    @property
    def bb_nr(self) -> str:
        """Die dritte Zahl der Protokollnummer, zweistellig wie im Original."""
        quelle = self.ursprung_protokoll or self.protokoll
        return f"{quelle.nummer:02d}" if quelle else ""


class BesprechungsTeilnehmer(Base):
    """Eine Zeile der Teilnehmerliste (Seite 4 des Protokolls)."""

    __tablename__ = "besprechungs_teilnehmer"

    id = Column(Integer, primary_key=True, autoincrement=True)
    protokoll_id = Column(
        Integer, ForeignKey("besprechungsprotokolle.id"), nullable=False
    )
    name = Column(String, nullable=False, default="")
    firma_kuerzel = Column(String, nullable=False, default="")
    telefon = Column(String, nullable=False, default="")
    anwesend = Column(Boolean, nullable=False, default=True)
    reihenfolge = Column(Integer, nullable=False, default=0)
    #: Kam der Name aus dem tl;dv-Transkript? Dann ist Firma/Telefon aus den
    #: Stammdaten geraten und gehört angesehen, bevor das Protokoll rausgeht.
    aus_transkript = Column(Boolean, nullable=False, default=False)
    erstellt_am = Column(DateTime, default=func.now())

    protokoll = relationship("Besprechungsprotokoll", back_populates="teilnehmer")


class BesprechungsAnlage(Base):
    """Eine hochgeladene Datei, die hinten an das Protokoll gehängt wird.

    Der Normalfall ist die unterschriebene Teilnehmerliste: Sie wird vor dem
    Termin gedruckt, vor Ort gegengezeichnet, eingescannt und hier hochgeladen
    — genau so entstand auch die vierte Seite des Beispielprotokolls. PDF und
    Bilder werden beim Erzeugen als ganzseitige Abbildungen angefügt.
    """

    __tablename__ = "besprechungs_anlagen"

    id = Column(Integer, primary_key=True, autoincrement=True)
    protokoll_id = Column(
        Integer, ForeignKey("besprechungsprotokolle.id"), nullable=False
    )
    dateipfad = Column(String, nullable=False)
    dateiname = Column(String, nullable=False, default="")
    #: Zeile über der Abbildung, z. B. "Teilnehmerliste, unterschrieben".
    #: Leer = keine Überschrift.
    bezeichnung = Column(String, nullable=False, default="")
    reihenfolge = Column(Integer, nullable=False, default=0)
    hochgeladen_am = Column(DateTime, default=func.now())

    protokoll = relationship("Besprechungsprotokoll", back_populates="anlagen")


class Projektbeteiligter(Base):
    """Stammdaten für "Abkürzungen Projektbeteiligte" (Seite 3).

    Bewusst nicht ``Gewerk``: Dort stehen die Nachunternehmer mit
    Vergabeeinheit und Postanschrift. Hier stehen alle, die im Protokoll als
    Kürzel auftauchen — Bauherr, Fachplaner, SiGeKo, die eigene Bauleitung.
    Die meisten davon sind kein Gewerk, und ein Gewerk um vier Rollenfelder zu
    erweitern, würde beide Listen unschärfer machen.
    """

    __tablename__ = "projektbeteiligte"

    id = Column(Integer, primary_key=True, autoincrement=True)
    projekt_id = Column(Integer, ForeignKey("projekte.id"), nullable=False)
    kuerzel = Column(String, nullable=False, default="")
    name = Column(String, nullable=False, default="")
    rolle = Column(String, nullable=False, default="")
    #: Für die Teilnehmerliste: Ansprechpartner und Telefon der Firma. tl;dv
    #: liefert nur Namen, alles Weitere kommt von hier.
    ansprechpartner = Column(String, nullable=False, default="")
    telefon = Column(String, nullable=False, default="")
    sortierung = Column(Integer, nullable=False, default=0)
    erstellt_am = Column(DateTime, default=func.now())

    projekt = relationship("Projekt", back_populates="projektbeteiligte")
