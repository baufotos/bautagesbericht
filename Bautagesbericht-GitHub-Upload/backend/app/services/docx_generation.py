"""Erzeugt das HPP-Bautagebuch aus der Blanko-Word-Vorlage.

Die Vorlage (``Bautagesbericht_HPP_leer.docx``) enthält nur das Gerüst:
Logo, Projekt-Label und eine Tabelle mit fünf Zeilen
(Datum, Haupteintrag + Wetterlabels, Firmen, Firmen, Unterschrift).
Wetterwerte, Stundentabelle, Temperaturdiagramm und weitere Firmenblöcke
existieren dort noch nicht — sie werden hier eingefügt.

Aufbau und Formatierung sind an den ausgefüllten HPP-Referenzberichten
(``reference/HPP_Vorlagen``) ausgemessen:

  Projektname   Arial bold 11.5 pt, rechts neben dem Label "Projekt"
  Datum         "Fr 07.08.2026" — Wochentagskürzel + Datum
  Wetterwerte   Station linksbündig, Zahlenwerte rechtsbündig unter ihren Labels
  Stundenwerte  Uhrzeit / Temperaturdiagramm / Temp. (°C) / Wind (m/s) /
                Wind (Grad) / Bewölkung, jeweils zwölf Zweistundenwerte
  Firmenblock   zweispaltig: Labels links, Werte rechts; Firmenname fett,
                leere Felder werden weggelassen
  Fußzeile      "Bautagebuch - {Projekt} - {TT.MM.JJJJ}"
"""

from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Twips

from app.config import settings
from app.schemas import BautagesberichtJSON

FONT = "Arial"
SYMBOL_FONT = "Segoe UI Symbol"

# Schriftgrößen in Halbpunkten, wie in Vorlage und Referenzberichten gemessen.
SZ_NORMAL = 14      # 7 pt — Standardtext der Tabelle
SZ_SMALL = 11       # 5.5 pt — graue Hilfslabels
SZ_PROJEKT = 23     # 11.5 pt — Projektname in der Kopfzeile
SZ_SYMBOL = 18      # 9 pt — Wettersymbole der Bewölkungszeile
GRAY = "999999"

# Spaltenbreiten der Vorlagentabelle in Twips.
COL_WIDTHS = [1091, 2148, 909, 850, 549, 828, 3073]
LABEL_COL = COL_WIDTHS[0]
VALUE_SPAN = sum(COL_WIDTHS[1:])     # 8357 — Breite der sechs Wertspalten
TAB_VALUE_COL = 1050                 # Tabstopp für den Projektnamen

WEEKDAY_ABBR = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# Stundentabelle: Beschriftungsspalte + zwölf Wertspalten.
HOURLY_LABEL_W = 1157
HOURLY_VALUE_W = (VALUE_SPAN - HOURLY_LABEL_W) // 12

# Temperaturdiagramm.
BAR_COLOR = "FFA500"
BAR_MAX_PT = 47
BAR_WIDTH_TWIPS = 150
BAR_INDENT = (HOURLY_VALUE_W - BAR_WIDTH_TWIPS) // 2

# Firmenblock: Label- und Wertspalte.
FIRMA_LABEL_W = 1440
FIRMA_VALUE_W = VALUE_SPAN - FIRMA_LABEL_W

# Bright-Sky-Icons auf darstellbare Symbole abbilden.
WETTER_SYMBOLE = {
    "clear-day": "☀",
    "clear-night": "☾",
    "partly-cloudy-day": "⛅",
    "partly-cloudy-night": "☁",
    "cloudy": "☁",
    "fog": "░",
    "rain": "☔",
    "sleet": "☔",
    "snow": "❄",
    "hail": "❄",
    "thunderstorm": "⚡",
    "wind": "≋",
}


def _fmt_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _fmt_date_weekday(d: date) -> str:
    return f"{WEEKDAY_ABBR[d.weekday()]} {_fmt_date(d)}"


def _num(value, unit: str, decimals: int = 1) -> str:
    """Zahl mit Einheit; leerer String wenn kein Wert vorliegt."""
    if value is None:
        return ""
    if decimals == 0:
        return f"{round(value):.0f} {unit}".strip()
    return f"{value:.{decimals}f} {unit}".strip()


