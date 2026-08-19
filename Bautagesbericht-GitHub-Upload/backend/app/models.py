from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class Projekt(Base):
    __tablename__ = "projekte"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    adresse = Column(String, nullable=True, default="")
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    erstellt_am = Column(DateTime, default=func.now())

    einreichungen = relationship("Einreichung", back_populates="projekt")


class Empfaenger(Base):
    __tablename__ = "empfaenger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    label = Column(String, nullable=False)
    email = Column(String, nullable=False)
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
