"""Generate the Treelancer Monthly Timesheet as a single-page, TEXT-LAYER PDF
that the existing trees-invoice ``TreelancerParser`` ingests unchanged.

Why this file is fussy about coordinates
----------------------------------------
The invoice parser (treesinvoice/parsers/treelancer.py) does NOT read a tagged
form; it re-derives fields purely from where words land on the page, bucketing
each word by the *centre* of its bounding box:

  Header value bands (PyMuPDF top-left points):
    value-1  cx in [95, 205)   -> Treelancer Name / Position / Month
    value-2  cx in [320, 460)  -> Client Name / PO Code / Year
  Daily table columns:
    date [0,108)  standard [108,207)  overtime [207,317)
    work_location [317,423)  remarks [423,800)
  Rows are anchored by the *pure-digit* day number in the date column;
  the footer "Total" line's std/ot must equal the summed rows.

So this generator positions every token to fall in the correct band, and wraps
long values *within* their column width so no word drifts into the next field.
reportlab's origin is bottom-left (y up); the parser/PyMuPDF use top-left
(y down). We author all geometry in top-down points and convert once at draw
time (``_y`` below). Colours/rules/grid are vector-only and add no words.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from reportlab.lib.colors import Color, HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

# ---- Brand palette (Trees Engineering) ------------------------------------ #
NAVY = HexColor("#0A2160")
GOLD = HexColor("#A0730F")
CREAM = HexColor("#F6F2E9")
GRID = Color(0.72, 0.72, 0.72)
INK = HexColor("#1A1A1A")

# ---- Page + band geometry (top-down points; must match the parser) -------- #
PAGE_W, PAGE_H = 595.276, 841.89  # A4 portrait

LABEL_1_X = 10.0            # left labels (Treelancer Name / POSITION / MONTH / Total)
LABEL_2_X = 210.0           # right labels (CLIENT Name / PO CODE / YEAR)
VALUE_1_X = 98.0            # value-1 band draw origin (band [95,205))
VALUE_1_W = 104.0
VALUE_2_X = 323.0           # value-2 band draw origin (band [320,460))
VALUE_2_W = 132.0

# Daily table column centres / origins (chosen well inside each band).
COL_DATE_CX = 54.0          # band [0,108)
COL_STD_CX = 157.0          # band [108,207)
COL_OT_CX = 262.0           # band [207,317)
COL_LOC_X = 322.0           # band [317,423) left-aligned
COL_LOC_W = 96.0
COL_REM_X = 428.0           # band [423,800) left-aligned
COL_REM_W = PAGE_W - COL_REM_X - 12.0

# Column boundary x's for drawing vertical grid rules.
COL_BOUNDS = [4.0, 108.0, 207.0, 317.0, 423.0, PAGE_W - 6.0]

# ---- Vertical rhythm (baselines, top-down) -------------------------------- #
Y_TITLE = 34.0
Y_HDR_1 = 66.0              # Treelancer Name / CLIENT Name
Y_HDR_2 = 100.0            # POSITION / PO CODE
Y_HDR_3 = 134.0           # MONTH / YEAR
Y_TABLE_HEAD = 156.0
Y_TABLE_SUB = 166.0
Y_ROW_0 = 180.0
ROW_H = 15.0

FONT = "Helvetica"
FONT_B = "Helvetica-Bold"


@dataclass
class DailyRow:
    day: int
    standard_hours: Decimal = Decimal("0")
    overtime_hours: Decimal = Decimal("0")
    work_location: str = ""
    remarks: str = ""
    is_off: bool = False


@dataclass
class TimesheetPDF:
    resource_name: str
    client_name: str
    position: str
    po_code: str | None            # None -> "NA"
    month: int                      # 1..12
    year: int
    rows: list[DailyRow] = field(default_factory=list)
    line_manager_name: str = ""
    line_manager_designation: str = ""
    signature_name: str = ""        # typed e-signature
    date_signed: date | None = None
    email: str | None = None        # optional (some template sheets carry EMAIL)

    # -- totals ------------------------------------------------------------- #
    @property
    def total_standard(self) -> Decimal:
        return sum((r.standard_hours for r in self.rows), Decimal("0"))

    @property
    def total_overtime(self) -> Decimal:
        return sum((r.overtime_hours for r in self.rows), Decimal("0"))


def _y(top_down: float) -> float:
    """Top-down point -> reportlab bottom-up point."""
    return PAGE_H - top_down


def _fmt_hours(v: Decimal) -> str:
    """Whole hours as '8', fractional as '8.5'; zero renders blank (like the
    Excel empty cells the parser treats as 0)."""
    if v == 0:
        return ""
    if v == v.to_integral_value():
        return str(int(v))
    return f"{v.normalize()}"


def _wrap(text: str, font: str, size: float, max_w: float) -> list[str]:
    if not text:
        return []
    lines: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if stringWidth(trial, font, size) <= max_w or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _one_line(text: str, font: str, size: float, max_w: float) -> str:
    """Fit text on one line, appending an ellipsis if it must be clipped
    (single-page constraint: cells never wrap onto a second visual line)."""
    if not text or stringWidth(text, font, size) <= max_w:
        return text
    ell = "…"
    while text and stringWidth(text + ell, font, size) > max_w:
        text = text[:-1]
    return text.rstrip() + ell


def render(data: TimesheetPDF, out: Path | str | None = None) -> bytes:
    """Render the timesheet. Writes to ``out`` if given; always returns bytes."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"Treelancer Monthly Timesheet - {data.resource_name} - {data.month:02d}/{data.year}")

    _draw_header_band(c)
    _draw_header_fields(c, data)
    _draw_table(c, data)
    _draw_footer(c, data)

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()
    if out is not None:
        Path(out).write_bytes(pdf_bytes)
    return pdf_bytes


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def _draw_header_band(c: canvas.Canvas) -> None:
    # Navy title bar with the required "Trees Engineering Sdn. Bhd." token.
    c.setFillColor(NAVY)
    c.rect(0, _y(48), PAGE_W, 48, stroke=0, fill=1)
    c.setFillColor(CREAM)
    c.setFont(FONT_B, 13)
    c.drawString(LABEL_1_X, _y(Y_TITLE), "Treelancer - Monthly Timesheet")
    c.setFillColor(GOLD)
    c.setFont(FONT_B, 10)
    c.drawRightString(PAGE_W - 12, _y(Y_TITLE), "Trees Engineering Sdn. Bhd.")
    # Gold rule under the header field block.
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.2)
    c.line(4, _y(148), PAGE_W - 6, _y(148))