def _run(text: str, *, bold: bool = False, size: int = SZ_NORMAL,
         color: str | None = None, font: str = FONT) -> str:
    rpr = f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>'
    if bold:
        rpr += "<w:b/>"
    if color:
        rpr += f'<w:color w:val="{color}"/>'
    rpr += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    return (
        f"<w:r><w:rPr>{rpr}</w:rPr>"
        f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
    )


def _para(runs: str, *, align: str | None = None, after: int = 0,
          shading: str | None = None, indent: int = 0,
          exact_height: int | None = None) -> str:
    ppr = ""
    if shading:
        ppr += f'<w:shd w:val="clear" w:color="auto" w:fill="{shading}"/>'
    if exact_height:
        ppr += f'<w:spacing w:after="0" w:line="{exact_height}" w:lineRule="exact"/>'
    else:
        ppr += f'<w:spacing w:after="{after}" w:line="240" w:lineRule="auto"/>'
    if indent:
        ppr += f'<w:ind w:left="{indent}" w:right="{indent}"/>'
    if align:
        ppr += f'<w:jc w:val="{align}"/>'
    return f"<w:p><w:pPr>{ppr}</w:pPr>{runs}</w:p>"


def _borders(top: bool, bottom: bool) -> str:
    def side(name: str, on: bool) -> str:
        if on:
            return f'<w:{name} w:val="single" w:sz="5" w:space="0" w:color="000000"/>'
        return f'<w:{name} w:val="nil"/>'

    return (
        "<w:tcBorders>"
        + side("top", top)
        + side("left", False)
        + side("bottom", bottom)
        + side("right", False)
        + "</w:tcBorders>"
    )


def _cell(width: int, body: str, *, gridspan: int | None = None,
          top: bool = False, bottom: bool = False,
          valign: str | None = None) -> str:
    tcpr = f'<w:tcW w:w="{width}" w:type="dxa"/>'
    if gridspan:
        tcpr += f'<w:gridSpan w:val="{gridspan}"/>'
    tcpr += _borders(top, bottom)
    if valign:
        tcpr += f'<w:vAlign w:val="{valign}"/>'
    return f"<w:tc><w:tcPr>{tcpr}</w:tcPr>{body or _para('')}</w:tc>"


def _row(cells: str, *, height: int | None = None):
    trpr = ""
    if height:
        trpr = f'<w:trPr><w:trHeight w:val="{height}" w:hRule="exact"/></w:trPr>'
    return parse_xml(f"<w:tr {nsdecls('w')}>{trpr}{cells}</w:tr>")


def _nested_table_open(width: int, grid: str) -> str:
    return (
        f"<w:tbl><w:tblPr>"
        f'<w:tblW w:w="{width}" w:type="dxa"/>'
        f"<w:tblBorders><w:top w:val=\"nil\"/><w:left w:val=\"nil\"/>"
        f"<w:bottom w:val=\"nil\"/><w:right w:val=\"nil\"/>"
        f"<w:insideH w:val=\"nil\"/><w:insideV w:val=\"nil\"/></w:tblBorders>"
        f'<w:tblLayout w:type="fixed"/>'
        f'<w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="0" w:type="dxa"/>'
        f'<w:bottom w:w="0" w:type="dxa"/><w:right w:w="28" w:type="dxa"/></w:tblCellMar>'
        f"</w:tblPr><w:tblGrid>{grid}</w:tblGrid>"
    )


def _weather_value_row(w):
    """Werteszeile unter den Wetter-Labels.

    Station linksbündig, die vier schmalen Zahlenspalten zentriert unter ihrem
    Label — so wie in den Referenzberichten ausgemessen. Die Schnee-Spalte ist
    in der Vorlage bis zum Seitenrand breit; ihr Wert bleibt daher linksbündig
    direkt unter dem Label stehen.
    """
    numeric = [
        (_num(w.temp_max_c, "°C"), "center"),
        (_num(w.temp_min_c, "°C"), "center"),
        (_num(w.regen_mm, "mm"), "center"),
        (_num(w.wind_max_ms, "m/s"), "center"),
        (_num(w.schnee_cm, "cm", decimals=0), None),
    ]
    cells = _cell(LABEL_COL, _para(""))
    cells += _cell(COL_WIDTHS[1], _para(_run(w.station or ""), after=60))
    for width, (value, align) in zip(COL_WIDTHS[2:], numeric):
        cells += _cell(width, _para(_run(value), align=align, after=60))
    return _row(cells)


