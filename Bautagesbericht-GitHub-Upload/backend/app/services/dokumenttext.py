"""Gelesenen Text so aufbereiten, dass Word ihn annimmt.

WARUM ES DIESES MODUL GIBT
==========================
Word-Dokumente sind XML, und XML 1.0 verbietet die meisten Steuerzeichen —
auch solche, die in einem Text harmlos aussehen. Ein Seitenvorschub (``\\x0c``)
aus einem kopierten PDF oder ein vertikaler Tabulator (``\\x0b``) aus einer
Texterkennung reicht, und das Erzeugen des Dokuments bricht mit

    XMLSyntaxError: PCDATA invalid Char value 12

ab. Für den Anwender sieht das so aus: Der Bautagesbericht steht auf
"fehlgeschlagen", ohne dass irgendwo stünde, woran es lag — und die
hochgeladenen Blätter waren in Ordnung.

Betroffen sind alle fünf Erzeuger (Bautagesbericht, Mängelliste,
Mängelanzeige, Projektbericht, Besprechungsprotokoll), weil sie dieselben drei
Textquellen haben: Texterkennung, PDF-Textebene und Eingaben aus der
Oberfläche. Ein einzelnes Zeichen darf keinen davon aufhalten.

WAS NICHT WEGGEWORFEN WIRD
==========================
Nichts Lesbares. Umlaute, Bindestriche, Anführungszeichen, Tabulatoren und
auch das weiche Trennzeichen bleiben unangetastet — letzteres steht in der
HPP-Vorlage als Zierstrich neben der Seitenzahl. Ersetzt werden ausschließlich
Zeichen, die Word nicht darstellen könnte, und zwar dort, wo sie eine
Bedeutung haben, durch die naheliegende: Ein Seitenvorschub trennte Zeilen,
also wird er ein Zeilenumbruch.
"""

from __future__ import annotations

import re

#: Steuerzeichen, die in XML 1.0 nicht vorkommen dürfen. Erlaubt bleiben nur
#: Tabulator und Zeilenvorschub; ``\\uFFFE`` und ``\\uFFFF`` sind ebenfalls
#: verboten. Die C1-Zeichen (``\\x80``–``\\x9F``) wären in XML 1.0 formal
#: zulässig, kommen aber praktisch nur aus falsch dekodierten Umlauten und
#: stehen im Dokument als leere Kästchen — deshalb fliegen sie mit.
_VERBOTEN = re.compile("[\x00-\x08\x0e-\x1f\x7f-\x9f￾￿]")

#: Zeichen, die einen Umbruch meinten und deshalb einer werden: vertikaler
#: Tabulator (in Words eigenem Textmodell ist das der Zeilenumbruch),
#: Seitenvorschub sowie die Unicode-Zeilen- und -Absatztrenner.
_ALS_UMBRUCH = re.compile("[\x0b\x0c  ]")

#: Unsichtbare Steuerzeichen der Textverarbeitung. Sie überleben das Kopieren
#: aus PDF und Web und hinterlassen im Word-Text Leerstellen und
#: Schreibrichtungswechsel an Stellen, an denen keine hingehören.
_UNSICHTBAR = re.compile("[​-‏‪-‮⁠﻿]")


def xml_sicher(text: str) -> str:
    """Der Text, wie er in ein Word-Dokument darf.

    Reihenfolge mit Bedacht: Zuerst werden die Zeilenenden vereinheitlicht,
    dann die Zeichen ersetzt, die einen Umbruch meinten, und erst zuletzt
    weggeworfen, was keine Bedeutung mehr hat. Umgekehrt wäre ein
    Seitenvorschub schon verschwunden, bevor sein Umbruch entstehen konnte.
    """
    if not text:
        return ""
    roh = str(text)
    roh = roh.replace("\r\n", "\n").replace("\r", "\n")
    roh = _ALS_UMBRUCH.sub("\n", roh)
    roh = _UNSICHTBAR.sub("", roh)
    return _VERBOTEN.sub("", roh)


def einzeilig(text: str) -> str:
    """Wie ``xml_sicher``, aber garantiert ohne Umbruch.

    Für Werte, die in eine Tabellenzelle mit knapper Höhe gehen — eine
    Kommissionsnummer oder ein Firmenname darf dort nicht plötzlich zwei
    Zeilen hoch werden, bloß weil in der Texterkennung ein Umbruch steckte.
    """
    sauber = xml_sicher(text).replace("\n", " ").replace("\t", " ")
    return re.sub(r" {2,}", " ", sauber).strip()


def zeilen(text: str) -> list[str]:
    """Der Text in seine Zeilen, ohne die leeren am Rand.

    Gebraucht dort, wo ein mehrzeiliger Wert als echter Zeilenumbruch ins
    Dokument soll (``<w:br/>``) und nicht als Leerzeichen — siehe
    ``docx_generation._run``.
    """
    sauber = xml_sicher(text)
    if not sauber:
        return []
    teile = sauber.split("\n")
    while teile and not teile[0].strip():
        teile.pop(0)
    while teile and not teile[-1].strip():
        teile.pop()
    return teile