def _label(c: canvas.Canvas, x: float, y: float, text: str, size: float = 9) -> None:
    c.setFillColor(NAVY)
    c.setFont(FONT_B, size)
    c.drawString(x, _y(y), text)


def _value_block(c: canvas.Canvas, x: float, y: float, max_w: float, text: str, size: float = 9) -> None:
    """Draw a possibly-wrapped value, top line at baseline ``y``, growing down.
    Each wrapped line stays within [x, x+max_w] so all word centres remain in
    the intended value band."""
    c.setFillColor(INK)
    c.setFont(FONT, size)
    for i, ln in enumerate(_wrap(text, FONT, size, max_w)):
        c.drawString(x, _y(y + i * (size + 1.5)), ln)


def _draw_header_fields(c: canvas.Canvas, d: TimesheetPDF) -> None:
    # Row 1: Treelancer Name | CLIENT Name
    _label(c, LABEL_1_X, Y_HDR_1, "Treelancer Name")
    _value_block(c, VALUE_1_X, Y_HDR_1, VALUE_1_W, d.resource_name)
    _label(c, LABEL_2_X, Y_HDR_1, "CLIENT Name")
    _value_block(c, VALUE_2_X, Y_HDR_1, VALUE_2_W, d.client_name)

    # Row 2: POSITION | PO CODE (+ instruction sub-label, kept out of value-2)
    _label(c, LABEL_1_X, Y_HDR_2, "POSITION")
    _value_block(c, VALUE_1_X, Y_HDR_2, VALUE_1_W, d.position)
    _label(c, LABEL_2_X, Y_HDR_2, "PO CODE")
    c.setFillColor(GRID)
    c.setFont(FONT, 6.5)
    c.drawString(LABEL_2_X, _y(Y_HDR_2 + 9), "(Put NA, if unknown)")
    _value_block(c, VALUE_2_X, Y_HDR_2, VALUE_2_W, d.po_code or "NA")

    # Row 3: MONTH | YEAR
    _label(c, LABEL_1_X, Y_HDR_3, "MONTH")
    _value_block(c, VALUE_1_X, Y_HDR_3, VALUE_1_W, calendar.month_name[d.month])
    _label(c, LABEL_2_X, Y_HDR_3, "YEAR")
    _value_block(c, VALUE_2_X, Y_HDR_3, VALUE_2_W, str(d.year))

    if d.email:
        c.setFillColor(INK)
        c.setFont(FONT, 7.5)
        c.drawRightString(PAGE_W - 12, _y(Y_HDR_3), f"EMAIL: {d.email}")