def _bar_cell(temp: float | None, max_temp: float) -> str:
    """Ein Balken des Temperaturdiagramms, unten ausgerichtet."""
    if temp is None or temp <= 0 or max_temp <= 0:
        return _cell(HOURLY_VALUE_W, _para(""), valign="bottom")
    height_pt = BAR_MAX_PT * (temp / max_temp)
    body = _para(
        "",
        shading=BAR_COLOR,
        indent=BAR_INDENT,
        exact_height=max(int(height_pt * 20), 20),
    )
    return _cell(HOURLY_VALUE_W, body, valign="bottom")


def _hourly_table(stundenwerte: list) -> str:
    """Verschachtelte Tabelle: Uhrzeiten, Temperaturdiagramm, Messwerte, Symbole."""
    values = stundenwerte[:12]
    temps = [s.temperatur_c for s in values if s.temperatur_c is not None]
    max_temp = max(temps) if temps else 0.0

    grid = f'<w:gridCol w:w="{HOURLY_LABEL_W}"/>' + (
        f'<w:gridCol w:w="{HOURLY_VALUE_W}"/>' * 12
    )
    tbl = _nested_table_open(VALUE_SPAN, grid)

    def text_row(label: str, render, *, font: str = FONT, size: int = SZ_NORMAL,
                 after: int = 0) -> str:
        row = (
            f'<w:tc><w:tcPr><w:tcW w:w="{HOURLY_LABEL_W}" w:type="dxa"/>'
            f"{_borders(False, False)}</w:tcPr>"
            f"{_para(_run(label, bold=True), after=after)}</w:tc>"
        )
        for s in values:
            row += (
                f'<w:tc><w:tcPr><w:tcW w:w="{HOURLY_VALUE_W}" w:type="dxa"/>'
                f"{_borders(False, False)}</w:tcPr>"
                f"{_para(_run(render(s), font=font, size=size), align='center', after=after)}</w:tc>"
            )
        return f"<w:tr>{row}</w:tr>"

    tbl += text_row("Uhrzeit", lambda s: f"{s.stunde:02d}", after=40)

    # Diagrammzeile: feste Höhe, Balken wachsen von unten.
    if temps:
        chart = (
            f'<w:tc><w:tcPr><w:tcW w:w="{HOURLY_LABEL_W}" w:type="dxa"/>'
            f"{_borders(False, False)}</w:tcPr>{_para('')}</w:tc>"
        )
        for s in values:
            chart += _bar_cell(s.temperatur_c, max_temp)
        tbl += (
            f'<w:tr><w:trPr><w:trHeight w:val="{BAR_MAX_PT * 20}" '
            f'w:hRule="exact"/></w:trPr>{chart}</w:tr>'
        )

    tbl += text_row("Temp. (°C)", lambda s: "" if s.temperatur_c is None else f"{s.temperatur_c:.1f}")
    tbl += text_row("Wind (m/s)", lambda s: "" if s.wind_ms is None else f"{s.wind_ms:.1f}")
    tbl += text_row("Wind (Grad)", lambda s: "" if s.wind_grad is None else f"{s.wind_grad:.0f}")
    tbl += text_row(
        "Bewölkung",
        lambda s: WETTER_SYMBOLE.get(s.icon or "", ""),
        font=SYMBOL_FONT,
        size=SZ_SYMBOL,
    )

    return tbl + "</w:tbl>"


def _hourly_row(stundenwerte: list):
    body = _hourly_table(stundenwerte) + _para("")
    cells = _cell(LABEL_COL, _para(""))
    cells += _cell(VALUE_SPAN, body, gridspan=6)
    return _row(cells)


def _note_row(text: str, *, bottom: bool):
    paras = "".join(
        _para(_run(line), after=24) for line in text.splitlines() if line.strip()
    )
    cells = _cell(LABEL_COL, _para(""), bottom=bottom)
    cells += _cell(VALUE_SPAN, paras or _para(""), gridspan=6, bottom=bottom)
    return _row(cells)


