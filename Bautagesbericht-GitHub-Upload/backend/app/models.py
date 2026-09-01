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
    erstellt_am = Column(DateTime, default=func.now())

    einreichungen = relationship("Einreichung", back_populates="projekt")
    gewerke = relationship("Gewerk", back_populates="projekt")
    maengel = relationship("Mangel", back_populates="projekt")
    plaene = relationship("ProjektPlan", back_populates="projekt")
    fotosaetze = relationship("Fotosatz", back_populates="projekt")
    projektberichte = relationship("Projektbericht", back_populates="projekt")


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