def _draw_table(c: canvas.Canvas, d: TimesheetPDF) -> None:
    ndays = calendar.monthrange(d.year, d.month)[1]

    # Column header labels.
    c.setFillColor(NAVY)
    c.setFont(FONT_B, 8)
    c.drawCentredString(COL_DATE_CX, _y(Y_TABLE_HEAD), "DATES")
    c.drawCentredString(COL_STD_CX, _y(Y_TABLE_HEAD), "STANDARD")
    c.drawCentredString(COL_OT_CX, _y(Y_TABLE_HEAD), "OVERTIME")
    c.drawCentredString((317 + 423) / 2, _y(Y_TABLE_HEAD), "WORK LOCATION")
    c.setFont(FONT_B, 7)
    c.drawString(COL_REM_X, _y(Y_TABLE_HEAD), "REMARKS / NOTES (Purpose / Nature of Work)")
    c.setFont(FONT, 6.5)
    c.setFillColor(GRID)
    c.drawCentredString(COL_STD_CX, _y(Y_TABLE_SUB), "# Hours Worked")
    c.drawCentredString(COL_OT_CX, _y(Y_TABLE_SUB), "# Hours Worked")

    rows_by_day = {r.day: r for r in d.rows}
    table_top = Y_ROW_0 - 11
    table_bottom = Y_ROW_0 + (ndays - 1) * ROW_H + 4

    # Horizontal grid rules.
    c.setStrokeColor(GRID)
    c.setLineWidth(0.4)
    for i in range(ndays + 1):
        yy = table_top + i * ROW_H
        c.line(COL_BOUNDS[0], _y(yy), COL_BOUNDS[-1], _y(yy))
    # Vertical grid rules.
    for bx in COL_BOUNDS:
        c.line(bx, _y(table_top), bx, _y(table_bottom))

    for i in range(ndays):
        day = i + 1
        base = Y_ROW_0 + i * ROW_H
        r = rows_by_day.get(day)

        # Day number — the ONLY pure-digit token in the date column (row anchor).
        c.setFillColor(INK)
        c.setFont(FONT, 8)
        c.drawCentredString(COL_DATE_CX, _y(base), str(day))
        if r is None:
            continue

        if r.is_off:
            c.setFillColor(GOLD)
            c.setFont(FONT_B, 8)
            c.drawString(COL_REM_X, _y(base), "OFF")
            continue

        c.setFillColor(INK)
        c.setFont(FONT, 8)
        std, ot = _fmt_hours(r.standard_hours), _fmt_hours(r.overtime_hours)
        if std:
            c.drawCentredString(COL_STD_CX, _y(base), std)
        if ot:
            c.drawCentredString(COL_OT_CX, _y(base), ot)
        if r.work_location:
            c.drawString(COL_LOC_X, _y(base), _one_line(r.work_location, FONT, 8, COL_LOC_W))
        if r.remarks:
            c.drawString(COL_REM_X, _y(base), _one_line(r.remarks, FONT, 8, COL_REM_W))

    # Totals row: label + summed std/ot in their columns (parser cross-checks).
    total_base = table_bottom + 11
    c.setFillColor(NAVY)
    c.setFont(FONT_B, 8.5)
    c.drawString(LABEL_1_X, _y(total_base), "Total")
    c.setFillColor(INK)
    c.setFont(FONT_B, 8.5)
    c.drawCentredString(COL_STD_CX, _y(total_base), _fmt_hours(d.total_standard) or "0")
    c.drawCentredString(COL_OT_CX, _y(total_base), _fmt_hours(d.total_overtime) or "0")
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.8)
    c.line(COL_BOUNDS[0], _y(total_base + 5), COL_BOUNDS[-1], _y(total_base + 5))
    return None


def _draw_footer(c: canvas.Canvas, d: TimesheetPDF) -> None:
    ndays = calendar.monthrange(d.year, d.month)[1]
    base = Y_ROW_0 + (ndays - 1) * ROW_H + 40

    _label(c, LABEL_1_X, base, "Submitted By", 9)

    _label(c, LABEL_1_X, base + 18, "Treelancer", 8)
    _value_block(c, 78, base + 18, 120, d.resource_name, 8)
    _label(c, LABEL_2_X, base + 18, "LINE MANAGER", 8)
    _value_block(c, 300, base + 18, 150, d.line_manager_name, 8)

    _label(c, LABEL_1_X, base + 34, "Position", 8)
    _value_block(c, 78, base + 34, 120, d.position, 8)
    _label(c, LABEL_2_X, base + 34, "DESIGNATION", 8)
    _value_block(c, 300, base + 34, 150, d.line_manager_designation, 8)

    # E-signature: typed name + confirmation, never a drawn scrawl.
    _label(c, LABEL_1_X, base + 52, "Signature", 8)
    c.setFillColor(INK)
    c.setFont("Helvetica-Oblique", 7.5)
    sig = _one_line(f"/s/ {d.signature_name}", "Helvetica-Oblique", 7.5, 108) if d.signature_name else ""
    c.drawString(78, _y(base + 52), sig)
    if d.signature_name:
        c.setFillColor(GRID)
        c.setFont(FONT, 6)
        c.drawString(78, _y(base + 60), "(e-signed & confirmed)")
    _label(c, LABEL_2_X, base + 52, "Signature", 8)

    _label(c, LABEL_1_X, base + 68, "Date Signed", 8)
    c.setFillColor(INK)
    c.setFont(FONT, 8)
    if d.date_signed:
        c.drawString(78, _y(base + 68), d.date_signed.strftime("%d/%m/%Y"))
    _label(c, LABEL_2_X, base + 68, "Date Signed", 8)

    c.setFillColor(GRID)
    c.setFont(FONT, 6.5)
    c.drawString(
        LABEL_1_X, _y(base + 88),
        "Treelancer who have taken leave/off days may use the following abbreviations "
        "in describing the nature of leave(s) taken.",
    )
    c.setFillColor(NAVY)
    c.setFont(FONT_B, 7.5)
    c.drawString(LABEL_1_X, _y(base + 100), "Leave/Day Off Codes:  OFF")