def _firma_row(firma, *, bottom: bool = True):
    """Ein Firmenblock als zweispaltige Tabelle. Leere Felder werden weggelassen."""
    fields: list[tuple[str, str, bool]] = []
    if firma.firma:
        fields.append(("Firma:", firma.firma, True))
    if firma.ort:
        fields.append(("Ort:", firma.ort, False))
    if firma.personen:
        fields.append(("Personen:", str(firma.personen), False))
    if firma.leistung:
        fields.append(("Leistung:", firma.leistung, False))
    if firma.besonderes:
        fields.append(("Besonders:", firma.besonderes, False))

    grid = f'<w:gridCol w:w="{FIRMA_LABEL_W}"/><w:gridCol w:w="{FIRMA_VALUE_W}"/>'
    tbl = _nested_table_open(VALUE_SPAN, grid)
    for i, (label, value, value_bold) in enumerate(fields):
        after = 0 if i == len(fields) - 1 else 24
        tbl += (
            "<w:tr>"
            f'<w:tc><w:tcPr><w:tcW w:w="{FIRMA_LABEL_W}" w:type="dxa"/>'
            f"{_borders(False, False)}</w:tcPr>{_para(_run(label), after=after)}</w:tc>"
            f'<w:tc><w:tcPr><w:tcW w:w="{FIRMA_VALUE_W}" w:type="dxa"/>'
            f"{_borders(False, False)}</w:tcPr>"
            f"{_para(_run(value, bold=value_bold), after=after)}</w:tc>"
            "</w:tr>"
        )
    tbl += "</w:tbl>"

    body = (tbl + _para("")) if fields else _para("")
    cells = _cell(LABEL_COL, _para(_run("Firmen", bold=True)), bottom=bottom)
    cells += _cell(VALUE_SPAN, body, gridspan=6, bottom=bottom)
    return _row(cells)


def _set_cell_paragraphs(cell_tc, paragraphs_xml: str) -> None:
    """Ersetzt den Inhalt einer bestehenden Vorlagenzelle."""
    for child in list(cell_tc):
        if child.tag in (qn("w:p"), qn("w:tbl")):
            cell_tc.remove(child)
    for para in parse_xml(f"<w:root {nsdecls('w')}>{paragraphs_xml}</w:root>"):
        cell_tc.append(para)


def _fill_projekt_header(doc, projekt: str) -> None:
    """Projektname mit Tabstopp rechts neben das Label 'Projekt' setzen."""
    for para in doc.paragraphs:
        if para.text.strip() == "Projekt":
            para.paragraph_format.tab_stops.add_tab_stop(Twips(TAB_VALUE_COL))
            para._p.append(parse_xml(f"<w:r {nsdecls('w')}><w:tab/></w:r>"))
            para._p.append(parse_xml(
                f"<w:r {nsdecls('w')}>"
                f'<w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}"/><w:b/>'
                f'<w:sz w:val="{SZ_PROJEKT}"/><w:szCs w:val="{SZ_PROJEKT}"/></w:rPr>'
                f'<w:t xml:space="preserve">{escape(projekt)}</w:t></w:r>'
            ))
            return


def _fill_footer_line(doc, projekt: str, datum: date) -> None:
    for para in doc.paragraphs:
        if para.text.strip() == "Bautagebuch":
            para.runs[0].text = f"Bautagebuch - {projekt} - {_fmt_date(datum)}"
            return


def _shrink_page_spacer(doc) -> None:
    """Entfernt den großen Leerraum-Absatz der Vorlage.

    Die Blanko-Vorlage schiebt die Fußzeile mit einem ~12,7 cm hohen
    ``w:after``-Absatz ans Seitenende (für handschriftliche Nutzung gedacht).
    Der automatisch erzeugte Bericht ist kompakt; dieser Abstand würde die
    Fußzeile auf eine zweite Seite drücken. Große Abstände auf Absatzebene
    werden daher auf ein moderates Maß begrenzt.
    """
    body = doc.element.body
    for para in body.findall(qn("w:p")):
        ppr = para.find(qn("w:pPr"))
        if ppr is None:
            continue
        spacing = ppr.find(qn("w:spacing"))
        if spacing is None:
            continue
        after = spacing.get(qn("w:after"))
        if after is not None and int(after) > 480:
            spacing.set(qn("w:after"), "240")


def _set_bottom_border(tr, visible: bool) -> None:
    for tc in tr.findall(qn("w:tc")):
        borders = tc.find(f"{qn('w:tcPr')}/{qn('w:tcBorders')}")
        if borders is None:
            continue
        bottom = borders.find(qn("w:bottom"))
        if bottom is None:
            continue
        if visible:
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "5")
            bottom.set(qn("w:space"), "0")
            bottom.set(qn("w:color"), "000000")
        else:
            bottom.set(qn("w:val"), "nil")
            for attr in ("w:sz", "w:color", "w:space"):
                if bottom.get(qn(attr)) is not None:
                    del bottom.attrib[qn(attr)]


def _drop_row_height(tr) -> None:
    trpr = tr.find(qn("w:trPr"))
    if trpr is None:
        return
    height = trpr.find(qn("w:trHeight"))
    if height is not None:
        trpr.remove(height)


def _collapse_cell(tc) -> None:
    """Überzählige Leerabsätze einer Vorlagenzelle entfernen."""
    paragraphs = tc.findall(qn("w:p"))
    for para in paragraphs[1:]:
        tc.remove(para)


def generate_bautagesbericht(
    data: BautagesberichtJSON,
    template_path: Path | None = None,
) -> Path:
    if template_path is None:
        template_path = settings.template_dir / "Bautagesbericht_HPP_leer.docx"

    doc = Document(str(template_path))

    _fill_projekt_header(doc, data.projekt)
    _fill_footer_line(doc, data.projekt, data.datum)
    _shrink_page_spacer(doc)

    table = doc.tables[0]
    rows = table._tbl.findall(qn("w:tr"))
    row_datum, row_wetter, row_firma, row_firma_leer, row_unterschrift = rows[:5]

    # Die Vorlage reserviert feste Zeilenhöhen für den handschriftlichen
    # Gebrauch; im generierten Bericht richtet sich die Höhe nach dem Inhalt.
    for tr in rows[:5]:
        _drop_row_height(tr)
    for tc in row_firma_leer.findall(qn("w:tc")):
        _collapse_cell(tc)

    # Datum
    datum_cells = row_datum.findall(qn("w:tc"))
    _set_cell_paragraphs(datum_cells[1], _para(_run(_fmt_date_weekday(data.datum))))

    # Wetterblock unterhalb der bestehenden Label-Zeile aufbauen
    anchor = row_wetter
    block_rows = []

    def append_block_row(new_row) -> None:
        nonlocal anchor
        anchor.addnext(new_row)
        anchor = new_row
        block_rows.append(new_row)

    if data.wetter:
        append_block_row(_weather_value_row(data.wetter))
        if data.wetter.stundenwerte:
            append_block_row(_hourly_row(data.wetter.stundenwerte))

    if data.haupteintrag:
        append_block_row(_note_row(data.haupteintrag, bottom=False))

    if block_rows:
        # Labels und Werte bilden einen Block: nur die letzte Zeile wird
        # nach unten abgegrenzt.
        _set_bottom_border(row_wetter, False)
        _set_bottom_border(block_rows[-1], True)

    # Firmenblöcke: erste Vorlagenzeile ersetzen, weitere dahinter einfügen
    if data.firmen:
        firma_anchor = row_firma
        for firma in data.firmen:
            new_row = _firma_row(firma)
            firma_anchor.addnext(new_row)
            firma_anchor = new_row
        table._tbl.remove(row_firma)

    # Unterschriftsdatum über das graue Label setzen
    unterschrift_cells = row_unterschrift.findall(qn("w:tc"))
    signed = data.unterschrift_datum or date.today()
    _set_cell_paragraphs(
        unterschrift_cells[1],
        _para(_run(_fmt_date(signed)), align="center")
        + _para(_run("Datum ", size=SZ_SMALL, color=GRAY), align="center"),
    )
    # In den Referenzberichten steht das Komma vor dem Firmennamen.
    hpp_cell = unterschrift_cells[2]
    first_run = hpp_cell.find(f"{qn('w:p')}/{qn('w:r')}/{qn('w:t')}")
    if first_run is not None and not (first_run.text or "").startswith(","):
        first_run.text = f", {first_run.text or ''}"

    safe_projekt = "".join(
        c if c.isalnum() or c in " -_" else "_" for c in data.projekt
    ).strip().replace(" ", "_")[:40] or "Projekt"
    output_path = settings.output_dir / f"BTB_{data.datum.isoformat()}_{safe_projekt}.docx"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))

    return output_path
